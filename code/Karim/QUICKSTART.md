# Street Sign Capture Tool, quick start

**Status: not finished.** This is a working prototype for manually collecting
labeled sign photos, not a polished tool. Expect rough edges. If something
breaks, that's expected at this stage, not user error, flag it to the project team.

## What this is

A Chrome extension that lets you browse Google Street View by hand, click a
button to grab a screenshot, drag a box around a damaged sign, and save the
cropped image plus structured metadata (which street, which corner, damage
type, intersection type) tied back to the real NYC DOT sign inventory record
for that corner.

It exists because automating Street View collection (scripted browser tools,
the paid Static API) hits real limits: Google blocks automated/headless
browser access to real imagery for most locations, and the Static API caps
out at 640x640 resolution regardless of what you ask for. So this tool is
built around a human doing the browsing and clicking, it only automates the
capture, cropping, and labeling steps.

## What it does NOT do yet

- No trained model, no damage detection. This only collects and labels
  training images.
- No SIMS-ready report export, no interactive webview.
- Output format does not currently match `data/annotations.csv` in this repo.
  It produces its own CSV (see "What you get" below). Reconciling the two
  formats is still an open task, don't assume they're interchangeable yet.
- No formal best-practices handbook exists yet either, see the draft in
  `BEST_PRACTICES.md` next to this file, treat it as a living draft, not a
  finished spec.

## 1. Get your own SIMS sign data

You need a lookup file mapping real sign records to street corners for
whatever ZIP code you're working in. This does NOT require Cyclomedia access,
it queries NYC's public Open Data.

Install the Python dependencies once:

```bash
pip install pandas pgeocode pyproj requests
```

Then, from `code/Karim/scripts/`:

```bash
python 01_query_sims_by_zip.py 10002
python 02_generate_signs_data.py 10002
```

(Replace `10002` with your actual ZIP code.) The first script downloads and
filters the sign inventory for that ZIP into `signs_zip_10002.csv`. The second
converts it into `signs_data.json`, the format the extension actually reads.

Copy the resulting `signs_data.json` into `street-sign-capture-extension/`,
replacing the example one already there (that one is scoped to ZIP 10001, it
won't have your corners in it).

## 2. Load the extension in Chrome

1. Go to `chrome://extensions`
2. Turn on **Developer mode** (top right)
3. Click **Load unpacked**, select the `street-sign-capture-extension/` folder
4. Whenever you edit any extension file, click the reload icon (circular
   arrow) on its card here, Chrome does not auto-reload unpacked extensions

## 3. One-time Chrome setting, so files save into this repo

Chrome's downloads API can only save inside your browser's default download
folder, there's no way for an extension to write anywhere else.

1. `chrome://settings/downloads`
2. Set the default location to somewhere inside your local clone of this
   repo, e.g. `data/streetview_captures/`
3. Captures will land in `.../manual_capture/` under whatever folder you
   picked, plus a CSV manifest when you export one from the toolbar popup

## 4. Using it

1. Open Google Maps, navigate to Street View at an intersection with signs
2. Click the blue **Capture Sign** button (bottom right of the page)
3. Drag a box around the sign
4. A panel appears prefilled with the nearest match from your SIMS data,
   confirm or correct: which street name is on the sign, which corner,
   intersection type, damage category
5. Click Save
6. Click the extension's toolbar icon any time to see how many you've
   captured this session and export a CSV manifest

Read `BEST_PRACTICES.md` before you get going on framing/angle/zoom, it
covers real gotchas (like the tight-crop rule having exceptions for
wrong-direction, hanging, and bent signs specifically).

## Known rough edges

- The extension needs the `<all_urls>` permission for the capture button to
  work at all, this was a real Chrome API limitation discovered during
  development, not an oversight, don't try to narrow it.
- If you see "Capture failed" errors, reload the extension first, that fixes
  it 90% of the time.
- See `street-sign-capture-extension/SETUP_NOTES.md` for the deeper technical
  notes (written with more assumed context, useful if you're going to modify
  the code, not required just to use it).

## Questions / problems

Raise it with the project team directly rather than guessing, especially
before changing the extension's data schema or damage categories, there's an
open question about reconciling this tool's output with
`data/annotations.csv` that needs a team decision, not a unilateral one.
