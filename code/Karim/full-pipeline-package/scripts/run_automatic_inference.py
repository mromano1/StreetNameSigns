"""
The "automatic" mode of pipeline_shell.py: runs the CURRENT spatial model
over freshly-fetched, un-annotated panoramas, crops each detected box, and
classifies each crop with the CURRENT physical (damage) model -- the two
models pipeline_shell.py's own section_missing banner named as "what
already exists to build on." Deliberately reuses the exact
CONF_THRESHOLD/class list already in production (report_physical.py), so
a demo run agrees with the deployed model on what counts as damage.

Known limitation, disclosed rather than hidden: the spatial model's own
sanity-check mAP50 is 0.056 (see docs/superpowers/plans/2026-08-13-
pipeline-shell.md) -- low confidence, not yet a reliable detector. This
runs it anyway, for a demo, and labels the run as such. It produces a
simple standalone HTML report (thumbnails + classifications), not the
full shapefile/interactive-map deliverable report_physical.py produces
for the deployed model -- that's a separate, larger, still-missing piece
(surfacing Community Board fields into that script, which only ever
evaluates its own fixed train/val split today, not arbitrary new
imagery).

Usage:
    python run_automatic_inference.py <dataset_dir>
    python run_automatic_inference.py ../data/cyclomedia_panoramas/cb211
"""
import base64
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import report_physical  # noqa: E402

DEFAULT_SPATIAL_WEIGHTS = SCRIPT_DIR.parent / "runs" / "detect" / "yolo" / "runs" / "spatial_sanity_check" / "weights" / "best.pt"
SPATIAL_MAP50 = 0.056  # 2026-08-13 sanity-check run -- see docs/superpowers/plans/2026-08-13-pipeline-shell.md
CONF_THRESHOLD = report_physical.CONF_THRESHOLD  # 0.25, same as the deployed model
REPORTS_DIR = SCRIPT_DIR.parent / "data" / "reports"


def clamp_box(xyxy, image_width, image_height):
    """Clamps a detection box (x1, y1, x2, y2) to valid image bounds --
    YOLO detections can occasionally extend a pixel or two past the real
    edge due to floating-point box regression."""
    x1, y1, x2, y2 = xyxy
    x1 = max(0, min(image_width, x1))
    x2 = max(0, min(image_width, x2))
    y1 = max(0, min(image_height, y1))
    y2 = max(0, min(image_height, y2))
    return x1, y1, x2, y2


def summarize_detection(corner_id, box_index, box_conf, damage_predictions, threshold=CONF_THRESHOLD):
    """damage_predictions: list of (class_name, confidence) from the
    physical model, same shape report_physical.predict_image returns.
    Returns a plain dict describing this one detected+classified box --
    "no damage" is anything with nothing above threshold, same rule
    build_shapefile_record already uses in production."""
    flagged = [(name, conf) for name, conf in damage_predictions if conf >= threshold]
    flagged.sort(key=lambda nc: nc[1], reverse=True)
    return {
        "corner_id": corner_id,
        "box_index": box_index,
        "box_confidence": box_conf,
        "damage": flagged[0][0] if flagged else "no_damage",
        "damage_confidence": flagged[0][1] if flagged else None,
    }


def build_html_report(rows, crop_paths, board_label):
    """rows: summarize_detection() dicts. crop_paths: {(corner_id, box_index): Path}
    for embedding thumbnails inline (self-contained, no relative-path
    dependency once opened). Returns the HTML as a string -- this function
    does no file I/O itself, so it's testable without a browser."""
    if not rows:
        body = (
            "<p>The spatial model found nothing at any corner. Consistent with its "
            f"low sanity-check mAP50 ({SPATIAL_MAP50}) -- a real, honest result, not a bug.</p>"
        )
    else:
        cards = []
        for row in rows:
            key = (row["corner_id"], row["box_index"])
            crop_path = crop_paths.get(key)
            img_tag = ""
            if crop_path and Path(crop_path).exists():
                b64 = base64.b64encode(Path(crop_path).read_bytes()).decode("ascii")
                img_tag = f'<img src="data:image/jpeg;base64,{b64}" style="max-width:220px;display:block;">'
            damage_label = row["damage"]
            conf_label = f'{row["damage_confidence"]:.2f}' if row["damage_confidence"] is not None else "-"
            cards.append(
                "<div style='border:1px solid #ccc;border-radius:6px;padding:10px;margin:8px;display:inline-block;vertical-align:top;'>"
                f"{img_tag}"
                f"<p><b>{row['corner_id']}</b> box {row['box_index']}<br>"
                f"box confidence: {row['box_confidence']:.2f}<br>"
                f"damage: <b>{damage_label}</b> ({conf_label})</p>"
                "</div>"
            )
        body = "<div>" + "".join(cards) + "</div>"

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Automatic detection -- {board_label}</title></head>
<body style="font-family:sans-serif;background:#111;color:#eee;padding:20px;">
<h1>Automatic detection + classification -- {board_label}</h1>
<p style="color:#f88;"><b>Experimental:</b> spatial model sanity-check mAP50 = {SPATIAL_MAP50} (low confidence,
not yet a reliable detector). This report shows the CURRENT model's real output, unfiltered by human review --
not a validated damage assessment.</p>
<p>{len(rows)} box(es) detected and classified.</p>
{body}
</body></html>"""


def run_corner(spatial_model, physical_model, corner_dir, corner_id):
    """Runs spatial detection on this corner's latest.jpg, crops+classifies
    each detected box, saves each crop next to the source image (matching
    the tight_<kind>_<n>.jpg naming convention already used elsewhere), and
    returns (rows, crop_paths) -- rows are summarize_detection() dicts,
    crop_paths maps (corner_id, box_index) -> saved crop Path. Empty if the
    spatial model found nothing at this corner."""
    from PIL import Image

    image_path = corner_dir / "latest.jpg"
    if not image_path.exists():
        return [], {}

    result = spatial_model(str(image_path), verbose=False)[0]
    boxes = result.boxes.xyxy.tolist()
    confs = result.boxes.conf.tolist()

    image = Image.open(image_path)
    rows = []
    crop_paths = {}
    for i, (xyxy, box_conf) in enumerate(zip(boxes, confs)):
        x1, y1, x2, y2 = clamp_box(xyxy, image.width, image.height)
        if x2 <= x1 or y2 <= y1:
            continue
        crop = image.crop((x1, y1, x2, y2))
        crop_path = corner_dir / f"auto_detect_{i}.jpg"
        crop.save(crop_path, format="JPEG", quality=92)

        physical_result = physical_model(str(crop_path), verbose=False)[0]
        damage_predictions = [
            (physical_result.names[int(c)], float(conf))
            for c, conf in zip(physical_result.boxes.cls.tolist(), physical_result.boxes.conf.tolist())
        ]
        rows.append(summarize_detection(corner_id, i, box_conf, damage_predictions))
        crop_paths[(corner_id, i)] = crop_path
    return rows, crop_paths


def main(dataset_dir, board_label=None, spatial_weights=None, physical_weights=None):
    from ultralytics import YOLO

    dataset_dir = Path(dataset_dir)
    board_label = board_label or dataset_dir.name
    spatial_weights = Path(spatial_weights) if spatial_weights else DEFAULT_SPATIAL_WEIGHTS
    if physical_weights is None:
        run_name = report_physical.latest_run_name()
        physical_weights = report_physical.RUNS_DIR / run_name / "weights" / "best.pt"
        print(f"Using physical model run: {run_name}")
    else:
        physical_weights = Path(physical_weights)

    print(f"Loading spatial model: {spatial_weights}")
    print(f"  (sanity-check only, mAP50={SPATIAL_MAP50} -- low confidence, not a reliable detector yet)")
    spatial_model = YOLO(str(spatial_weights))
    print(f"Loading physical model: {physical_weights}")
    physical_model = YOLO(str(physical_weights))

    corner_dirs = sorted(d for d in dataset_dir.iterdir() if d.is_dir())
    print(f"\nRunning automatic detection + classification over {len(corner_dirs)} corner(s)...")

    all_rows = []
    all_crop_paths = {}
    for corner_dir in corner_dirs:
        rows, crop_paths = run_corner(spatial_model, physical_model, corner_dir, corner_dir.name)
        all_rows.extend(rows)
        all_crop_paths.update(crop_paths)
        for row in rows:
            conf_label = f"{row['damage_confidence']:.2f}" if row["damage_confidence"] is not None else "-"
            print(f"  {row['corner_id']} box {row['box_index']} (box_conf={row['box_confidence']:.2f}): "
                  f"{row['damage']} ({conf_label})")

    print(f"\nDone. {len(all_rows)} box(es) detected and classified across {len(corner_dirs)} corner(s).")

    html = build_html_report(all_rows, all_crop_paths, board_label)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"automatic_detection_{board_label}.html"
    report_path.write_text(html, encoding="utf-8")
    print(f"Wrote {report_path}")
    return report_path, all_rows


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python run_automatic_inference.py <dataset_dir>")
    main(sys.argv[1])
