#!/usr/bin/env python3
"""Prepare annotation, split, YOLO export, and demo CSV files.

This script turns the project workflow into small, repeatable steps:

    python code/pipeline.py init-annotations
    python code/pipeline.py validate data/annotations.csv
    python code/pipeline.py split data/annotations.csv
    python code/pipeline.py export-yolo data/annotations.csv
    python code/pipeline.py export-demo data/annotations.csv

The annotation CSV uses pixel bounding boxes. Damage labels are separated with
semicolons, for example: faded;bent_or_damaged.
"""

from __future__ import annotations

import argparse
import csv
import random
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path


DAMAGE_CLASSES = [
    "missing_sign",
    "bent_or_damaged",
    "old_design",
    "faded",
    "hanging",
    "vandalized",
    "wrong_direction",
    "incomplete_intersection",
]

DETECTION_CLASS = "street_name_sign"
YOLO_CLASSES = [DETECTION_CLASS, *DAMAGE_CLASSES]

ANNOTATION_FIELDS = [
    "annotation_id",
    "location_id",
    "source_id",
    "image_path",
    "request_location",
    "pano_id",
    "image_date",
    "copyright",
    "metadata_status",
    "latitude",
    "longitude",
    "location_method",
    "bbox_xmin",
    "bbox_ymin",
    "bbox_xmax",
    "bbox_ymax",
    "damage_labels",
    "is_undamaged",
    "confidence",
    "confidence_notes",
    "annotator",
    "split",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def parse_labels(value: str) -> list[str]:
    labels = []
    for label in value.replace(",", ";").split(";"):
        clean = label.strip()
        if clean:
            labels.append(clean)
    return labels


def require_columns(rows: list[dict[str, str]], path: Path, columns: list[str]) -> None:
    if not rows:
        raise ValueError(f"{path} has no data rows.")
    missing = [column for column in columns if column not in rows[0]]
    if missing:
        raise ValueError(f"{path} is missing columns: {', '.join(missing)}")


def completed_annotation(row: dict[str, str]) -> bool:
    return all(row.get(field, "").strip() for field in ["bbox_xmin", "bbox_ymin", "bbox_xmax", "bbox_ymax"])


def class_counts(rows: list[dict[str, str]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        labels = parse_labels(row.get("damage_labels", ""))
        if labels:
            counts.update(labels)
        elif parse_bool(row.get("is_undamaged", "")):
            counts[DETECTION_CLASS] += 1
    return counts


def init_annotations(args: argparse.Namespace) -> int:
    metadata_path = Path(args.metadata)
    output_path = Path(args.output)
    if output_path.exists() and not args.force:
        print(f"Refusing to overwrite existing file: {output_path}")
        print("Use --force if you intentionally want to replace it.")
        return 2

    metadata_rows = read_csv(metadata_path)
    require_columns(
        metadata_rows,
        metadata_path,
        [
            "location_id",
            "image_id",
            "request_location",
            "metadata_status",
            "matched_latitude",
            "matched_longitude",
            "pano_id",
            "image_date",
            "copyright",
            "image_path",
            "download_status",
        ],
    )

    rows = []
    for row in metadata_rows:
        if row.get("metadata_status") != "OK" or row.get("download_status") != "OK":
            continue
        image_id = row["image_id"].strip()
        rows.append(
            {
                "annotation_id": f"{image_id}_ann001",
                "location_id": row["location_id"].strip(),
                "source_id": image_id,
                "image_path": row["image_path"].strip(),
                "request_location": row["request_location"].strip(),
                "pano_id": row["pano_id"].strip(),
                "image_date": row["image_date"].strip(),
                "copyright": row["copyright"].strip(),
                "metadata_status": row["metadata_status"].strip(),
                "latitude": row["matched_latitude"].strip(),
                "longitude": row["matched_longitude"].strip(),
                "location_method": "streetview_metadata",
                "bbox_xmin": "",
                "bbox_ymin": "",
                "bbox_xmax": "",
                "bbox_ymax": "",
                "damage_labels": "",
                "is_undamaged": "",
                "confidence": "",
                "confidence_notes": "",
                "annotator": "",
                "split": "",
            }
        )

    write_csv(output_path, rows, ANNOTATION_FIELDS)
    print(f"Wrote {len(rows)} annotation template rows to {output_path}")
    return 0


def validate_annotations(args: argparse.Namespace) -> int:
    path = Path(args.annotations)
    rows = read_csv(path)
    require_columns(rows, path, ANNOTATION_FIELDS)

    errors = []
    warnings = []
    seen_ids = set()
    valid_labels = set(DAMAGE_CLASSES)

    for line_number, row in enumerate(rows, start=2):
        annotation_id = row.get("annotation_id", "").strip()
        if not annotation_id:
            errors.append(f"line {line_number}: missing annotation_id")
        elif annotation_id in seen_ids:
            errors.append(f"line {line_number}: duplicate annotation_id {annotation_id}")
        seen_ids.add(annotation_id)

        labels = parse_labels(row.get("damage_labels", ""))
        unknown = [label for label in labels if label not in valid_labels]
        if unknown:
            errors.append(f"line {line_number}: unknown damage labels: {', '.join(unknown)}")

        is_undamaged = parse_bool(row.get("is_undamaged", ""))
        if is_undamaged and labels:
            errors.append(f"line {line_number}: is_undamaged cannot be true when damage_labels are present")
        if not is_undamaged and not labels:
            warnings.append(f"line {line_number}: no damage_labels and is_undamaged is not true")

        if not completed_annotation(row):
            warnings.append(f"line {line_number}: bounding box is incomplete")
            continue

        try:
            xmin = float(row["bbox_xmin"])
            ymin = float(row["bbox_ymin"])
            xmax = float(row["bbox_xmax"])
            ymax = float(row["bbox_ymax"])
        except ValueError:
            errors.append(f"line {line_number}: bounding box values must be numeric")
            continue

        if xmin >= xmax or ymin >= ymax:
            errors.append(f"line {line_number}: bounding box max values must be greater than min values")
        if min(xmin, ymin, xmax, ymax) < 0:
            errors.append(f"line {line_number}: bounding box values must be non-negative")

    counts = class_counts(rows)
    print(f"Checked {len(rows)} rows in {path}")
    if counts:
        print("Class counts:")
        for label in YOLO_CLASSES:
            if counts[label]:
                print(f"  {label}: {counts[label]}")
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"  {warning}")
    if errors:
        print("Errors:")
        for error in errors:
            print(f"  {error}")
        return 1
    return 0


def split_annotations(args: argparse.Namespace) -> int:
    path = Path(args.annotations)
    output_dir = Path(args.output_dir)
    rows = read_csv(path)
    require_columns(rows, path, ANNOTATION_FIELDS)

    complete_rows = [row for row in rows if completed_annotation(row)]
    if not complete_rows:
        print("No completed annotations found. Fill bbox fields before splitting.")
        return 2

    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in complete_rows:
        group_key = row.get(args.group_by, "").strip() or row.get("source_id", "").strip()
        grouped[group_key].append(row)

    group_keys = list(grouped)
    random.Random(args.seed).shuffle(group_keys)
    test_group_count = max(1, round(len(group_keys) * args.test_ratio))
    test_groups = set(group_keys[:test_group_count])

    train_rows = []
    test_rows = []
    all_rows = []
    for group_key in group_keys:
        split = "test" if group_key in test_groups else "train"
        for row in grouped[group_key]:
            row = dict(row)
            row["split"] = split
            all_rows.append(row)
            if split == "test":
                test_rows.append(row)
            else:
                train_rows.append(row)

    write_csv(output_dir / "annotations_with_split.csv", all_rows, ANNOTATION_FIELDS)
    write_csv(output_dir / "train.csv", train_rows, ANNOTATION_FIELDS)
    write_csv(output_dir / "test.csv", test_rows, ANNOTATION_FIELDS)
    print(f"Wrote {len(train_rows)} train rows and {len(test_rows)} test rows to {output_dir}")
    return 0


def yolo_bbox(row: dict[str, str], image_width: float, image_height: float) -> tuple[float, float, float, float]:
    xmin = float(row["bbox_xmin"])
    ymin = float(row["bbox_ymin"])
    xmax = float(row["bbox_xmax"])
    ymax = float(row["bbox_ymax"])
    x_center = ((xmin + xmax) / 2) / image_width
    y_center = ((ymin + ymax) / 2) / image_height
    width = (xmax - xmin) / image_width
    height = (ymax - ymin) / image_height
    return x_center, y_center, width, height


def export_yolo(args: argparse.Namespace) -> int:
    path = Path(args.annotations)
    output_dir = Path(args.output_dir)
    rows = read_csv(path)
    require_columns(rows, path, ANNOTATION_FIELDS)

    complete_rows = [row for row in rows if completed_annotation(row)]
    if not complete_rows:
        print("No completed annotations found. Fill bbox fields before exporting YOLO data.")
        return 2

    rows_by_source: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in complete_rows:
        split = row.get("split", "").strip() or "train"
        if split not in {"train", "test", "val"}:
            split = "train"
        row = dict(row)
        row["split"] = "val" if split == "test" else split
        rows_by_source[row["source_id"]].append(row)

    copied_images = 0
    written_labels = 0
    for source_id, source_rows in rows_by_source.items():
        split = source_rows[0]["split"]
        image_path = Path(source_rows[0]["image_path"])
        if not image_path.exists():
            print(f"Skipping {source_id}: image not found at {image_path}")
            continue

        image_output = output_dir / "images" / split / image_path.name
        label_output = output_dir / "labels" / split / f"{image_path.stem}.txt"
        image_output.parent.mkdir(parents=True, exist_ok=True)
        label_output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image_path, image_output)
        copied_images += 1

        label_lines = []
        for row in source_rows:
            labels = parse_labels(row.get("damage_labels", ""))
            if not labels:
                labels = [DETECTION_CLASS]
            x_center, y_center, width, height = yolo_bbox(row, args.image_width, args.image_height)
            for label in labels:
                class_id = YOLO_CLASSES.index(label)
                label_lines.append(
                    f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"
                )
        label_output.write_text("\n".join(label_lines) + "\n", encoding="utf-8")
        written_labels += len(label_lines)

    data_yaml = output_dir / "data.yaml"
    class_lines = "\n".join(f"  {index}: {name}" for index, name in enumerate(YOLO_CLASSES))
    data_yaml.write_text(
        f"path: {output_dir}\n"
        "train: images/train\n"
        "val: images/val\n"
        f"nc: {len(YOLO_CLASSES)}\n"
        "names:\n"
        f"{class_lines}\n",
        encoding="utf-8",
    )
    print(f"Copied {copied_images} images and wrote {written_labels} YOLO label rows to {output_dir}")
    print(f"Wrote YOLO config to {data_yaml}")
    return 0


def export_demo(args: argparse.Namespace) -> int:
    path = Path(args.annotations)
    output_path = Path(args.output)
    rows = read_csv(path)
    require_columns(rows, path, ANNOTATION_FIELDS)

    output_fields = [
        "source_id",
        "image_path",
        "latitude",
        "longitude",
        "bbox_xmin",
        "bbox_ymin",
        "bbox_xmax",
        "bbox_ymax",
        "damage_labels",
        "confidence",
        "notes",
    ]
    damaged_rows = []
    for row in rows:
        labels = parse_labels(row.get("damage_labels", ""))
        if not labels:
            continue
        damaged_rows.append(
            {
                "source_id": row["source_id"],
                "image_path": row["image_path"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "bbox_xmin": row["bbox_xmin"],
                "bbox_ymin": row["bbox_ymin"],
                "bbox_xmax": row["bbox_xmax"],
                "bbox_ymax": row["bbox_ymax"],
                "damage_labels": ";".join(labels),
                "confidence": row.get("confidence", ""),
                "notes": row.get("confidence_notes", ""),
            }
        )

    write_csv(output_path, damaged_rows, output_fields)
    print(f"Wrote {len(damaged_rows)} damaged-sign rows to {output_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run StreetNameSigns data preparation steps.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-annotations", help="Create a labeling CSV from Street View metadata.")
    init_parser.add_argument("--metadata", default="data/streetview/metadata.csv")
    init_parser.add_argument("--output", default="data/annotations.csv")
    init_parser.add_argument("--force", action="store_true")
    init_parser.set_defaults(func=init_annotations)

    validate_parser = subparsers.add_parser("validate", help="Check annotation labels and boxes.")
    validate_parser.add_argument("annotations")
    validate_parser.set_defaults(func=validate_annotations)

    split_parser = subparsers.add_parser("split", help="Create grouped train/test CSV files.")
    split_parser.add_argument("annotations")
    split_parser.add_argument("--output-dir", default="data/splits")
    split_parser.add_argument("--test-ratio", type=float, default=0.2)
    split_parser.add_argument("--seed", type=int, default=42)
    split_parser.add_argument("--group-by", default="location_id")
    split_parser.set_defaults(func=split_annotations)

    yolo_parser = subparsers.add_parser("export-yolo", help="Export completed annotations as a YOLO dataset.")
    yolo_parser.add_argument("annotations")
    yolo_parser.add_argument("--output-dir", default="data/yolo")
    yolo_parser.add_argument("--image-width", type=float, default=640)
    yolo_parser.add_argument("--image-height", type=float, default=640)
    yolo_parser.set_defaults(func=export_yolo)

    demo_parser = subparsers.add_parser("export-demo", help="Export the final damaged-sign review table.")
    demo_parser.add_argument("annotations")
    demo_parser.add_argument("--output", default="data/demo_outputs/damaged_signs.csv")
    demo_parser.set_defaults(func=export_demo)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except ValueError as error:
        print(error)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
