#!/bin/sh
# push-guard.sh -- fast-fail pre-push / CI pre-flight guard for Go repos.
#
# Three checks, in order; the first failure wins and prints the exact error:
#   1. git diff --check   -- conflict markers (<<<<<<< ======= >>>>>>>) + whitespace errors
#   2. gofmt (exact)      -- Go parse errors AND unformatted files. The naive
#                            `gofmt -l . | wc -l` pattern misses parse errors
#                            (gofmt prints them to stderr, exits 2, lists nothing).
#                            This is exactly what broke herd's Linux CI on
#                            2026-09-18 (runs 35400989022 / 35401074912: conflict
#                            markers left in mesh/gateway/astmatrix.go:93-104).
#   3. go vet             -- scoped to changed packages only (10-30s budget).
#
# Usage:
#   push-guard.sh pre-push                        # git pre-push hook: ref lines on stdin
#   PUSH_GUARD_RANGE='base...head' push-guard.sh  # CI / explicit range
#   push-guard.sh                                 # worktree mode: staged+unstaged vs HEAD
#   PUSH_GUARD_SKIP=1 ...                         # emergency bypass (loud, never silent)
#
# Adopted 2026-09-18, debate d867e8f6. Canonical fleet copy: /home/toxic/bin/push-guard.sh
# Pre-push install one-liner:
#   install -Dm755 /home/toxic/bin/pre-push "$(git rev-parse --git-dir)/hooks/pre-push"

set -eu

ZERO40='0000000000000000000000000000000000000000'
EMPTY_TREE='4b825dc642cb6eb9a060e54bf8d69288fbee4904'

START_MS="$(date +%s%N | cut -c1-13)"
log()  { printf 'push-guard: %s\n' "$*"; }
fail() { printf 'push-guard: FAIL: %s\n' "$*" >&2; exit 1; }
now_ms() { date +%s%N | cut -c1-13; }

# --- emergency override: loud, never silent ---------------------------------
if [ "${PUSH_GUARD_SKIP:-0}" = "1" ]; then
    log 'BYPASSED via PUSH_GUARD_SKIP=1 -- proceeding UNGUARDED (this line is the audit trail)'
    exit 0
fi

command -v git >/dev/null 2>&1 || fail 'git not found on PATH'
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || fail 'not inside a git work tree'
cd "$ROOT"

TMPD="$(mktemp -d)" || fail 'mktemp failed'
trap 'rm -rf "$TMPD"' EXIT INT TERM
RANGES="$TMPD/ranges"; FILES="$TMPD/files"; GOFILES="$TMPD/gofiles"; PKGS="$TMPD/pkgs"; UNTRACKED="$TMPD/untracked"
: > "$RANGES"; : > "$FILES"; : > "$GOFILES"; : > "$PKGS"; : > "$UNTRACKED"

add_range() { printf '%s\n' "$1" >> "$RANGES"; }

norm_range() { # $1 = "base...head" | "base..head" | single rev -> normalized "base...head"
    spec="$1"
    case "$spec" in
        *...*)
            base="${spec%%...*}"; head="${spec##*...}" ;;
        *..*)
            base="${spec%%..*}"; head="${spec##*..}" ;;
        *)
            head="$spec"
            if git rev-parse --verify --quiet "$spec^" >/dev/null 2>&1; then
                base="$spec^"
            else
                base="$EMPTY_TREE"
            fi ;;
    esac
    [ "$base" = "$ZERO40" ] && base="$EMPTY_TREE"
    printf '%s...%s' "$base" "$head"
}

# --- collect change ranges ---------------------------------------------------
MODE="${1:-range}"
if [ "$MODE" = "pre-push" ]; then
    # git pre-push stdin: "<local ref> <local sha> <remote ref> <remote sha>" per line
    seen=0
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        seen=1
        # word-split the four fields (refnames never contain spaces)
        # shellcheck disable=SC2086
        set -- $line
        local_ref="${1:-?}"; local_sha="${2:-}"; remote_sha="${4:-}"
        [ -z "$local_sha" ] && continue
        if [ "$local_sha" = "$ZERO40" ]; then
            log "ref $local_ref deleted -- nothing to guard"
            continue
        fi
        add_range "$(norm_range "$remote_sha...$local_sha")"
    done
    [ "$seen" -eq 1 ] || { log 'no ref updates on stdin -- nothing to guard'; exit 0; }
elif [ -n "${PUSH_GUARD_RANGE:-}" ]; then
    add_range "$(norm_range "$PUSH_GUARD_RANGE")"
else
    log 'worktree mode: guarding staged + unstaged changes vs HEAD'
fi

# --- check 1: conflict markers + whitespace errors ---------------------------
t0="$(now_ms)"
if [ -s "$RANGES" ]; then
    while IFS= read -r r; do
        [ -z "$r" ] && continue
        out="$(git diff --check "$r" -- 2>&1)" || true
        [ -n "$out" ] && fail "conflict markers / whitespace errors in range $r:
$out"
    done < "$RANGES"
else
    out="$(git diff --check -- 2>&1)" || true
    [ -n "$out" ] && fail "conflict markers / whitespace errors (unstaged):
$out"
    out="$(git diff --check --cached -- 2>&1)" || true
    [ -n "$out" ] && fail "conflict markers / whitespace errors (staged):
$out"
    # untracked files are invisible to plain `git diff` -- check each against /dev/null
    git ls-files --others --exclude-standard -z | tr '\0' '\n' > "$UNTRACKED" 2>/dev/null || true
    while IFS= read -r f; do
        [ -z "$f" ] && continue
        out="$(git diff --check --no-index /dev/null "$f" 2>&1)" || true
        [ -n "$out" ] && fail "conflict markers / whitespace errors (untracked: $f):
$out"
    done < "$UNTRACKED"
fi
log "check 1 (git diff --check): PASS ($(( $(now_ms) - t0 )) ms)"

# --- collect changed files ----------------------------------------------------
if [ -s "$RANGES" ]; then
    while IFS= read -r r; do
        [ -z "$r" ] && continue
        git diff --name-only --diff-filter=ACMRT "$r" -- >> "$FILES" 2>/dev/null || true
    done < "$RANGES"
else
    git diff --name-only HEAD -- >> "$FILES" 2>/dev/null || true
    cat "$UNTRACKED" >> "$FILES" 2>/dev/null || true
fi
sort -u "$FILES" -o "$FILES"
grep '\.go$' "$FILES" > "$GOFILES" || true

if [ ! -s "$GOFILES" ]; then
    log 'no Go files changed -- gofmt/go vet skipped'
    log "ALL CHECKS PASS: total $(( $(now_ms) - START_MS )) ms"
    exit 0
fi
log "$(wc -l < "$GOFILES" | tr -d ' ') Go file(s) changed"

# --- check 2: gofmt -- exact (parse errors fail, not just -l output) -----------
t0="$(now_ms)"
if ! command -v gofmt >/dev/null 2>&1; then
    log 'gofmt not found -- Go checks SKIPPED (diff --check above still enforced)'
    log "CHECKS DONE (partial): total $(( $(now_ms) - START_MS )) ms"
    exit 0
fi
set +e
gofmt_out="$(xargs -a "$GOFILES" gofmt -l -- 2>&1)"
gofmt_code=$?
set -e
[ "$gofmt_code" -ne 0 ] && fail "gofmt parse errors (exit $gofmt_code):
$gofmt_out"
[ -n "$gofmt_out" ] && fail "gofmt: these files need formatting:
$gofmt_out"
log "check 2 (gofmt): PASS ($(( $(now_ms) - t0 )) ms)"

# --- check 3: go vet -- scoped to changed packages only ------------------------
t0="$(now_ms)"
while IFS= read -r f; do
    [ -z "$f" ] && continue
    d="$(dirname "$f")"
    case "$d" in .) p='./';; *) p="./$d";; esac
    printf '%s\n' "$p" >> "$PKGS"
done < "$GOFILES"
sort -u "$PKGS" -o "$PKGS"
log "vetting $(tr '\n' ' ' < "$PKGS")"
set +e
vet_out="$(xargs -a "$PKGS" go vet 2>&1)"
vet_code=$?
set -e
[ "$vet_code" -ne 0 ] && fail "go vet failed (exit $vet_code) on changed packages:
$vet_out"
log "check 3 (go vet): PASS ($(( $(now_ms) - t0 )) ms)"

log "ALL CHECKS PASS: total $(( $(now_ms) - START_MS )) ms"
