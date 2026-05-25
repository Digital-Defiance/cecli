#!/usr/bin/env bash
# Pin Bright Vision parent app to a released bright-vision-core version on PyPI and
# install into the parent .venv (not bright-vision-core/.venv).
#
# Usage:
#   ./scripts/sync_bright_vision.sh 0.100.1.dev0
#   ./scripts/sync_bright_vision.sh v0.100.1.dev0 --commit
#   BRIGHT_VISION_ROOT=/path/to/bright-vision ./scripts/sync_bright_vision.sh v0.100.1.dev0

set -euo pipefail

CORE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSUME_YES=0
DO_COMMIT=0
SKIP_PIP=0
VERSION_ARG=""

usage() {
  echo "Usage: $0 <version> [--commit] [--yes] [--skip-pip]" >&2
  echo "  version     PEP 440 or tag, e.g. 0.100.1.dev0 or v0.100.1.dev0" >&2
  echo "  --commit    commit requirements-core.txt + submodule pointer in parent app" >&2
  echo "  BRIGHT_VISION_ROOT  override parent app path (default: repo containing submodule)" >&2
  exit 1
}

die() {
  echo "error: $*" >&2
  exit 1
}

confirm() {
  local prompt="$1"
  if (( ASSUME_YES )); then
    return 0
  fi
  local ans
  read -r -p "${prompt} [y/N] " ans
  ans="$(printf '%s' "$ans" | tr '[:upper:]' '[:lower:]')"
  [[ "$ans" == "y" || "$ans" == "yes" ]]
}

resolve_vision_root() {
  if [[ -n "${BRIGHT_VISION_ROOT:-}" ]]; then
    echo "$(cd "$BRIGHT_VISION_ROOT" && pwd)"
    return
  fi
  if [[ -n "${AIDER_VISION_ROOT:-}" ]]; then
    echo "$(cd "$AIDER_VISION_ROOT" && pwd)"
    return
  fi
  local parent
  parent="$(cd "${CORE_ROOT}/.." && pwd)"
  if [[ -f "${parent}/.gitmodules" ]] && [[ -d "${parent}/bright-vision-core" ]]; then
    echo "$parent"
    return
  fi
  die "could not find Bright Vision parent (set BRIGHT_VISION_ROOT)"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --commit) DO_COMMIT=1; shift ;;
    --yes) ASSUME_YES=1; shift ;;
    --skip-pip) SKIP_PIP=1; shift ;;
    -h|--help) usage ;;
    -*)
      die "unknown option: $1"
      ;;
    *)
      [[ -z "$VERSION_ARG" ]] || die "unexpected argument: $1"
      VERSION_ARG="$1"
      shift
      ;;
  esac
done

[[ -n "$VERSION_ARG" ]] || usage

VERSION_TAG="$VERSION_ARG"
PEP440_VERSION="${VERSION_TAG#v}"
if [[ ! "$PEP440_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.]+)?$ ]]; then
  die "invalid version: ${VERSION_ARG}"
fi
if [[ "$VERSION_TAG" != v* ]]; then
  VERSION_TAG="v${PEP440_VERSION}"
fi

VISION_ROOT="$(resolve_vision_root)"
REQ_FILE="${VISION_ROOT}/requirements-core.txt"
SUBMODULE="${VISION_ROOT}/bright-vision-core"
VENV="${VISION_ROOT}/.venv"

echo "Parent app: ${VISION_ROOT}"
echo "Pin: bright-vision-core==${PEP440_VERSION}"

cat >"$REQ_FILE" <<EOF
# Pinned PyPI release of the engine (updated by bright-vision-core/scripts/sync_bright_vision.sh).
# Dev default: editable submodule via \`source activate.sh\` in Bright Vision.
# After a core release: cd bright-vision-core && ./build.sh ${VERSION_TAG} --sync-vision
bright-vision-core==${PEP440_VERSION}
EOF
echo "Wrote ${REQ_FILE}"

if [[ -d "$SUBMODULE/.git" ]]; then
  echo "Checking out submodule at tag ${VERSION_TAG}..."
  git -C "$SUBMODULE" fetch origin tag "$VERSION_TAG" 2>/dev/null || true
  if git -C "$SUBMODULE" rev-parse "$VERSION_TAG" >/dev/null 2>&1; then
    git -C "$SUBMODULE" checkout "$VERSION_TAG"
  else
    echo "warning: tag ${VERSION_TAG} not found in submodule; requirements pin still updated" >&2
  fi
fi

if (( SKIP_PIP )); then
  echo "Skipping pip install (--skip-pip)."
else
  PYTHON="${VISION_PYTHON:-python3}"
  if [[ ! -d "$VENV" ]]; then
    echo "Creating ${VENV}..."
    "$PYTHON" -m venv "$VENV"
  fi
  # shellcheck disable=SC1091
  source "${VENV}/bin/activate"
  echo "Installing into Bright Vision .venv (not core/.venv)..."
  python -m pip install -q -U pip "uvicorn[standard]"
  python -m pip install -q -U -r "$REQ_FILE"
  python -c "
import bright_vision_core as bvc
from cecli import __version__ as cecli_version
print('bright_vision_core', getattr(bvc, '__version__', '?'), 'at', bvc.__file__)
print('cecli', cecli_version)
"
  command -v bright-vision-core-serve >/dev/null && echo "bright-vision-core-serve: $(command -v bright-vision-core-serve)"
  deactivate 2>/dev/null || true
fi

if (( DO_COMMIT )); then
  if ! git -C "$VISION_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    die "parent app is not a git repo; cannot --commit"
  fi
  MSG="chore: pin bright-vision-core==${PEP440_VERSION}"
  git -C "$VISION_ROOT" add requirements-core.txt
  if [[ -d "$SUBMODULE/.git" ]]; then
    git -C "$VISION_ROOT" add bright-vision-core
  fi
  if git -C "$VISION_ROOT" diff --cached --quiet; then
    echo "Nothing to commit in parent app."
  elif (( ASSUME_YES )) || confirm "Commit in parent app: \"${MSG}\"?"; then
    git -C "$VISION_ROOT" commit -m "$MSG"
    echo "Committed in parent app."
  else
    echo "Skipped commit; changes left staged/unstaged in parent app."
  fi
fi

echo "Done. Use: cd ${VISION_ROOT} && source activate.sh  (editable) or source .venv/bin/activate after PyPI install."
