#!/usr/bin/env python3
"""Train and optionally validate a YOLO model for the pilot dataset.

Install the optional dependency before running:

    pip install ultralytics

Example:

    python code/train_yolo.py --data data/yolo/data.yaml --epochs 50
"""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train a YOLO model on the StreetNameSigns dataset.")
    parser.add_argument("--data", default="data/yolo/data.yaml", help="YOLO data.yaml path.")
    parser.add_argument("--model", default="yolov8n.pt", help="Base YOLO weights or model config.")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--project", default="runs/street-name-signs")
    parser.add_argument("--name", default="pilot")
    parser.add_argument("--skip-val", action="store_true", help="Skip validation after training.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        from ultralytics import YOLO
    except ImportError:
        print("Missing optional dependency: ultralytics")
        print("Install it with: pip install ultralytics")
        return 2

    model = YOLO(args.model)
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project=args.project,
        name=args.name,
    )
    if not args.skip_val:
        model.val(data=args.data, imgsz=args.imgsz, project=args.project, name=f"{args.name}-val")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
