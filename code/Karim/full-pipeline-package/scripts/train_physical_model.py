"""
Trains the Physical Condition model and records its accuracy -- both
aggregate and per-damage-category. Extracted from "Section 2: Training" of
notebooks/06_yolo_physical_pipeline.ipynb so its stdout inherits the
parent process's terminal when run as a subprocess (nbconvert captures
cell output rather than streaming it live -- see
docs/superpowers/specs/2026-08-01-retrain-visibility-design.md). Running
this script directly does exactly what the notebook's Section 2 used to do
inline.

Usage:
    python train_physical_model.py
"""
import os
os.environ.setdefault('KMP_DUPLICATE_LIB_OK', 'TRUE')

import sys
from datetime import datetime
from pathlib import Path

import torch
import ultralytics
import yaml
from ultralytics import YOLO

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import physical_report_lib as lib  # noqa: E402

DATA_YAML = SCRIPT_DIR.parent / "yolo" / "data_physical.yaml"
TRAIN_LABELS_DIR = SCRIPT_DIR.parent / "data" / "yolo_dataset_physical" / "labels" / "train"
VAL_LABELS_DIR = SCRIPT_DIR.parent / "data" / "yolo_dataset_physical" / "labels" / "val"
RUNS_DIR = SCRIPT_DIR.parent / "yolo" / "runs_physical"
HISTORY_PATH = RUNS_DIR / "PHYSICAL_RUN_HISTORY.csv"
CLASS_METRICS_PATH = RUNS_DIR / "PHYSICAL_CLASS_METRICS_HISTORY.csv"
PRETRAINED_WEIGHTS = SCRIPT_DIR.parent / "yolo26n.pt"
PHYSICAL_CLASS_NAMES = ["old_design", "faded", "bent_damaged", "hanging", "vandalized"]


def main():
    print('torch:', torch.__version__)
    print('cuda available:', torch.cuda.is_available())
    if torch.cuda.is_available():
        print('device:', torch.cuda.get_device_name(0))
    print('ultralytics:', ultralytics.__version__)

    with open(DATA_YAML) as f:
        data_cfg = yaml.safe_load(f)
    print(f"Classes ({len(data_cfg['names'])}):")
    for idx, name in data_cfg['names'].items():
        print(f'  {idx}: {name}')
    for split, labels_dir in [('train', TRAIN_LABELS_DIR), ('val', VAL_LABELS_DIR)]:
        img_dir = SCRIPT_DIR.parent / "data" / "yolo_dataset_physical" / "images" / split
        n_img = len(list(img_dir.glob('*.jpg'))) if img_dir.is_dir() else 0
        n_lbl = len(list(labels_dir.glob('*.txt'))) if labels_dir.is_dir() else 0
        print(f'{split}: {n_img} images, {n_lbl} labels')

    if not (TRAIN_LABELS_DIR.is_dir() and any(TRAIN_LABELS_DIR.glob("*.txt"))):
        raise SystemExit('No labeled training data yet -- run prepare_yolo_dataset_physical.py first.')

    run_name = f"street_sign_physical_{datetime.now().strftime('%Y-%m-%d')}"
    model = YOLO(str(PRETRAINED_WEIGHTS))
    model.train(
        data=str(DATA_YAML),
        epochs=50,
        batch=16,
        optimizer='AdamW',
        imgsz=640,
        project=str(RUNS_DIR),
        name=run_name,
        workers=0,
    )
    # Ultralytics silently auto-suffixes the save dir (-2, -3, ...) when
    # `name` already exists on disk from a prior attempt, without updating
    # our `run_name` variable -- re-sync it to the actual dir so the
    # history CSV rows and report_physical.py's later run both point at
    # the run that was really trained.
    run_name = model.trainer.save_dir.name

    val_metrics = model.val(data=str(DATA_YAML))
    precision = float(val_metrics.box.mp)
    recall = float(val_metrics.box.mr)
    map50 = float(val_metrics.box.map50)
    map50_95 = float(val_metrics.box.map)

    class_counts = lib.count_classes_in_dataset(TRAIN_LABELS_DIR, VAL_LABELS_DIR, PHYSICAL_CLASS_NAMES)
    history_row = lib.build_run_history_row(
        run_name=run_name,
        date_str=datetime.now().strftime('%Y-%m-%d'),
        class_counts=class_counts,
        precision=precision, recall=recall, map50=map50, map50_95=map50_95,
    )
    lib.append_run_history(history_row, HISTORY_PATH)
    print(f"Run '{run_name}' appended to PHYSICAL_RUN_HISTORY.csv")
    print(history_row)

    class_metrics_rows = lib.build_class_metrics_rows(
        run_name=run_name,
        date_str=datetime.now().strftime('%Y-%m-%d'),
        summary=val_metrics.summary(),
    )
    lib.append_class_metrics(class_metrics_rows, CLASS_METRICS_PATH)
    print(f"Per-class metrics for '{run_name}' appended to PHYSICAL_CLASS_METRICS_HISTORY.csv ({len(class_metrics_rows)} classes)")

    return run_name


if __name__ == "__main__":
    main()
