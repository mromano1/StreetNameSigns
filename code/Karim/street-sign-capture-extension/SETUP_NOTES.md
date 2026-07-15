---
name: street-sign-capture-extension-setup
description: Context for Claude Code to re-set up the Street Sign Capture Chrome extension on a new machine
---

# Street Sign Capture extension, setup notes for Claude

This is a Chrome extension (Manifest V3) for manually browsing Street View,
clicking "Capture Sign," dragging a box around a damaged sign, and saving the
cropped image plus metadata (matched against SIMS sign records) for later
YOLO training / SIMS reporting. Built because Google blocks headless/automated
browser access to real Street View imagery (confirmed during development:
bot detection degrades coverage for non-famous locations when driven by
Playwright), so this is designed for a **human** to drive the browser
manually; the extension only automates capture and labeling.

## How to load it (do this first)

1. Open `chrome://extensions`
2. Enable **Developer mode** (top right toggle)
3. Click **Load unpacked**, select this folder
4. **After any edit to these files, you must click the reload icon (⟳) on the
   extension's card.** Chrome does not hot-reload unpacked extensions.

## One-time Chrome settings (so files land inside the project, not system Downloads)

Chrome's `downloads` API can only save inside the browser's default download
directory, no extension can write to an arbitrary path. So:

1. `chrome://settings/downloads`
2. Set the default location to the project's `ML Project/data/raw_images/zip_10001/`
   folder (adjust path per machine/zip code)
3. Captures land in `.../zip_10001/manual_capture/<timestamp>_<street>.jpg`, and the
   popup's "Export CSV" button lands a manifest in the same subfolder.

## Non-obvious bugs already hit and fixed, don't reintroduce these

- **`host_permissions` must be `"<all_urls>"`.** A scoped permission like
  `"https://www.google.com/maps/*"` looks like it should be enough for
  `chrome.tabs.captureVisibleTab`, and Chrome will happily load the extension with it,
  but the API call fails at runtime with `"Either the '<all_urls>' or 'activeTab'
  permission is required."` This is because `captureVisibleTab` specifically only
  accepts `<all_urls>` or `activeTab`. `activeTab` doesn't work either, since it only
  activates on a *toolbar action* click, not a content-script-injected button (which is
  what "Capture Sign" is). Confirmed via repeated live testing, don't "fix" this back
  to a scoped permission, it will silently break capture again.
- **Don't add `web_accessible_resources` for `signs_data.json`.** It's not needed.
  The content script asks the background service worker for the data via
  `chrome.runtime.sendMessage({type: 'get_signs_data'})`, and the service worker reads
  the bundled JSON directly (service workers always have privileged access to their
  own extension's files, no cross-origin exposure needed). Adding a
  `web_accessible_resources` entry for this earlier caused a
  `"failed to load extension: invalid value for web accessible resource"` error and
  broke the whole extension load. Just leave this out.
- The red selection-box outline used to bleed into the saved crop (the stroke was
  painted on the same canvas the crop was cut from). Fixed in `content.js` by
  repainting the clean screenshot onto the canvas immediately before cropping. If you
  ever refactor the drag-select code, keep that repaint step.
- **CSS specificity gotcha**: a pre-existing rule `#ssc-panel button { border: none }`
  (ID selector) silently overrides class-based button styling like `.ssc-btn-group
  button { border: 2px solid ... }` no matter what order they're declared in. If you
  ever restyle the panel buttons and the changes don't seem to apply, this is why.
  Scope the new rule as `#ssc-panel .ssc-btn-group button` to out-specificity it (this
  is what `content.css` already does; don't remove that prefix).

## `sign_location` code meanings (confirmed against an official NYC DOT data dictionary)

`Data_Dictionary-ParkingRegulationLocationsandSigns.xlsx` (project root) documents the
`sign_location` field for a sibling SIMS dataset (note: that dataset explicitly
excludes street name signs, so treat this as strong-but-not-100%-certain evidence for
the actual Street Sign Work Orders data, not a guaranteed exact match). Per that
dictionary, `sign_location` distinguishes real **corner** placements from
non-corner placements:

- Corners (map to a compass direction): `N/E C` = Northeast Corner, `N/W C`, `S/E C`,
  `S/W C` (diagonal), and `N C`/`N CURB`, `E C`/`E CURB`, `S C`/`S CURB`, `W C`/`W CURB`
  (single-cardinal corner, some intersections have a corner best described by one
  direction, not a diagonal, e.g. T-intersections).
- NOT corners (median/mall/apex/island/offset-from-side, don't map these to a
  compass direction): `CML` (Center Mall), `MALL`/`MAL` (Mall), `MEDIAN`/`MED`
  (Median), `ISL` (Island), `APEX`/`APX`/`APEXI` (Apex of Intersection), and compound
  codes like `N WSD` ("north of the intersection, on the west side") / `E SSD`
  ("east of the intersection, on the south side") which describe a sign offset along
  a side, not sitting at a corner at all. `CEN MED` (center median) and `*NOTE` (a
  data annotation) also aren't corners.

`compassFromSignLocation()` in `content.js` implements exactly this split, verified
against every real distinct `sign_location` value in `signs_zip_10001.csv` (26 unique
values, all classify as expected: 4 diagonal + 4 single-cardinal corners map to a
direction, the other 18 correctly fall through to unclassified/"other"). If you
regenerate `signs_data.json` for a new zip code and something looks off in the corner
picker, re-run that same value_counts check against the new CSV before assuming the
regex is wrong, it might be a genuinely new code format not in this list yet.

## Panel fields (as of the current build)

The confirmation panel has four **required** button-group answers (street name,
intersection type, corner, damage category) plus optional notes. "Required" is
enforced in the Save click handler in `content.js`, it blocks the save, shows a red
message in `#ssc-validation-error`, and outlines the incomplete `.ssc-btn-group`
elements in red. Corner picker also has a manual override: a "type a heading in
degrees" input that maps any 0-359 value to NE/SE/SW/NW via a pre-built 2-degree
resolution lookup table (`DEGREE_TABLE`/`cornerFromTypedDegree`), for when the
auto-guessed buttons (derived from `loc.heading` in the URL) don't match what's
actually in view. Street name and corner also have plain write-in text boxes as a
further fallback. If you add another required category, follow the same pattern:
track a `selectedX` variable, add it to the `missing` array check in the save
handler, and add its field to the `record` object.

## Files

- `manifest.json`: MV3 manifest. `host_permissions: ["<all_urls>"]`,
  `content_scripts` scoped to `https://www.google.com/maps/*` only (that's what
  controls where the floating button appears, unrelated to the host_permissions
  requirement above).
- `background.js`: service worker. Handles `capture` (screenshot), `save` (download +
  metadata to `chrome.storage.local`), and `get_signs_data` (serves the bundled JSON).
- `content.js`: injected on Google Maps. Floating capture button, drag-to-crop
  overlay, the Manhattan-grid compass HUD (grid runs about 29 degrees east of true
  north, see `MANHATTAN_GRID_OFFSET`), nearest-corner SIMS matching, and the
  confirmation panel (corner picker, sign-text picker, damage category buttons).
- `content.css`: styling for all of the above.
- `popup.html` / `popup.js`: toolbar popup showing session capture count, CSV export,
  and a clear-all button.
- `signs_data.json`: pre-built lookup table of unique sign corners for **zip 10001
  only**, generated from `ML Project/data/processed/signs_zip_10001.csv`. Structure:
  `{zip, corners: [{corner_id, on_street, from_street, latitude, longitude, signs: [{order_number, sign_code, sign_location, support}]}]}`.
  Corners are deduped by rounding lat/lon to 7 decimals; `signs` holds every raw SIMS
  order record at that exact corner (a corner often has multiple, since multiple sign
  codes/supports/mount types get installed at one intersection corner).

## To regenerate `signs_data.json` for a different zip code

Run the sign query notebook (`ML Project/notebooks/01_sign_query_by_zipcode.ipynb`)
for the target ZIP first to produce `data/processed/signs_zip_{ZIP}.csv`, then:

```python
import pandas as pd, json

df = pd.read_csv(f'data/processed/signs_zip_{ZIP}.csv').dropna(subset=['latitude', 'longitude'])
df['lat_r'] = df['latitude'].round(7)
df['lon_r'] = df['longitude'].round(7)

corners = []
for i, ((lat_r, lon_r), group) in enumerate(df.groupby(['lat_r', 'lon_r'])):
    signs = [
        {'order_number': r.order_number, 'sign_code': r.sign_code,
         'sign_location': r.sign_location, 'support': r.support}
        for r in group.itertuples()
    ]
    corners.append({
        'corner_id': f'{ZIP}_{i:03d}',
        'on_street': group.iloc[0]['on_street'],
        'from_street': group.iloc[0]['from_street'],
        'latitude': float(group.iloc[0]['latitude']),
        'longitude': float(group.iloc[0]['longitude']),
        'signs': signs,
    })

with open('extension/signs_data.json', 'w') as f:
    json.dump({'zip': ZIP, 'corners': corners}, f, indent=0)
```

This overwrites `signs_data.json` for a single zip. Multi-zip support would need this
to become a dict keyed by zip, with a way to pick the active zip in the popup, not
built yet, not needed yet.

## Current capture route

Work is in progress through 6th Avenue in zip 10001, north to south, tracked in
`ML Project/data/processed/capture_route_zip10001.csv` (51 corners, with
`streetview_link` per row for direct clicking). As of this note, progress is around
W 30th St (stop 33 of 51). Ask for current progress rather than assuming the CSV
reflects the true state, it's a static route list, not a live tracker. Full street
inventory for zip 10001 (628 corners, 47 street names) is in
`ML Project/data/processed/signs_zip_10001.csv` for planning a route on a different
avenue next (9th, 8th, and 7th Ave are the next-largest after 6th Ave).

Also flagged but unresolved: about 15% of corners in zip 10001 (94 of 628) have signs
coded with an `HD` suffix on `sign_code` (historic district, brown signs, not standard
green), concentrated in the West Village. There's no `color` field in the SIMS data at
all; `HD` in `sign_code` is the only proxy. The damage taxonomy (white-border,
all-caps, etc.) was written assuming standard green signs, so whether or how to apply
it to brown historic signs is an open question to raise with the DOT contacts, not
something resolved in code.

## Testing approach (for Claude, if changes are needed)

Real Google Maps Street View can't be reliably driven by Playwright (bot detection),
so functional testing was done against a local `http.server` test page with a
temporarily widened manifest copy (`host_permissions` and `content_scripts.matches`
including `http://localhost/*`) in a scratch directory. Never commit that widened
manifest back into this real extension folder. The production manifest here should
only ever have `https://www.google.com/maps/*` in `content_scripts.matches`.
