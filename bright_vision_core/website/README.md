# BrightVision Core site (Jekyll)

Marketing and docs for **BrightVision Core** — separate from upstream **`cecli/website/`** (left untouched).

| | |
|--|--|
| **Source** | Copied from legacy `bright_vision_core/website`, rebranded Cecli → Bright + Cecli lineage |
| **Ruby** | **3.3+** (GitHub Actions; `console` 1.35+ needs ≥ 3.3) |
| **Local preview** | `bundle install && bundle exec jekyll serve` (from this directory) |
| **Deploy** | GitHub Pages on `bright-vision-core` repo → [bright-vision-core.digitaldefiance.org](https://bright-vision-core.digitaldefiance.org) |
| **Rebrand** | `scripts/rebrand-website.py` then `scripts/rebrand-website-pass2.py` |

Homepage: `index.html` (standalone layout). Docs: `docs/` (Just the Docs theme).
