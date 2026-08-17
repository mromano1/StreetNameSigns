# Street Sign Capture Tool

A browser extension for manually collecting labeled sign photos from Street
View, matched against real NYC DOT SIMS sign records. Built as an interim
data-collection path while Cyclomedia API access is pending.

Start here: **[QUICKSTART.md](QUICKSTART.md)**

Also in this folder:
- `full-pipeline-package/` - the full runnable pipeline (SIMS query, Cyclomedia
  panorama fetch, annotation tool, this extension, physical-model training,
  automatic-mode inference) as a standalone downloadable package -- see its
  own README.md for setup
- `street-sign-capture-extension/` - the extension itself
- `BEST_PRACTICES.md` - draft capture guidelines (angle, framing, damage
  categories)
- `scripts/` - standalone scripts to pull your own SIMS data for a given ZIP
  code (no Jupyter or AI assistant required)

**Status:** working prototype, not finished. See the "What this does NOT do
yet" section in QUICKSTART.md before assuming it covers something it doesn't.
