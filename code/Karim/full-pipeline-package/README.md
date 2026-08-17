# Street Sign Damage Detection -- Full Pipeline Package

This package contains the entire street-sign-damage pipeline: SIMS
querying, Cyclomedia panorama fetching (including multi-angle capture),
the offline annotation tool, the Chrome capture extension, physical-model
training, and automatic-mode inference. It's broader in scope than the
separate extension-only stakeholder package or the narrower
extension+backend `partner-package` -- this one is for someone who wants
to run the whole thing themselves.

## What's included

- `scripts/` -- the full pipeline (see `PIPELINE_SCRIPT_NAMES` in
  `build_full_pipeline_package.py` for the exact list), plus each
  script's own test, so you can verify your setup with `pytest`.
- `annotation_tool/` -- the offline box-drawing/tagging tool.
- `extension/` -- the Chrome capture extension (live Google Maps /
  Cyclomedia Street Smart capture, with ML-assisted damage suggestions).
- `yolo26n.pt`, plus the currently-trained physical-damage-model weights
  and the spatial-detection sanity-check weights -- needed for automatic
  mode and the model server to run at all.
- `yolo/data_physical.yaml` and `yolo/data_physical_from_annotations.yaml`
  -- the dataset configs `train_physical_model.py` and
  `prepare_physical_dataset_from_annotations.py` need, rewritten to point
  at this package's own `data/` instead of the original developer's machine.
- `start_pipeline_shell.bat`, `start_model_server.bat`,
  `start_tight_crop_server.bat`, `annotation_tool/start_annotation_server.bat`
  -- rewritten to use this package's own virtual environment (see Setup),
  not the original developer's machine-specific Python path.
- `requirements.txt`, `.env.example`, `setup.bat`.

## What's NOT included

- **No real credentials.** `.env.example` lists every environment
  variable the included scripts actually read (Cyclomedia access, plus
  optional SIMS/NYC Open Data rate-limit tokens); you supply your own
  values.
- **No bulk data.** This package on its own has no fetched panoramas,
  annotations, or SIMS data -- see "Adding the data package" below.
- This project's own internal planning/spec documents, git history, and
  the older versioned extension-only zips are not included.

## Setup

1. Have Python 3.10+ available -- either already on your PATH, or
   installed somewhere else on this computer (e.g. Anaconda/Miniconda).
   `setup.bat` checks PATH first and, if that fails, asks for the full
   path to an existing `python.exe` before offering to open the
   python.org download page.
2. Double-click `setup.bat` (or run it from a terminal). This creates a
   `venv/` folder, installs everything in `requirements.txt` into it, and
   creates `.env` from `.env.example` if one doesn't already exist.
3. Edit `.env` with your own Cyclomedia credentials (`CYCLOMEDIA_USERNAME`,
   `CYCLOMEDIA_PASSWORD`, `CYCLOMEDIA_API_KEY`). You only need these to
   fetch *new* panoramas or query SIMS live -- if you're only using data
   from the companion data package, you can skip this for now.

## Adding the data package

If you have the companion `full-pipeline-data` folder, copy its `data/`
subfolder into this package's own root, right alongside `scripts/` and
`annotation_tool/`. Every script already resolves paths like
`../data/cyclomedia_panoramas/` relative to `scripts/`, so nothing else
needs to change -- it just works once `data/` is sitting there.

## Running things

- **The full guided pipeline** (select a Community Board, pull SIMS
  signs + Cyclomedia panoramas, then choose manual annotation or
  automatic inference): double-click `start_pipeline_shell.bat`.
- **Manual annotation mode** needs two servers running alongside it:
  `start_tight_crop_server.bat` and `annotation_tool/start_annotation_server.bat`
  (the pipeline shell launches both of these for you automatically when
  you choose manual mode).
- **The physical-damage-model server** (used by both the extension's
  live suggestions and the annotation tool's tight-crop suggestions):
  `start_model_server.bat`.
- **The Chrome extension**: load `extension/` as an unpacked extension
  via `chrome://extensions` (Developer mode -> Load unpacked).

## Verifying your setup

From `scripts/`, with the venv activated:
```
..\venv\Scripts\pytest
```
All tests should pass. If any fail, something about your environment
(missing dependency, wrong Python version) needs attention before relying
on the pipeline.
