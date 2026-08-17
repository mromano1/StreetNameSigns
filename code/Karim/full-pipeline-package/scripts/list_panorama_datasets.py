"""
Scans data/cyclomedia_panoramas/ for fetch_manifest.json files (written by
fetch_cyclomedia_panoramas.py, one per pulled dataset/neighborhood
collection -- the root one plus any --output-dir subfolder like demo_cb301/)
and writes datasets.json, the index the annotation tool's dataset dropdown
reads.

Run this any time you pull a new collection, so it shows up in the dropdown.

Usage:
    python list_panorama_datasets.py
"""
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PANORAMAS_DIR = SCRIPT_DIR.parent / "data" / "cyclomedia_panoramas"
OUT_PATH = PANORAMAS_DIR / "datasets.json"


def build_dataset_list(manifest_relpaths: list[str], signs_relpaths: list[str] = ()) -> list[dict]:
    """manifest_relpaths: paths relative to data/cyclomedia_panoramas/, e.g.
    "fetch_manifest.json" (the root/original collection) or
    "demo_cb301/fetch_manifest.json" (a subfolder collection). Returns
    dataset entries sorted with the root collection first, then subfolders
    alphabetically by label.

    Each entry's "signs" field is where the annotation tool should fetch
    SIMS sign data matching that collection's corner_ids from -- the root
    collection always uses the extension's own live signs_data.json
    (02_generate_signs_data.py's default --out). A subfolder collection
    uses its own co-located signs_data.json (see signs_relpaths) if one was
    generated for it (02_generate_signs_data.py --out
    data/cyclomedia_panoramas/<folder>/signs_data.json), else None --
    deliberately not a silent fallback to some other collection's file,
    whose corner_ids won't match and would just look like permanent
    "no SIMS match" with no indication why."""
    signs_by_folder = set()
    for relpath in signs_relpaths:
        posix_relpath = relpath.replace("\\", "/")
        if "/" in posix_relpath:
            signs_by_folder.add(posix_relpath.rsplit("/", 1)[0])

    entries = []
    for relpath in manifest_relpaths:
        posix_relpath = relpath.replace("\\", "/")
        parent = posix_relpath.rsplit("/", 1)[0] if "/" in posix_relpath else ""
        label = parent if parent else "original"
        if not parent:
            signs = "/extension/signs_data.json"
        elif parent in signs_by_folder:
            signs = f"/data/cyclomedia_panoramas/{parent}/signs_data.json"
        else:
            signs = None
        entries.append({
            "label": label,
            "manifest": f"/data/cyclomedia_panoramas/{posix_relpath}",
            "signs": signs,
        })
    entries.sort(key=lambda e: (e["label"] != "original", e["label"]))
    return entries


def main():
    manifest_relpaths = [
        str(p.relative_to(PANORAMAS_DIR)) for p in PANORAMAS_DIR.glob("**/fetch_manifest.json")
    ]
    signs_relpaths = [
        str(p.relative_to(PANORAMAS_DIR)) for p in PANORAMAS_DIR.glob("*/signs_data.json")
    ]
    datasets = build_dataset_list(manifest_relpaths, signs_relpaths)
    OUT_PATH.write_text(json.dumps({"datasets": datasets}, indent=2))
    print(f"Wrote {len(datasets)} dataset(s) to {OUT_PATH}")
    for d in datasets:
        signs_note = d["signs"] if d["signs"] else "(none -- no SIMS matching for this collection)"
        print(f"  {d['label']}: {d['manifest']}")
        print(f"    signs: {signs_note}")


if __name__ == "__main__":
    main()
