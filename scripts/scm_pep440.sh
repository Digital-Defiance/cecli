#!/usr/bin/env sh
# Map git tags like v0.111.1.bright0 -> PEP 440 0.111.1+bright0 for setuptools-scm.
# Usage: eval "$(./scripts/scm_pep440.sh /path/to/bright-vision-core)"

repo="${1:-.}"
desc="$(git -C "$repo" describe --tags --long 2>/dev/null || true)"
[ -n "$desc" ] || exit 0

pep="$(printf '%s' "$desc" | sed -E 's/^v?([0-9]+\.[0-9]+\.[0-9]+)\.bright([0-9]+).*/\1+bright\2/')"
case "$pep" in
  *+bright*)
    printf "export SETUPTOOLS_SCM_PRETEND_VERSION='%s'\n" "$pep"
    ;;
esac
