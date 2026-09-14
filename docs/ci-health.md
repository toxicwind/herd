# CI Health: budget-gate vs real failures

A triage guide for `toxicwind/herd` Actions failures, maintained alongside
`.github/workflows/workflow-health.yml` (the nightly monitor).

## The one thing to know

**Jobs that die in 2–4 seconds with 0 steps executed are a billing problem,
not a code problem.** No code change, rerun strategy, or workflow edit can
fix them. The account's Actions spending gate is blocking every job before a
runner is assigned.

## Budget-gate signature (confirmed 2026-09-14)

All three must hold:

1. **Zero steps started** — every job in the run has an empty `steps` list
   (no `started_at` on any step).
2. **Instant death** — `updated_at - created_at` on the run is seconds
   (observed: 4s, e.g. run `33797167331` on Linux CI).
3. **Billing annotation** — the failed job's check-run annotations contain:

   > The job was not started because recent account payments have failed or
   > your spending limit needs to be increased. Please check the 'Billing &
   > plans' section in your settings

Real example: Linux CI run `33797167331` (2026-09-03) — job `100787535541`
(`run-tests`), conclusion `failure`, 0 steps, 2s duration, annotation above.

## Triage procedure (30 seconds, by hand)

1. Open the failed run → click the failed job → look at the steps list.
2. **No steps at all?** → budget gate. Go to account Settings → Billing &
   plans → fix payment method / raise the Actions spending limit. Do not
   open the code.
3. **Steps ran and one failed?** → real failure. Read the failing step's log
   as usual.
4. **Ambiguous?** → let the monitor classify it (below), or compare against
   the signature above.

## The nightly monitor

`.github/workflows/workflow-health.yml` runs daily (`23 6 * * *` UTC) and on
`workflow_dispatch`. It:

- pulls the last 10 runs of each key workflow (Build Unified Docker Image,
  Build Containers, Close inactive issues, Windows CI, Linux CI, UI Tests),
- classifies each recent failure as `BUDGET_GATE`, `REAL_FAILURE`, or
  `UNKNOWN` using the signature above (annotation text is matched
  case-insensitively against `spending limit` / `billing` /
  `payments have failed` / `not started because`),
- posts a markdown table to the job summary,
- maintains a single tracking issue, **"CI health: budget-gate vs real
  failures"**, updating it and commenting **only when the classification
  changes** (no issue spam),
- exits non-zero only when a `REAL_FAILURE` is found, so budget gates stay
  visible in the summary without paging anyone.

The script is dependency-light: bash heredoc + Python stdlib + `urllib`,
no third-party actions (not even `checkout`).

### Caveats

- If the billing gate is active, **the monitor itself cannot run** —
  scheduled runs need a runner too. A missing monitor run is itself a
  signal: check billing first.
- Classification is heuristic. `UNKNOWN` means "0 steps started but the
  budget annotation couldn't be confirmed" — check that run by hand.

### Local self-test

The embedded script has a `--self-test` mode with fixture-based tests
(no network). To run it, extract the Python between the `PYEOF` markers:

```bash
sed -n "/python3 - <<'PYEOF'/,/^          PYEOF/p" \
  .github/workflows/workflow-health.yml \
  | sed '1d;$d' | sed 's/^          //' > /tmp/health.py
python3 /tmp/health.py --self-test
```
