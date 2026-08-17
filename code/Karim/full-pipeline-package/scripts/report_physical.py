"""
Test + report + shapefile generation for the Physical Condition model.
Run against the latest (or a specified) trained run under
yolo/runs_physical/. See
docs/superpowers/specs/2026-07-29-physical-condition-model-flow-design.md.

Usage:
    python report_physical.py [run_name]
"""
import csv
import sys
from datetime import datetime
from pathlib import Path

import cv2
import folium
from ultralytics import YOLO

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import physical_report_lib as lib  # noqa: E402

RUNS_DIR = SCRIPT_DIR.parent / "yolo" / "runs_physical"
HISTORY_PATH = RUNS_DIR / "PHYSICAL_RUN_HISTORY.csv"
CLASS_METRICS_PATH = RUNS_DIR / "PHYSICAL_CLASS_METRICS_HISTORY.csv"
REPORTS_DIR = SCRIPT_DIR.parent / "data" / "reports"
TRAIN_DIR = SCRIPT_DIR.parent / "data" / "yolo_dataset_physical" / "images" / "train"
VAL_DIR = SCRIPT_DIR.parent / "data" / "yolo_dataset_physical" / "images" / "val"
TRAIN_LABELS_DIR = SCRIPT_DIR.parent / "data" / "yolo_dataset_physical" / "labels" / "train"
VAL_LABELS_DIR = SCRIPT_DIR.parent / "data" / "yolo_dataset_physical" / "labels" / "val"
CONF_THRESHOLD = 0.25
N_SAMPLES = 6


def latest_run_name():
    runs = sorted(
        (d for d in RUNS_DIR.iterdir() if (d / "weights" / "best.pt").exists()),
        key=lambda d: d.stat().st_mtime,
    ) if RUNS_DIR.exists() else []
    if not runs:
        raise SystemExit(f"No trained run found under {RUNS_DIR}. Run the Training section first.")
    return runs[-1].name


def predict_image(model, image_path):
    """Returns list of (class_name, confidence) for one image."""
    result = model(str(image_path), verbose=False)[0]
    return [
        (result.names[int(c)], float(conf))
        for c, conf in zip(result.boxes.cls.tolist(), result.boxes.conf.tolist())
    ]


def annotated_image_b64(model, image_path):
    result = model(str(image_path), verbose=False)[0]
    annotated = result.plot()
    ok, buf = cv2.imencode(".jpg", annotated)
    return lib.encode_image_base64(buf.tobytes())


def load_run_metrics(run_name):
    if not HISTORY_PATH.exists():
        return None
    with open(HISTORY_PATH, newline="", encoding="utf-8") as f:
        matches = [r for r in csv.DictReader(f) if r["run_name"] == run_name]
    return matches[-1] if matches else None


def build_records(model, image_paths, rows_by_filename):
    records = []
    for image_path in image_paths:
        row = rows_by_filename.get(Path(image_path).name)
        if row is None:
            continue
        predictions = predict_image(model, image_path)
        record = lib.build_shapefile_record(row, predictions, threshold=CONF_THRESHOLD)
        if record is not None:
            records.append(record)
    return records


def build_samples(model, image_paths, rows_by_filename):
    """Builds the report's sample-detection entries: one dict per image
    with keys annotated_b64, predicted, human, filename. Consumed by
    physical_report_lib.render_report_html's `samples` context key."""
    samples = []
    for image_path in image_paths:
        row = rows_by_filename.get(image_path.name, {})
        predictions = predict_image(model, image_path)
        pred_str = ", ".join(f"{n}:{c:.2f}" for n, c in predictions) or "(no detections)"
        samples.append({
            "annotated_b64": annotated_image_b64(model, image_path),
            "predicted": pred_str,
            "human": row.get("damage_category", ""),
            "filename": image_path.name,
        })
    return samples


def build_interactive_map_html(model, records, image_dirs):
    """records: shapefile-record dicts (from build_records) that include
    latitude/longitude (see physical_report_lib.build_shapefile_record).
    image_dirs: directories searched, in order, for each record's original
    image (used to render an annotated-detection thumbnail in its map
    popup). Returns the standalone Folium/Leaflet map's full HTML document
    as a string, or None if there are no records to map -- never builds an
    empty/broken map."""
    if not records:
        return None

    def find_image_path(filename):
        for d in image_dirs:
            candidate = Path(d) / filename
            if candidate.exists():
                return candidate
        return None

    grouped = lib.group_records_by_predicted_class(records)
    avg_lat = sum(r["latitude"] for r in records) / len(records)
    avg_lon = sum(r["longitude"] for r in records) / len(records)
    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=15)

    for cls, cls_records in sorted(grouped.items()):
        layer = folium.FeatureGroup(name=f"{cls} ({len(cls_records)})")
        for record in cls_records:
            image_path = find_image_path(record["filename"])
            image_b64 = annotated_image_b64(model, image_path) if image_path else None
            popup_html = lib.build_map_popup_html(record, image_b64)
            folium.CircleMarker(
                location=[record["latitude"], record["longitude"]],
                radius=5,
                color=lib.PHYSICAL_CLASS_COLORS.get(cls, lib.DEFAULT_CLASS_COLOR),
                fill=True,
                fill_opacity=0.8,
                popup=folium.Popup(popup_html, max_width=260),
            ).add_to(layer)
        layer.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m.get_root().render()


def main(run_name=None):
    run_name = run_name or latest_run_name()
    model_path = RUNS_DIR / run_name / "weights" / "best.pt"
    if not model_path.exists():
        raise SystemExit(f"No trained model at {model_path}.")

    print(f"Loading model from {model_path}")
    model = YOLO(str(model_path))

    rows_by_filename = lib.load_manifest_rows_by_filename()

    val_images = sorted(VAL_DIR.glob("*.jpg"))
    train_images = sorted(TRAIN_DIR.glob("*.jpg"))
    all_images = train_images + val_images

    print(f"Running inference on {len(val_images)} val image(s)...")
    val_records = build_records(model, val_images, rows_by_filename)
    print(f"Running inference on {len(all_images)} total image(s)...")
    all_records = build_records(model, all_images, rows_by_filename)

    print("Building interactive map...")
    map_doc_html = build_interactive_map_html(model, all_records, [TRAIN_DIR, VAL_DIR])

    metrics = load_run_metrics(run_name) or {}
    class_counts_by_split = lib.count_classes_by_split(TRAIN_LABELS_DIR, VAL_LABELS_DIR, lib.PHYSICAL_CLASS_NAMES)
    class_metrics = lib.load_class_metrics_last_two_runs(CLASS_METRICS_PATH)

    sample_paths = lib.select_diverse_sample_paths(val_images, rows_by_filename, N_SAMPLES)
    samples = build_samples(model, sample_paths, rows_by_filename)

    history_rows = []
    if HISTORY_PATH.exists():
        with open(HISTORY_PATH, newline="", encoding="utf-8") as f:
            history_rows = list(csv.DictReader(f))

    context = {
        "run_name": run_name,
        "run_date": metrics.get("date", datetime.now().strftime("%Y-%m-%d")),
        "metrics": metrics,
        "class_counts_by_split": class_counts_by_split,
        "class_metrics": class_metrics,
        "map_doc_html": map_doc_html,
        "history_chart_b64": lib.render_history_chart_base64(history_rows) if history_rows else "",
        "samples": samples,
        "flagged_count_val": len(val_records),
        "flagged_count_all": len(all_records),
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    html_path = REPORTS_DIR / f"physical_condition_{run_name}.html"
    html_path.write_text(lib.render_report_html(context), encoding="utf-8")
    print(f"Report written to {html_path}")

    lib.write_shapefile(val_records, REPORTS_DIR / f"physical_condition_val_{run_name}.shp")
    lib.write_shapefile(all_records, REPORTS_DIR / f"physical_condition_all_{run_name}.shp")
    print(f"Shapefiles written to {REPORTS_DIR}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
