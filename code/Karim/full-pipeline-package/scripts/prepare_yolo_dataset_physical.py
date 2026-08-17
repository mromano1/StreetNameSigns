"""
Convert manual-capture manifests + cropped images into the YOLO detection
dataset layout for the Physical Condition model: ../yolo/data_physical.yaml
and notebooks/06_yolo_physical_pipeline.ipynb expect
../data/yolo_dataset_physical/{images,labels}/{train,val}.

Scoped to physical-condition classes only (old_design, faded, bent_damaged,
hanging, vandalized) -- see
docs/superpowers/specs/2026-07-29-physical-condition-model-flow-design.md.
Rows tagged only with intersection-rule categories (missing,
wrong-direction) are dropped entirely, not kept as negatives; rows mixing
an intersection tag with a physical tag keep only the physical tag(s).

Regenerates the dataset from scratch on every run -- source of truth is the
manifest CSVs + images under data/raw_images/, this script only ever writes
into data/yolo_dataset_physical/. Does not read or write anything under
data/yolo_dataset/ or yolo/data.yaml (the separate 7-class flow).

Usage:
    python prepare_yolo_dataset_physical.py
"""
import csv
import random
import re
import shutil
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
DATA_YAML = SCRIPT_DIR.parent / "yolo" / "data_physical.yaml"
OUT_IMAGES = DATA_DIR / "yolo_dataset_physical" / "images"
OUT_LABELS = DATA_DIR / "yolo_dataset_physical" / "labels"

# capture extension damage-button value -> physical-model class name.
# "old_design" covers both white-border and all-caps signs, same as the
# 7-class model. missing/wrong-direction are intersection-rule tags, out
# of scope for this model -- see INTERSECTION_TOKENS below.
PHYSICAL_BUTTON_TO_CLASS = {
    "bent": "bent_damaged",
    "white-border": "old_design",
    "all-caps": "old_design",
    "faded": "faded",
    "hanging": "hanging",
    "vandalized": "vandalized",
}
INTERSECTION_TOKENS = {"missing", "wrong-direction"}
# A capture artifact (glitched/wobbly panorama stitching, etc.) is a
# data-quality issue, not real sign damage -- deliberately not in
# PHYSICAL_BUTTON_TO_CLASS. Training the model to detect artifacts is out of
# scope; this only exists so artifact-tagged captures don't get mislabeled
# as physical damage and included in training.
ARTIFACT_TOKEN = "artifact"
NEGATIVE_VALUE = "no damage"

# Near-full-frame box: images are already cropped tight to the sign, so
# this is a placeholder box, not real localization (same limitation as
# prepare_yolo_dataset.py).
BBOX_CENTER = (0.5, 0.5)
BBOX_SIZE = (0.9, 0.9)

VAL_FRACTION = 0.2
MIN_FOR_VAL_SPLIT = 5  # classes with fewer examples than this go entirely to train
SEED = 42


def classify_damage_category(raw):
    """Classifies a manifest row's raw damage_category string for the
    Physical Condition model. Returns (class_names, drop, unmapped):

    - class_names: deduped list of physical class names, in first-seen
      order. Empty for a "no damage" negative or a dropped row.
    - drop: True if this row must be excluded from the dataset entirely
      (a pure intersection-tag row, an artifact-tagged row, or one with an
      unrecognized token) -- as opposed to a "no damage" negative, which is
      kept.
    - unmapped: unrecognized tokens, for the caller's warning message.
      Only non-empty when drop is True for that reason.
    """
    raw = (raw or "").strip()
    if raw == NEGATIVE_VALUE:
        return [], False, []

    tokens = [t.strip() for t in raw.split(";") if t.strip()]

    # An artifact tag means the image itself is untrustworthy -- drop
    # unconditionally, even if a physical damage tag is also present.
    # Unlike intersection tags (a separate concern from image quality),
    # there's nothing here worth salvaging.
    if ARTIFACT_TOKEN in tokens:
        return [], True, []

    class_names = []
    unmapped = []
    for t in tokens:
        mapped = PHYSICAL_BUTTON_TO_CLASS.get(t)
        if mapped:
            if mapped not in class_names:
                class_names.append(mapped)
        elif t not in INTERSECTION_TOKENS:
            unmapped.append(t)

    if unmapped:
        return [], True, unmapped

    if not class_names:
        return [], True, []

    return class_names, False, []


def find_manifests():
    return sorted(DATA_DIR.glob("raw_images/*/manual_capture/manifest_*.csv"))


def load_rows(manifest_paths):
    """Returns (rows, warnings). rows is a list of (image_path,
    class_names) -- class_names is [] for negative ("no damage") rows,
    non-empty for positive rows. Rows dropped entirely (pure
    intersection-tag rows, artifact-tagged rows, unmapped tokens, missing
    files, blanks, duplicates) never appear in rows; warnings explains each
    skip."""
    rows = []
    warnings = []
    seen_filenames = {}
    for manifest_path in manifest_paths:
        capture_dir = manifest_path.parent
        with open(manifest_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                filename = (row.get("filename") or "").strip()
                raw = (row.get("damage_category") or "").strip()
                image_path = capture_dir / filename

                if not image_path.exists():
                    warnings.append(f"manifest row for missing file, skipped: {filename}")
                    continue

                if filename in seen_filenames:
                    warnings.append(f"duplicate filename across manifests, skipped: {filename}")
                    continue
                seen_filenames[filename] = True

                if not raw:
                    warnings.append(f"blank damage_category, skipped: {filename}")
                    continue

                class_names, drop, unmapped = classify_damage_category(raw)

                if unmapped:
                    warnings.append(
                        f"unrecognized damage_category value(s) {unmapped!r}, skipped: {filename}"
                    )
                    continue

                if drop:
                    tokens = [t.strip() for t in raw.split(";") if t.strip()]
                    if ARTIFACT_TOKEN in tokens:
                        warnings.append(
                            f"artifact-tagged damage_category {raw!r} (capture issue, not real damage), skipped: {filename}"
                        )
                    else:
                        warnings.append(
                            f"intersection-only damage_category {raw!r}, out of scope for physical model, skipped: {filename}"
                        )
                    continue

                rows.append((image_path, class_names))

    return rows, warnings


def load_class_ids(yaml_path=None):
    """Parses just the `names:` block of a data.yaml-style file (`  0:
    old_design` lines) -- avoids a PyYAML dependency for a file this
    simple. Defaults to the module-level DATA_YAML."""
    yaml_path = Path(yaml_path) if yaml_path else DATA_YAML
    ids = {}
    in_names = False
    for line in yaml_path.read_text().splitlines():
        if re.match(r"^names\s*:", line):
            in_names = True
            continue
        if in_names:
            m = re.match(r"^\s+(\d+)\s*:\s*(\S+)", line)
            if m:
                ids[m.group(2)] = int(m.group(1))
            elif line.strip():
                break
    if not ids:
        raise SystemExit(f"Couldn't parse any class names out of {yaml_path}")
    return ids


def split_rows(rows):
    """Stratifies across ALL of an image's labels, not just the primary
    (first) one -- a class that only ever appears as a secondary tag
    alongside a more common class would otherwise never control its own
    split, and could end up over- or under-represented in val purely by
    chance of where its co-occurring primary label happened to land.

    Processed rarest-class-first (by total occurrence count) so scarce
    classes get first pick of the val budget before a more common
    co-occurring class claims those same images. Classes with fewer than
    MIN_FOR_VAL_SPLIT total occurrences (primary or secondary, across all
    images) go entirely to train -- too few to honestly split without
    duplicating an image across train and val."""
    by_label = defaultdict(list)
    for idx, (image_path, class_names) in enumerate(rows):
        for label in (class_names or ["__negative__"]):
            by_label[label].append(idx)

    rng = random.Random(SEED)
    assigned = {}  # idx -> "train" | "val"
    for label in sorted(by_label, key=lambda l: len(by_label[l])):
        indices = by_label[label]
        if len(indices) < MIN_FOR_VAL_SPLIT:
            print(f"  '{label}': only {len(indices)} example(s) total -- all going to train, val will have 0.")
            for idx in indices:
                assigned.setdefault(idx, "train")
            continue

        already_val = sum(1 for idx in indices if assigned.get(idx) == "val")
        target_val = max(1, round(len(indices) * VAL_FRACTION))
        remaining_val_slots = max(0, target_val - already_val)

        unassigned = [idx for idx in indices if idx not in assigned]
        rng.shuffle(unassigned)
        for idx in unassigned[:remaining_val_slots]:
            assigned[idx] = "val"
        for idx in unassigned[remaining_val_slots:]:
            assigned[idx] = "train"

    train = [rows[i] for i in range(len(rows)) if assigned.get(i, "train") == "train"]
    val = [rows[i] for i in range(len(rows)) if assigned.get(i) == "val"]
    return train, val


def write_split(name, items, class_ids, out_images=None, out_labels=None):
    out_images = Path(out_images) if out_images else OUT_IMAGES
    out_labels = Path(out_labels) if out_labels else OUT_LABELS
    img_dir = out_images / name
    lbl_dir = out_labels / name
    for d in (img_dir, lbl_dir):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    counts = defaultdict(int)
    for image_path, class_names in items:
        image_path = Path(image_path)
        shutil.copy2(image_path, img_dir / image_path.name)
        label_path = lbl_dir / (image_path.stem + ".txt")
        cx, cy = BBOX_CENTER
        w, h = BBOX_SIZE
        lines = [f"{class_ids[cls_name]} {cx} {cy} {w} {h}" for cls_name in class_names]
        label_path.write_text("\n".join(lines) + ("\n" if lines else ""))
        counts["__negative__" if not class_names else class_names[0]] += 1

    print(f"{name}: {len(items)} images")
    for label, n in sorted(counts.items()):
        print(f"    {label}: {n}")


def main():
    class_ids = load_class_ids()
    manifests = find_manifests()
    if not manifests:
        raise SystemExit(f"No manifest CSVs found under {DATA_DIR / 'raw_images'}.")

    print(f"Found {len(manifests)} manifest(s):")
    for m in manifests:
        print(f"  {m}")

    rows, warnings = load_rows(manifests)
    if warnings:
        print(f"\n{len(warnings)} row(s) skipped:")
        for w in warnings:
            print(f"  - {w}")

    if not rows:
        raise SystemExit("No usable rows after filtering. Nothing to write.")

    print(f"\n{len(rows)} usable images. Splitting (val classes need >= {MIN_FOR_VAL_SPLIT} examples):")
    train, val = split_rows(rows)

    print()
    write_split("train", train, class_ids)
    write_split("val", val, class_ids)

    print("\nDone. Physical Condition dataset written to", OUT_IMAGES.parent)


if __name__ == "__main__":
    main()
