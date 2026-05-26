#!/usr/bin/env sh
# Map git tags v0.111.1.bright0 -> PyPI/setuptools-scm 0.111.1.post0
# (PyPI rejects local versions like +bright0; .bright0 is not valid PEP 440 public.)
#
# Usage:
#   eval "$(./scripts/scm_pep440.sh /path/to/bright-vision-core)"
#   eval "$(./scripts/scm_pep440.sh /path/to/repo v0.111.1.bright4)"  # explicit tag (required when multiple .brightN tags share a commit)

repo="${1:-.}"
explicit_tag="${2:-}"

if [ -n "$explicit_tag" ]; then
  desc="$explicit_tag"
else
  desc="$(git -C "$repo" describe --tags --long 2>/dev/null || true)"
fi
[ -n "$desc" ] || exit 0

pep="$(printf '%s' "$desc" | sed -E 's/^v?([0-9]+\.[0-9]+\.[0-9]+)\.bright([0-9]+).*/\1.post\2/')"
case "$pep" in
  *.post*)
    printf "export SETUPTOOLS_SCM_PRETEND_VERSION='%s'\n" "$pep"
    ;;
esac
