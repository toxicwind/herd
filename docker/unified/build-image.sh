#!/bin/bash
#
# Build script for unified container with version pinning
#
# Usage:
#   ./build-image.sh --cuda                              # Build CUDA image
#   ./build-image.sh --vulkan                            # Build Vulkan image
#   ./build-image.sh --cuda --no-cache                   # Build without cache
#   ./build-image.sh --cuda --resolve                   # Print resolved commit hashes (name=value on stdout)
#   ./build-image.sh --cuda --stage=base                # Build + push the builder base image
#   ./build-image.sh --cuda --stage=llama               # Build + push one project's artifacts image
#   ./build-image.sh --cuda --assemble                  # Assemble the unified image from published artifacts
#   LLAMA_REF=b1234 ./build-image.sh --vulkan            # Pin llama.cpp to a commit hash
#   LLAMA_REF=v1.2.3 ./build-image.sh --cuda             # Pin llama.cpp to a tag
#   WHISPER_REF=v1.0.0 ./build-image.sh --vulkan         # Pin whisper.cpp to a tag
#   SD_REF=master ./build-image.sh --cuda                # Pin stable-diffusion.cpp to a branch
#   LS_VERSION=170 ./build-image.sh --cuda               # Override llama-swap version
#   IK_LLAMA_REF=main ./build-image.sh --cuda            # Pin ik_llama.cpp to main branch (CUDA only)
#

set -euo pipefail

BACKEND=""
NO_CACHE=false
RESOLVE=false
STAGE=""
ASSEMBLE=false
WHISPER_FFMPEG="${WHISPER_FFMPEG:-yes}"

for arg in "$@"; do
    case $arg in
        --cuda)
            BACKEND="cuda"
            ;;
        --vulkan)
            BACKEND="vulkan"
            ;;
        --no-cache)
            NO_CACHE=true
            ;;
        --resolve)
            RESOLVE=true
            ;;
        --stage=*)
            STAGE="${arg#--stage=}"
            ;;
        --assemble)
            ASSEMBLE=true
            ;;
        --help|-h)
            echo "Usage: ./build-image.sh --cuda|--vulkan [--no-cache]"
            echo "       ./build-image.sh --cuda|--vulkan --resolve"
            echo "       ./build-image.sh --cuda|--vulkan --stage=base|llama|whisper|sd|audio|ik-llama"
            echo "       ./build-image.sh --cuda|--vulkan --assemble"
            echo ""
            echo "Options:"
            echo "  --cuda      Build CUDA image (NVIDIA GPUs)"
            echo "  --vulkan    Build Vulkan image (AMD GPUs and compatible hardware)"
            echo "  --no-cache  Force rebuild without using Docker cache"
            echo "  --resolve   Resolve all upstream refs and print name=value pairs on"
            echo "              stdout (human progress on stderr); no Docker involved"
            echo "  --stage=X   Build and push one content-addressed stage image to"
            echo "              \$ARTIFACT_REPO (base, or one project); skips when the"
            echo "              tag already exists in the registry"
            echo "  --assemble  Assemble the unified image from the published stage"
            echo "              images (nothing is compiled here)"
            echo "  --help, -h  Show this help message"
            echo ""
            echo "Environment variables:"
            echo "  DOCKER_IMAGE_TAG     Set custom image tag (default: llama-swap:unified-cuda or llama-swap:unified-vulkan)"
            echo "  LLAMA_REF            Pin llama.cpp to a commit, tag, or branch"
            echo "  WHISPER_REF          Pin whisper.cpp to a commit, tag, or branch"
            echo "  SD_REF               Pin stable-diffusion.cpp to a commit, tag, or branch"
            echo "  AUDIO_REF            Pin audio.cpp to a commit, tag, or branch"
            echo "  IK_LLAMA_REF         Pin ik_llama.cpp to a commit, tag, or branch (CUDA only)"
            echo "  LS_VERSION           Override llama-swap version (e.g., '170' or 'latest')"
            echo "  WHISPER_FFMPEG       Enable whisper.cpp FFmpeg support (default: yes)"
            echo "  ARTIFACT_REPO        Registry repo for --stage/--assemble images"
            echo "                       (default: ghcr.io/\${GITHUB_REPOSITORY:-mostlygeek/llama-swap}-build)"
            echo "  CUDA_VERSION         CUDA version for the base image (default: 12.9.1)"
            exit 0
            ;;
    esac
done

if [[ -z "$BACKEND" ]]; then
    echo "Error: No backend specified. Please use --cuda or --vulkan."
    echo ""
    echo "Usage: ./build-image.sh --cuda|--vulkan [--no-cache]"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$(dirname "${SCRIPT_DIR}")")"

DOCKER_IMAGE_TAG="${DOCKER_IMAGE_TAG:-llama-swap:unified-${BACKEND}}"

# Git repository URLs
LLAMA_REPO="https://github.com/ggml-org/llama.cpp.git"
WHISPER_REPO="https://github.com/ggml-org/whisper.cpp.git"
SD_REPO="https://github.com/leejet/stable-diffusion.cpp.git"
AUDIO_REPO="https://github.com/0xShug0/audio.cpp.git"
LLAMA_SWAP_REPO="https://github.com/mostlygeek/llama-swap.git"
IK_LLAMA_REPO="https://github.com/ikawrakow/ik_llama.cpp.git"

# Resolve a git ref (commit hash, tag, or branch) to a full commit hash.
# Requires only: git, network access to the remote.
resolve_ref() {
    local repo_url="$1"
    local ref="$2"

    # Full 40-char SHA — use as-is
    if [[ "${ref}" =~ ^[0-9a-f]{40}$ ]]; then
        echo "${ref}"
        return
    fi

    # Try tag then branch (exact match)
    local hash
    hash=$(git ls-remote "${repo_url}" "refs/tags/${ref}" "refs/heads/${ref}" 2>/dev/null | head -1 | cut -f1)
    if [[ -n "${hash}" ]]; then
        echo "${hash}"
        return
    fi

    # Short hash (7+ chars): scan all refs for a SHA with this prefix
    if [[ "${ref}" =~ ^[0-9a-f]{7,}$ ]]; then
        hash=$(git ls-remote "${repo_url}" 2>/dev/null | grep "^${ref}" | head -1 | cut -f1)
        if [[ -n "${hash}" ]]; then
            echo "${hash}"
            return
        fi
    fi

    echo "ERROR: Could not resolve ref '${ref}' for ${repo_url}" >&2
    if [[ "${ref}" =~ ^[0-9a-f]+$ && ${#ref} -lt 7 ]]; then
        echo "  Short hashes must be at least 7 characters (got ${#ref})." >&2
    else
        echo "  Tried: tag, branch, git ls-remote prefix match" >&2
    fi
    echo "  Use a full 40-char SHA, a tag name, a branch name, or a 7+ char short hash." >&2
    return 1
}

# Resolve HEAD of a repo without needing to know the default branch name.
get_latest_hash() {
    git ls-remote "${1}" HEAD 2>/dev/null | head -1 | cut -f1
}

# --- Staged CI build ----------------------------------------------------
#
# The caller workflow (unified-docker.yml -> unified-docker-backend.yml) builds
# one backend as: builder base -> one artifacts image per upstream project ->
# assemble. Every image is addressed by its content, so anything unchanged is
# skipped: the base by its Dockerfile's hash, a project by its upstream commit
# plus its Dockerfile, its install script, the base tag, and the build args it
# reads. A rerun is idempotent and a failed assemble retries without
# recompiling anything.
#
# Stage images live in ARTIFACT_REPO, a separate GHCR package from the released
# unified images on purpose (a new tag per project per upstream commit would
# bury :unified-<backend> under thousands of tags). The default is fork-aware:
# under CI it derives from GITHUB_REPOSITORY so a fork pushes to its own
# namespace instead of upstream's (which 403s).

ARTIFACT_REPO="${ARTIFACT_REPO:-ghcr.io/${GITHUB_REPOSITORY:-mostlygeek/llama-swap}-build}"
CUDA_VERSION="${CUDA_VERSION:-12.9.1}"

image_exists() {
    docker buildx imagetools inspect "$1" >/dev/null 2>&1
}

# Base tag: base-<backend>.Dockerfile hash + CUDA_VERSION (changing either
# rebuilds the base and, through the base tag, every project on it).
content_base_tag() {
    local h
    h=$( { sha256sum "${SCRIPT_DIR}/base-${BACKEND}.Dockerfile" | cut -d' ' -f1
           printf 'cuda-version=%s\n' "${CUDA_VERSION}"
         } | sha256sum | cut -c1-16 )
    echo "${ARTIFACT_REPO}:base-${BACKEND}-${h}"
}

project_commit() { # $1 = project name -> resolved commit hash
    case "$1" in
        llama)    echo "${LLAMA_HASH}" ;;
        whisper)  echo "${WHISPER_HASH}" ;;
        sd)       echo "${SD_HASH}" ;;
        audio)    echo "${AUDIO_HASH}" ;;
        ik-llama) echo "${IK_LLAMA_HASH}" ;;
        *) echo "ERROR: unknown project '$1' (want llama|whisper|sd|audio|ik-llama)" >&2; return 1 ;;
    esac
}

# Project tag: upstream commit + project Dockerfile + install script +
# base tag + build args the Dockerfile reads.
content_project_tag() { # $1 = project name
    local project="$1" commit h
    commit=$(project_commit "$project") || return 1
    h=$( { sha256sum "${SCRIPT_DIR}/${project}.Dockerfile" \
                        "${SCRIPT_DIR}/install-${project}.sh" 2>/dev/null | cut -d' ' -f1
           printf 'base=%s\ncommit=%s\nffmpeg=%s\n' \
                  "${BASE_TAG}" "${commit}" "${WHISPER_FFMPEG}"
         } | sha256sum | cut -c1-16 )
    echo "${ARTIFACT_REPO}:${BACKEND}-${project}-${h}"
}

run_stage() { # $1 = base | llama | whisper | sd | audio | ik-llama
    local stage="$1" tag
    BASE_TAG=$(content_base_tag)

    if [[ "$stage" == "base" ]]; then
        tag="${BASE_TAG}"
        if image_exists "$tag"; then
            echo "base unchanged, reusing ${tag}" >&2
            return 0
        fi
        echo "building base ${tag}" >&2
        docker buildx build --push \
            --build-arg "CUDA_VERSION=${CUDA_VERSION}" \
            -t "$tag" -f "${SCRIPT_DIR}/base-${BACKEND}.Dockerfile" \
            "${SCRIPT_DIR}"
        return 0
    fi

    case "$stage" in
        llama|whisper|sd|audio|ik-llama) ;;
        *) echo "ERROR: unknown stage '$stage' (want base|llama|whisper|sd|audio|ik-llama)" >&2; exit 1 ;;
    esac
    if [[ "$stage" == "ik-llama" && "$BACKEND" != "cuda" ]]; then
        echo "ERROR: ik-llama is CUDA-only" >&2
        exit 1
    fi

    tag=$(content_project_tag "$stage")
    if image_exists "$tag"; then
        echo "stage ${stage} unchanged, reusing ${tag}" >&2
        return 0
    fi

    local commit build_args
    commit=$(project_commit "$stage")
    build_args=( --build-arg "BUILDER_BASE=${BASE_TAG}"
                 --build-arg "BACKEND=${BACKEND}" )
    case "$stage" in
        llama)   build_args+=( --build-arg "LLAMA_COMMIT_HASH=${commit}" ) ;;
        whisper) build_args+=( --build-arg "WHISPER_COMMIT_HASH=${commit}"
                               --build-arg "WHISPER_FFMPEG=${WHISPER_FFMPEG}" ) ;;
        sd)      build_args+=( --build-arg "SD_COMMIT_HASH=${commit}" ) ;;
        audio)   build_args+=( --build-arg "AUDIO_COMMIT_HASH=${commit}" ) ;;
        ik-llama) build_args+=( --build-arg "IK_LLAMA_COMMIT_HASH=${commit}" ) ;;
    esac
    echo "building stage ${stage} ${tag}" >&2
    docker buildx build --push \
        -t "$tag" -f "${SCRIPT_DIR}/${stage}.Dockerfile" \
        "${build_args[@]}" "${SCRIPT_DIR}"
}

run_assemble() {
    BASE_TAG=$(content_base_tag)
    DOCKER_IMAGE_TAG="${DOCKER_IMAGE_TAG:-llama-swap:unified-${BACKEND}}"

    # config.example.yaml lives at the repo root docs/, outside this build
    # context, so it is passed as a named build context (runtime.Dockerfile
    # copies it via COPY --from=repo-docs).
    local docs_dir="${REPO_ROOT}/docs"
    if [[ ! -f "${docs_dir}/config.example.yaml" ]]; then
        echo "ERROR: ${docs_dir}/config.example.yaml not found" >&2
        exit 1
    fi

    local build_args=(
        --build-arg "BACKEND=${BACKEND}"
        --build-arg "BUILDER_BASE=${BASE_TAG}"
        --build-arg "WHISPER_IMAGE=$(content_project_tag whisper)"
        --build-arg "SD_IMAGE=$(content_project_tag sd)"
        --build-arg "AUDIO_IMAGE=$(content_project_tag audio)"
        --build-arg "LLAMA_IMAGE=$(content_project_tag llama)"
        --build-arg "LS_VERSION=${LS_HASH}"
        --build-arg "LLAMA_COMMIT_HASH=${LLAMA_HASH}"
        --build-arg "WHISPER_COMMIT_HASH=${WHISPER_HASH}"
        --build-arg "SD_COMMIT_HASH=${SD_HASH}"
        --build-arg "AUDIO_COMMIT_HASH=${AUDIO_HASH}"
        --build-arg "IK_LLAMA_COMMIT_HASH=${IK_LLAMA_HASH}"
    )
    if [[ "$BACKEND" == "cuda" ]]; then
        # Vulkan omits this and the Dockerfile falls back to its empty
        # ik-llama-empty stage, so no backend branching is needed there.
        build_args+=( --build-arg "IK_LLAMA_IMAGE=$(content_project_tag ik-llama)" )
    fi

    echo "assembling ${DOCKER_IMAGE_TAG}" >&2
    docker buildx build --load \
        --build-context "repo-docs=${docs_dir}" \
        -t "${DOCKER_IMAGE_TAG}" -f "${SCRIPT_DIR}/runtime.Dockerfile" \
        "${build_args[@]}" "${SCRIPT_DIR}"

    # Rootless variant, same recipe as the local monolithic path below.
    local rootless_tag="${DOCKER_IMAGE_TAG}-rootless"
    docker build -t "${rootless_tag}" - <<EOF
FROM ${DOCKER_IMAGE_TAG}
USER root
RUN groupadd --system --gid 10001 llama-swap && \\
    useradd --system --uid 10001 --gid 10001 \\
      --home /app --shell /sbin/nologin llama-swap && \\
    chown -R 10001:10001 /etc/llama-swap /models
USER 10001
EOF
    echo "assembled ${DOCKER_IMAGE_TAG} and ${rootless_tag}" >&2
}

# In --resolve mode the human-readable progress goes to stderr so stdout
# carries only name=value lines (safe to append to $GITHUB_OUTPUT). This must
# happen before ANY stdout output: even the banner below would corrupt the
# output file (a line of '=' chars parses as an empty variable name).
if [[ "${RESOLVE}" == true ]]; then
    exec 3>&1 1>&2
fi

echo "=========================================="
echo "llama-swap Unified Build (${BACKEND})"
echo "=========================================="
echo ""

# Resolve llama.cpp ref
if [[ -n "${LLAMA_REF:-}" ]]; then
    LLAMA_HASH=$(resolve_ref "${LLAMA_REPO}" "${LLAMA_REF}") || exit 1
    echo "llama.cpp: ${LLAMA_REF} -> ${LLAMA_HASH}"
else
    LLAMA_HASH=$(get_latest_hash "${LLAMA_REPO}")
    if [[ -z "${LLAMA_HASH}" ]]; then
        echo "ERROR: Could not determine latest commit for llama.cpp" >&2
        exit 1
    fi
    echo "llama.cpp: latest HEAD: ${LLAMA_HASH}"
fi

# Resolve whisper.cpp ref
if [[ -n "${WHISPER_REF:-}" ]]; then
    WHISPER_HASH=$(resolve_ref "${WHISPER_REPO}" "${WHISPER_REF}") || exit 1
    echo "whisper.cpp: ${WHISPER_REF} -> ${WHISPER_HASH}"
else
    WHISPER_HASH=$(get_latest_hash "${WHISPER_REPO}")
    if [[ -z "${WHISPER_HASH}" ]]; then
        echo "ERROR: Could not determine latest commit for whisper.cpp" >&2
        exit 1
    fi
    echo "whisper.cpp: latest HEAD: ${WHISPER_HASH}"
fi

# Resolve stable-diffusion.cpp ref
if [[ -n "${SD_REF:-}" ]]; then
    SD_HASH=$(resolve_ref "${SD_REPO}" "${SD_REF}") || exit 1
    echo "stable-diffusion.cpp: ${SD_REF} -> ${SD_HASH}"
else
    SD_HASH=$(get_latest_hash "${SD_REPO}")
    if [[ -z "${SD_HASH}" ]]; then
        echo "ERROR: Could not determine latest commit for stable-diffusion.cpp" >&2
        exit 1
    fi
    echo "stable-diffusion.cpp: latest HEAD: ${SD_HASH}"
fi

# Resolve audio.cpp ref
if [[ -n "${AUDIO_REF:-}" ]]; then
    AUDIO_HASH=$(resolve_ref "${AUDIO_REPO}" "${AUDIO_REF}") || exit 1
    echo "audio.cpp: ${AUDIO_REF} -> ${AUDIO_HASH}"
else
    AUDIO_HASH=$(get_latest_hash "${AUDIO_REPO}")
    if [[ -z "${AUDIO_HASH}" ]]; then
        echo "ERROR: Could not determine latest commit for audio.cpp" >&2
        exit 1
    fi
    echo "audio.cpp: latest HEAD: ${AUDIO_HASH}"
fi

# Resolve ik_llama.cpp ref (CUDA only)
if [[ "$BACKEND" == "cuda" ]]; then
    if [[ -n "${IK_LLAMA_REF:-}" ]]; then
        IK_LLAMA_HASH=$(resolve_ref "${IK_LLAMA_REPO}" "${IK_LLAMA_REF}") || exit 1
        echo "ik_llama.cpp: ${IK_LLAMA_REF} -> ${IK_LLAMA_HASH}"
    else
        IK_LLAMA_HASH=$(get_latest_hash "${IK_LLAMA_REPO}")
        if [[ -z "${IK_LLAMA_HASH}" ]]; then
            echo "ERROR: Could not determine latest commit for ik_llama.cpp" >&2
            exit 1
        fi
        echo "ik_llama.cpp: latest HEAD: ${IK_LLAMA_HASH}"
    fi
else
    IK_LLAMA_HASH="n/a"
    echo "ik_llama.cpp: skipped (vulkan build)"
fi

# Resolve llama-swap ref
if [[ -n "${LS_VERSION:-}" ]]; then
    LS_HASH=$(resolve_ref "${LLAMA_SWAP_REPO}" "${LS_VERSION}") || exit 1
    echo "llama-swap: ${LS_VERSION} -> ${LS_HASH}"
else
    LS_HASH=$(get_latest_hash "${LLAMA_SWAP_REPO}")
    if [[ -z "${LS_HASH}" ]]; then
        echo "ERROR: Could not determine latest commit for llama-swap" >&2
        exit 1
    fi
    echo "llama-swap: latest HEAD: ${LS_HASH}"
fi

# --resolve: restore stdout and emit only name=value lines, then exit before
# any Docker invocation.
if [[ "${RESOLVE}" == true ]]; then
    exec 1>&3 3>&-
    echo "llama_hash=${LLAMA_HASH}"
    echo "whisper_hash=${WHISPER_HASH}"
    echo "sd_hash=${SD_HASH}"
    echo "audio_hash=${AUDIO_HASH}"
    echo "ik_llama_hash=${IK_LLAMA_HASH}"
    echo "ls_hash=${LS_HASH}"
    exit 0
fi

# Staged CI modes: build one content-addressed stage, or assemble the unified
# image from the published stages. Nothing is compiled in --assemble.
if [[ -n "${STAGE}" ]]; then
    run_stage "${STAGE}"
    exit 0
fi

if [[ "${ASSEMBLE}" == true ]]; then
    run_assemble
    exit 0
fi

echo ""
echo "=========================================="
echo "Starting Docker build..."
echo "=========================================="
echo ""

BUILD_ARGS=(
    --build-arg "BACKEND=${BACKEND}"
    --build-arg "LLAMA_COMMIT_HASH=${LLAMA_HASH}"
    --build-arg "WHISPER_COMMIT_HASH=${WHISPER_HASH}"
    --build-arg "SD_COMMIT_HASH=${SD_HASH}"
    --build-arg "IK_LLAMA_COMMIT_HASH=${IK_LLAMA_HASH}"
    --build-arg "LS_VERSION=${LS_HASH}"
    --build-arg "WHISPER_FFMPEG=${WHISPER_FFMPEG}"
    -t "${DOCKER_IMAGE_TAG}"
    -f "${SCRIPT_DIR}/Dockerfile"
)

if [[ "$NO_CACHE" == true ]]; then
    BUILD_ARGS+=(--no-cache)
    echo "Note: Building without cache"
elif [[ "${GITHUB_ACTIONS:-}" == "true" && "${ACT:-}" != "true" ]]; then
    # Derive the cache repo from the image tag so forked CI pushes cache to
    # the fork's own ghcr.io namespace instead of upstream's (which 403s).
    CACHE_REF="${DOCKER_IMAGE_TAG%:*}:unified-${BACKEND}-cache"
    BUILD_ARGS+=(
        --cache-from "type=registry,ref=${CACHE_REF}"
        --cache-to "type=registry,ref=${CACHE_REF},mode=max"
    )
    echo "Note: Using registry cache (${CACHE_REF})"
fi

DOCKER_BUILDKIT=1 docker buildx build --load "${BUILD_ARGS[@]}" "${SCRIPT_DIR}"

echo ""
echo "=========================================="
echo "Verifying build artifacts..."
echo "=========================================="
echo ""

EXPECTED_BINARIES=(llama-server llama-cli whisper-server whisper-cli sd-server sd-cli llama-swap)
if [[ "$BACKEND" == "cuda" ]]; then
    EXPECTED_BINARIES+=(ik-llama-server)
fi

MISSING_BINARIES=()
for binary in "${EXPECTED_BINARIES[@]}"; do
    if ! docker run --rm --entrypoint which "${DOCKER_IMAGE_TAG}" "${binary}" >/dev/null 2>&1; then
        MISSING_BINARIES+=("${binary}")
    fi
done

if [[ ${#MISSING_BINARIES[@]} -gt 0 ]]; then
    echo "ERROR: Build succeeded but the following binaries are missing:"
    for binary in "${MISSING_BINARIES[@]}"; do
        echo "  - ${binary}"
    done
    echo ""
    echo "Try running with --no-cache flag:"
    echo "  ./build-image.sh --${BACKEND} --no-cache"
    exit 1
fi

VERIFIED_LIST="llama-server, llama-cli, whisper-server, whisper-cli, sd-server, sd-cli, llama-swap"
if [[ "$BACKEND" == "cuda" ]]; then
    VERIFIED_LIST="${VERIFIED_LIST}, ik-llama-server"
fi
echo "All expected binaries verified: ${VERIFIED_LIST}"

echo ""
echo "=========================================="
echo "Building rootless image..."
echo "=========================================="
echo ""

ROOTLESS_TAG="${DOCKER_IMAGE_TAG}-rootless"
# NOTE: plain `docker build` (docker driver) intentionally used here instead of
# `docker buildx build` with the docker-container driver: the container driver
# cannot see images in the local daemon, so `FROM ${DOCKER_IMAGE_TAG}` would
# try to pull the tag from the registry and fail with "not found" (the push
# step only runs after this script). The docker driver resolves the just-built
# local image fine.
docker build -t "${ROOTLESS_TAG}" - <<EOF
FROM ${DOCKER_IMAGE_TAG}
USER root
RUN groupadd --system --gid 10001 llama-swap && \\
    useradd --system --uid 10001 --gid 10001 \\
      --home /app --shell /sbin/nologin llama-swap && \\
    chown -R 10001:10001 /etc/llama-swap /models
USER 10001
EOF

echo "Rootless image built: ${ROOTLESS_TAG}"

echo ""
echo "=========================================="
echo "Build complete!"
echo "=========================================="
echo ""
echo "Image tags:"
echo "  ${DOCKER_IMAGE_TAG}"
echo "  ${ROOTLESS_TAG}"
echo ""
echo "Built with:"
echo "  llama.cpp:            ${LLAMA_HASH}"
echo "  whisper.cpp:          ${WHISPER_HASH}"
echo "  stable-diffusion.cpp: ${SD_HASH}"
if [[ "$BACKEND" == "cuda" ]]; then
    echo "  ik_llama.cpp:         ${IK_LLAMA_HASH}"
fi
echo "  llama-swap:           $(docker run --rm --entrypoint cat "${DOCKER_IMAGE_TAG}" /versions.txt | grep llama-swap | cut -d' ' -f2-)"
echo ""
if [[ "$BACKEND" == "vulkan" ]]; then
    echo "Run with:"
    echo "  docker run -it --rm --device /dev/dri:/dev/dri ${DOCKER_IMAGE_TAG}"
    echo ""
    echo "Note: For AMD GPUs, you may also need:"
    echo "  docker run -it --rm --device /dev/dri:/dev/dri --group-add video ${DOCKER_IMAGE_TAG}"
else
    echo "Run with:"
    echo "  docker run -it --rm --gpus all ${DOCKER_IMAGE_TAG}"
fi
