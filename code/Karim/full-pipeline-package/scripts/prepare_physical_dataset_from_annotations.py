"""
Convert the annotation tool's tight-crop imagery + damage tags into a YOLO
dataset for the Physical Condition model -- same class taxonomy and
box-placeholder convention as prepare_yolo_dataset_physical.py (which
builds from the capture extension's manual-capture manifests instead),
reusing that script's classify_damage_category/split_rows/write_split/
load_class_ids so both sources agree on what counts as physical damage and
split the same way.

Written to its OWN output folder (data/yolo_dataset_physical_from_
annotations/), deliberately separate from data/yolo_dataset_physical/ --
this is a different, newer image source (a tight Cyclomedia re-render, not
a browser screen-crop) and this script must never silently overwrite the
dataset behind whatever's currently the trained/deployed Physical
Condition model. Merging the two sources (once there's enough
annotation-tool data to be worth it) is a deliberate later decision, not
this script's job.

Every row needs a real tight_crop_path -- the whole point of this source is
training on the tight re-render's added detail, not settling for the raw
panorama crop. Rows without one (e.g. annotated before
start_tight_crop_server.bat was running) are skipped with a warning --
run backfill_tight_crops.py against that CSV first to recover them.

Usage:
    python prepare_physical_dataset_from_annotations.py <annotations.csv> [<annotations2.csv> ...]
"""
import csv
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import annotation_csv_lib
import prepare_yolo_dataset_physical as pydp

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
PANORAMAS_DIR = DATA_DIR / "cyclomedia_panoramas"
OUT_IMAGES = DATA_DIR / "yolo_dataset_physical_from_annotations" / "images"
OUT_LABELS = DATA_DIR / "yolo_dataset_physical_from_annotations" / "labels"


def load_rows(csv_paths, panoramas_dir=PANORAMAS_DIR):
    """Reads one or more annotation-tool export CSVs. Returns (rows,
    warnings) in the (image_path, class_names) shape
    prepare_yolo_dataset_physical's split_rows/write_split expect.
    Deduped across ALL csv_paths together (not per-file), so passing an
    old export alongside a newer one still keeps only each box's latest
    save."""
    panoramas_dir = Path(panoramas_dir)
    all_raw_rows = []
    for csv_path in csv_paths:
        with open(csv_path, newline="", encoding="utf-8") as f:
            all_raw_rows.extend(csv.DictReader(f))
    deduped = annotation_csv_lib.dedupe_latest_boxes(all_raw_rows)

    rows = []
    warnings = []
    for row in deduped:
        if row.get("flagged") == "true":
            continue

        tight_crop_path = (row.get("tight_crop_path") or "").strip()
        label = f"{row.get('source_image')} box {row.get('box_index')}"
        if not tight_crop_path:
            warnings.append(f"no tight crop yet, skipped (run backfill_tight_crops.py?): {label}")
            continue

        image_path = panoramas_dir / tight_crop_path
        if not image_path.exists():
            warnings.append(f"tight_crop_path recorded but file missing, skipped: {tight_crop_path}")
            continue

        raw_damage = (row.get("damage_category") or "").strip()
        if not raw_damage:
            warnings.append(f"blank damage_category, skipped: {tight_crop_path}")
            continue

        class_names, drop, unmapped = pydp.classify_damage_category(raw_damage)
        if unmapped:
            warnings.append(
                f"unrecognized damage_category value(s) {unmapped!r}, skipped: {tight_crop_path}"
            )
            continue
        if drop:
            tokens = [t.strip() for t in raw_damage.split(";") if t.strip()]
            if pydp.ARTIFACT_TOKEN in tokens:
                warnings.append(f"artifact-tagged damage_category {raw_damage!r}, skipped: {tight_crop_path}")
            else:
                warnings.append(
                    f"intersection-only damage_category {raw_damage!r}, out of scope, skipped: {tight_crop_path}"
                )
            continue

        rows.append((image_path, class_names))

    return rows, warnings


def write_split(name, items, class_ids):
    """Local, deliberately NOT pydp.write_split: that function copies each
    image using image_path.name alone, which is safe for the manual-
    capture source (timestamped filenames, e.g. damaged_1784076636051_
    6_AVENUE.jpg) but silently collides here -- every corner's tight
    crops are named tight_{image_kind}_{box_index}.jpg (e.g.
    tight_latest_0.jpg) *inside its own corner_id folder*, so copying by
    bare filename into one shared images/train/ directory means every
    corner's box 0 overwrites the previous one, and box 1 the previous
    box 1, etc. Confirmed empirically: 21 real rows collapsed to 2 files
    per split. Flattening the source folder into the copied filename
    (same fix as prepare_yolo_dataset_spatial.py's write_split) avoids
    this."""
    img_dir = OUT_IMAGES / name
    lbl_dir = OUT_LABELS / name
    for d in (img_dir, lbl_dir):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    counts = defaultdict(int)
    for image_path, class_names in items:
        image_path = Path(image_path)
        flat_name = f"{image_path.parent.name}_{image_path.name}"
        shutil.copy2(image_path, img_dir / flat_name)
        label_path = lbl_dir / (Path(flat_name).stem + ".txt")
        cx, cy = pydp.BBOX_CENTER
        w, h = pydp.BBOX_SIZE
        lines = [f"{class_ids[cls_name]} {cx} {cy} {w} {h}" for cls_name in class_names]
        label_path.write_text("\n".join(lines) + ("\n" if lines else ""))
        counts["__negative__" if not class_names else class_names[0]] += 1

    print(f"{name}: {len(items)} images")
    for label, n in sorted(counts.items()):
        print(f"    {label}: {n}")


def main(csv_paths):
    class_ids = pydp.load_class_ids(SCRIPT_DIR.parent / "yolo" / "data_physical_from_annotations.yaml")

    rows, warnings = load_rows(csv_paths)
    if warnings:
        print(f"{len(warnings)} row(s) skipped:")
        for w in warnings:
            print(f"  - {w}")

    if not rows:
        raise SystemExit("No usable rows after filtering. Nothing to write.")

    print(f"\n{len(rows)} usable tight-crop image(s). Splitting (val classes need >= {pydp.MIN_FOR_VAL_SPLIT} examples):")
    train, val = pydp.split_rows(rows)

    print()
    write_split("train", train, class_ids)
    write_split("val", val, class_ids)

    print("\nDone. Written to", OUT_IMAGES.parent, "-- separate from data/yolo_dataset_physical/,")
    print("the deployed model's dataset. Merge deliberately, don't just repoint training at this folder.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(
            "Usage: python prepare_physical_dataset_from_annotations.py <annotations.csv> [<annotations2.csv> ...]"
        )
    main(sys.argv[1:])
