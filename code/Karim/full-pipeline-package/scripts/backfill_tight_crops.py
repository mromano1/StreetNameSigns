"""
Replays already-saved annotation-tool box coordinates through the tight-crop
server (serve_tight_crop.py), for rows that ended up with an empty
tight_crop_path -- e.g. every row annotated before the server was running,
or before its multi-dataset fix (2026-08-13; see tight_crop_lib.py).

Doesn't touch the original CSV -- writes <name>_with_tight_crops.csv
alongside it, tight_crop_path filled in for whichever rows succeeded.

Requires start_tight_crop_server.bat (or `python serve_tight_crop.py`)
running first -- this makes a real Cyclomedia API call per box.

Usage:
    python backfill_tight_crops.py <annotations.csv>
"""
import csv
import sys
from pathlib import Path

import requests

import annotation_csv_lib

TIGHT_CROP_URL = "http://127.0.0.1:8766/tight-crop"

dedupe_latest = annotation_csv_lib.dedupe_latest_boxes


def backfill(rows, post_fn=None):
    """rows: deduped CSV row dicts. post_fn(payload) -> the tight-crop
    server's response dict ({"path": ...}) or None on failure --
    injectable so tests never hit a real server. Mutates and returns rows
    with tight_crop_path filled in for successful requests, plus
    (successes, failures) counts/list for reporting. Rows already carrying
    a tight_crop_path, or flagged (a capture-glitch panorama, not worth a
    Cyclomedia call), are left untouched."""
    post_fn = post_fn or _real_post
    successes = 0
    failures = []
    for row in rows:
        if row.get("flagged") == "true":
            continue
        if (row.get("tight_crop_path") or "").strip():
            continue
        payload = {
            "corner_id": row["corner_id"],
            "image_kind": row["image_kind"],
            "box_index": int(row["box_index"]),
            "box": {
                "x": float(row["bbox_x"]), "y": float(row["bbox_y"]),
                "w": float(row["bbox_w"]), "h": float(row["bbox_h"]),
            },
        }
        result = post_fn(payload)
        if result is None:
            failures.append((row["source_image"], row["box_index"]))
            continue
        row["tight_crop_path"] = result["path"]
        successes += 1
    return rows, successes, failures


def _real_post(payload):
    try:
        resp = requests.post(TIGHT_CROP_URL, json=payload, timeout=30)
    except requests.RequestException as e:
        print(f"  request failed: {e}")
        return None
    if not resp.ok:
        print(f"  server returned {resp.status_code}: {resp.text[:200]}")
        return None
    return resp.json()


def main(csv_path):
    csv_path = Path(csv_path)
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    deduped = dedupe_latest(rows)
    print(f"{len(rows)} row(s) in CSV, {len(deduped)} after dedup (latest save per box).")

    updated, successes, failures = backfill(deduped)
    print(f"Backfilled {successes} tight crop(s), {len(failures)} failure(s).")
    for source_image, box_index in failures:
        print(f"  - failed: {source_image} box {box_index}")

    out_path = csv_path.with_name(csv_path.stem + "_with_tight_crops.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(updated)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python backfill_tight_crops.py <annotations.csv>")
    main(sys.argv[1])
