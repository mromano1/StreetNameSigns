"""
Pure/testable logic for the Physical Condition model's report + shapefile
generation: shapefile record building, coordinate reprojection, run-history
tracking, and HTML report rendering. Deliberately free of ultralytics/cv2
imports so it stays unit-testable without loading a real model -- the
orchestration that calls a real YOLO model lives in report_physical.py.

See docs/superpowers/specs/2026-07-29-physical-condition-model-flow-design.md.
"""
import base64
import csv
import html
import io
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import shapefile
from pyproj import Transformer

import prepare_yolo_dataset_physical as pydp
import community_board_lookup as cbl

_TO_2263 = Transformer.from_crs("EPSG:4326", "EPSG:2263", always_xy=True)

# (record dict key, DBF column name) pairs -- DBF field names are limited
# to 10 characters (verified: pyshp silently truncates and warns past that,
# e.g. "order_numbers" -> "order_numb"), so several of Task 4's descriptive
# dict keys need a short DBF-safe alias here rather than being shortened at
# the source.
SHAPEFILE_FIELDS = [
    ("order_numbers", "order_num"),
    ("sign_codes", "sign_codes"),
    ("corner_id", "corner_id"),
    ("predicted_classes", "pred_class"),
    ("confidences", "confidence"),
    ("human_label", "human_lbl"),
    ("filename", "filename"),
    ("capture_date", "cap_date"),
    ("community_board", "comm_board"),
    ("intersection", "intersect"),
]

# NAD83 / New York Long Island (US feet) -- the exact WKT already used by
# this project's other shapefiles (data/processed/sims_coverage_area.prj),
# reused verbatim since pyshp doesn't generate a .prj on its own.
EPSG_2263_PRJ = (
    'PROJCS["NAD_1983_StatePlane_New_York_Long_Island_FIPS_3104_Feet",'
    'GEOGCS["GCS_North_American_1983",DATUM["D_North_American_1983",'
    'SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],'
    'UNIT["Degree",0.0174532925199433]],PROJECTION["Lambert_Conformal_Conic"],'
    'PARAMETER["False_Easting",984250.0],PARAMETER["False_Northing",0.0],'
    'PARAMETER["Central_Meridian",-74.0],'
    'PARAMETER["Standard_Parallel_1",41.0333333333333],'
    'PARAMETER["Standard_Parallel_2",40.6666666666667],'
    'PARAMETER["Latitude_Of_Origin",40.1666666666667],'
    'UNIT["US survey foot",0.304800609601219]]'
)


def reproject_lat_lon_to_2263(lat, lon):
    """WGS84 (lat, lon) -> NY State Plane / EPSG:2263 (x, y) in US feet."""
    x, y = _TO_2263.transform(lon, lat)
    return x, y


def _dedupe_flagged_predictions(flagged):
    """flagged: list of (class_name, confidence) pairs already above
    threshold. The model can emit more than one detection box for the same
    class on a single-sign image (near-identical overlapping boxes that
    per-class NMS doesn't fully collapse) -- this reduces those down to one
    entry per class, keeping the highest-confidence occurrence, and
    preserves first-seen order for the rest."""
    best_by_class = {}
    order = []
    for name, conf in flagged:
        if name not in best_by_class:
            order.append(name)
            best_by_class[name] = conf
        elif conf > best_by_class[name]:
            best_by_class[name] = conf
    return [(name, best_by_class[name]) for name in order]


def build_intersection_string(on_street, from_street):
    """Combines a manifest row's on_street/from_street (free-text,
    typically all-caps, e.g. "6 AVENUE") into a human-readable
    intersection label, e.g. "6 Avenue & West 53 Street". Either side
    may be missing (some manifest rows only ever recorded one street).

    Alphabetically sorted rather than on_street-first: two signs at the
    same physical corner can have on_street/from_street recorded in
    either order, and without canonicalizing, the same corner produces
    two different strings depending on which sign's row gets read --
    real example from the 2026-08-17 report, "Grand Concourse & E 138
    St" vs "E 138 St & Grand Concourse" for the same corner. Sorting
    means grouping/deduping by this string (e.g. a DOT reviewer) always
    lands on one canonical label per corner."""
    on_street = (on_street or "").strip().title()
    from_street = (from_street or "").strip().title()
    if on_street and from_street:
        first, second = sorted([on_street, from_street])
        return f"{first} & {second}"
    return on_street or from_street


def build_shapefile_record(row, predictions, threshold=0.25, cb_index=None):
    """row: a manifest CSV row dict (latitude, longitude, order_numbers,
    sign_codes, corner_id, damage_category, filename, timestamp,
    on_street, from_street). predictions: list of (class_name,
    confidence) tuples for this image. cb_index: an optional Community
    Board lookup index from community_board_lookup.build_community_board_index
    / load_community_board_index -- when omitted, community_board is "".
    Returns a record dict, or None if no prediction meets `threshold`."""
    flagged = [(name, conf) for name, conf in predictions if conf >= threshold]
    if not flagged:
        return None
    flagged = _dedupe_flagged_predictions(flagged)

    if not row.get("latitude") or not row.get("longitude"):
        return None

    lat = float(row["latitude"])
    lon = float(row["longitude"])
    x, y = reproject_lat_lon_to_2263(lat, lon)

    community_board = (
        cbl.lookup_community_board(lat, lon, cb_index) if cb_index else ""
    )

    return {
        "x": x,
        "y": y,
        "latitude": lat,
        "longitude": lon,
        "order_numbers": row.get("order_numbers", ""),
        "sign_codes": row.get("sign_codes", ""),
        "corner_id": row.get("corner_id", ""),
        "predicted_classes": ";".join(name for name, _ in flagged),
        "confidences": ";".join(f"{conf:.2f}" for _, conf in flagged),
        "human_label": row.get("damage_category", ""),
        "filename": row.get("filename", ""),
        "capture_date": (row.get("timestamp") or "")[:10],
        "community_board": community_board,
        "intersection": build_intersection_string(
            row.get("on_street", ""), row.get("from_street", "")
        ),
    }


def write_shapefile(records, out_path):
    """Writes a point shapefile (EPSG:2263) -- one point per record, fields
    per SHAPEFILE_FIELDS (dict_key -> dbf_name). Writes .shp/.shx/.dbf via
    pyshp plus a .prj (pyshp doesn't generate one)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with shapefile.Writer(str(out_path), shapeType=shapefile.POINT) as w:
        for _dict_key, dbf_name in SHAPEFILE_FIELDS:
            w.field(dbf_name, "C", size=254)
        for record in records:
            w.point(record["x"], record["y"])
            w.record(*[str(record.get(dict_key, "")) for dict_key, _dbf_name in SHAPEFILE_FIELDS])

    out_path.with_suffix(".prj").write_text(EPSG_2263_PRJ, encoding="ascii")


def shapefile_row_to_record(row):
    """row: a dict of DBF-name keys, as returned when reading a shapefile
    back (e.g. geopandas/pyshp), such as {'pred_class': ..., 'human_lbl':
    ...}. Returns a dict using the original descriptive keys (predicted_
    classes, human_label, ...) via the same SHAPEFILE_FIELDS mapping used
    to write it, so downstream map-building code can share one record
    shape with build_shapefile_record."""
    return {dict_key: row.get(dbf_name, "") for dict_key, dbf_name in SHAPEFILE_FIELDS}


def group_records_by_predicted_class(records):
    """records: list of record dicts (each has 'predicted_classes', a
    semicolon-joined string of one or more damage classes). Returns
    {class_name: [record, ...]} -- a record with multiple predicted
    classes appears under each of them, so a map's per-class layer
    toggle still shows it regardless of which of its classes is on."""
    grouped = defaultdict(list)
    for record in records:
        for cls in (record.get("predicted_classes") or "").split(";"):
            cls = cls.strip()
            if cls:
                grouped[cls].append(record)
    return dict(grouped)


def build_map_popup_html(record, image_b64):
    """record: a record dict (predicted_classes, confidences, human_label,
    corner_id, filename, order_numbers, sign_codes, intersection,
    community_board, and optionally latitude/longitude). image_b64:
    base64-encoded JPEG, or None if no image is available for this record.
    Returns the HTML for a map marker popup."""
    img_html = (
        f'<img src="data:image/jpeg;base64,{image_b64}" '
        f'style="max-width:220px;display:block;margin-bottom:6px;">'
        if image_b64 else ""
    )
    lat, lon = record.get("latitude"), record.get("longitude")
    latlon_html = ""
    if lat is not None and lon is not None:
        try:
            latlon_html = f'Lat/Long: {float(lat):.6f}, {float(lon):.6f}<br>'
        except (TypeError, ValueError):
            pass
    return (
        f'{img_html}'
        f'<b>{record.get("predicted_classes", "")}</b> ({record.get("confidences", "")})<br>'
        f'SN: {record.get("sign_codes", "")}<br>'
        f'ST Order #: {record.get("order_numbers", "")}<br>'
        f'Condition: {record.get("human_label", "")}<br>'
        f'Corner: {record.get("corner_id", "")}<br>'
        f'Intersection: {html.escape(record.get("intersection", ""))}<br>'
        f'Community Board: {record.get("community_board", "")}<br>'
        f'{latlon_html}'
        f'{record.get("filename", "")}'
    )


RUN_HISTORY_FIELDS = [
    "date", "run_name", "total_images", "no_damage",
    "old_design", "faded", "bent_damaged", "hanging", "vandalized",
    "precision", "recall", "mAP50", "mAP50_95", "notes",
]
PHYSICAL_CLASS_NAMES = ["old_design", "faded", "bent_damaged", "hanging", "vandalized"]

# Distinct per-class marker colors for the interactive map -- previously
# every class used the same hardcoded red, so toggling more than one layer
# on made them indistinguishable. First 5 slots of this project's
# categorical palette, in fixed (non-cycled) order; class identity is never
# color-alone since each marker's popup and its FeatureGroup layer name
# both already show the class as text.
PHYSICAL_CLASS_COLORS = {
    "old_design": "#2a78d6",     # blue
    "faded": "#eb6834",          # orange
    "bent_damaged": "#1baf7a",   # aqua
    "hanging": "#eda100",        # yellow
    "vandalized": "#e87ba4",     # magenta
}
DEFAULT_CLASS_COLOR = "#7a7a7a"  # neutral gray fallback for an unrecognized class


def select_diverse_sample_paths(image_paths, rows_by_filename, n_samples):
    """image_paths: list of Path objects (e.g. sorted val images).
    rows_by_filename: {filename: manifest row dict}, used to look up each
    image's human-labeled damage_category. Returns up to n_samples of
    image_paths, round-robin-picked across distinct damage categories (by
    first-seen order) so the report's sample-detections section shows a
    spread of classes instead of just whichever class happens to sort
    first alphabetically by filename. A multi-label category (e.g.
    "old_design;hanging") buckets by its first token. Images with no
    manifest row or a blank category form their own "" bucket. If there
    are fewer distinct categories than n_samples, later rounds fill in
    additional images from categories that have more than one example."""
    buckets = {}
    bucket_order = []
    for path in image_paths:
        row = rows_by_filename.get(path.name, {})
        raw = (row.get("damage_category") or "").strip()
        key = raw.split(";", 1)[0].strip()
        if key not in buckets:
            buckets[key] = []
            bucket_order.append(key)
        buckets[key].append(path)

    selected = []
    round_idx = 0
    while len(selected) < n_samples:
        added_this_round = False
        for key in bucket_order:
            if len(selected) >= n_samples:
                break
            bucket = buckets[key]
            if round_idx < len(bucket):
                selected.append(bucket[round_idx])
                added_this_round = True
        if not added_this_round:
            break
        round_idx += 1
    return selected


def build_run_history_row(run_name, date_str, class_counts, precision, recall, map50, map50_95, notes=""):
    row = {
        "date": date_str, "run_name": run_name, "notes": notes,
        "precision": precision, "recall": recall,
        "mAP50": map50, "mAP50_95": map50_95,
    }
    row["total_images"] = sum(class_counts.values())
    for cls in ["no_damage"] + PHYSICAL_CLASS_NAMES:
        row[cls] = class_counts.get(cls, 0)
    return row


def append_run_history(row, csv_path):
    csv_path = Path(csv_path)
    file_exists = csv_path.exists()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RUN_HISTORY_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def load_last_two_runs(csv_path):
    """Returns (last_row, previous_row): raw dicts (RUN_HISTORY_FIELDS
    keys, string values) for the two most recent rows of a run-history CSV.
    previous_row is None if there's only one row; both are None if the file
    doesn't exist or has no rows."""
    csv_path = Path(csv_path)
    if not csv_path.exists():
        return None, None
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None, None
    last_row = rows[-1]
    previous_row = rows[-2] if len(rows) >= 2 else None
    return last_row, previous_row


CLASS_METRICS_FIELDS = ["run_name", "date", "class_name", "precision", "recall", "mAP50", "mAP50_95"]


def build_class_metrics_rows(run_name, date_str, summary):
    """summary: the list of dicts Ultralytics' DetMetrics.summary() returns
    from model.val() -- one dict per class with at least one validation
    example this run (keys 'Class', 'Box-P', 'Box-R', 'mAP50', 'mAP50-95';
    other keys like 'Images'/'Instances'/'Box-F1' are ignored). Returns one
    row per entry, CLASS_METRICS_FIELDS-shaped, ready for
    append_class_metrics(). A class with zero validation examples this run
    never appears in `summary` and so is simply absent from the result --
    never fabricated as a zero."""
    return [
        {
            "run_name": run_name,
            "date": date_str,
            "class_name": entry["Class"],
            "precision": entry["Box-P"],
            "recall": entry["Box-R"],
            "mAP50": entry["mAP50"],
            "mAP50_95": entry["mAP50-95"],
        }
        for entry in summary
    ]


def append_class_metrics(rows, csv_path):
    csv_path = Path(csv_path)
    file_exists = csv_path.exists()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CLASS_METRICS_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


def load_class_metrics_last_two_runs(csv_path):
    """Returns {class_name: (last_row, previous_row)} for every class
    present in the most recent run_name in a class-metrics CSV. previous_row
    is None for a class with no row in the run before that (e.g. it had
    zero validation examples that run). Returns {} if the file doesn't
    exist or has no rows."""
    csv_path = Path(csv_path)
    if not csv_path.exists():
        return {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return {}

    run_names_in_order = list(dict.fromkeys(r["run_name"] for r in rows))
    last_run_name = run_names_in_order[-1]
    previous_run_name = run_names_in_order[-2] if len(run_names_in_order) >= 2 else None

    last_by_class = {r["class_name"]: r for r in rows if r["run_name"] == last_run_name}
    previous_by_class = (
        {r["class_name"]: r for r in rows if r["run_name"] == previous_run_name}
        if previous_run_name else {}
    )
    return {
        class_name: (row, previous_by_class.get(class_name))
        for class_name, row in last_by_class.items()
    }


def resolve_report_path(reports_dir, run_name):
    """Returns the resolved Path to a run's HTML report
    (physical_condition_{run_name}.html) if it exists and stays within
    reports_dir, else None. run_name may come from an untrusted HTTP
    request path -- this guards against path traversal (e.g. a run_name
    containing '/' or '..' segments, or invalid path characters) by
    rejecting any candidate whose resolved path isn't actually inside
    reports_dir, or that can't be resolved at all."""
    reports_dir = Path(reports_dir).resolve()
    try:
        candidate = (reports_dir / f"physical_condition_{run_name}.html").resolve()
        candidate.relative_to(reports_dir)
    except (ValueError, OSError):
        return None
    if not candidate.is_file():
        return None
    return candidate


def _count_classes_in_labels_dir(labels_dir, id_to_name):
    counts = defaultdict(int)
    for label_file in Path(labels_dir).glob("*.txt"):
        content = label_file.read_text().strip()
        if not content:
            counts["no_damage"] += 1
            continue
        first_line = content.splitlines()[0]
        cls_id = int(first_line.split()[0])
        counts[id_to_name[cls_id]] += 1
    return counts


def count_classes_in_dataset(train_labels_dir, val_labels_dir, class_names):
    """Counts images per class (by first label id per file) plus negatives
    (empty label files) across train+val label dirs. Returns a dict like
    {"no_damage": N, "old_design": N, ...} -- only non-zero classes are
    included."""
    id_to_name = dict(enumerate(class_names))
    combined = defaultdict(int)
    for labels_dir in (train_labels_dir, val_labels_dir):
        for cls, n in _count_classes_in_labels_dir(labels_dir, id_to_name).items():
            combined[cls] += n
    return dict(combined)


def count_classes_by_split(train_labels_dir, val_labels_dir, class_names):
    """Like count_classes_in_dataset, but keeps the train and val counts
    separate instead of merging them. Returns {"train": {...}, "val":
    {...}}, each dict shaped like count_classes_in_dataset's return value.
    A class with zero examples in a given split is simply absent from
    that split's dict, never fabricated as a zero."""
    id_to_name = dict(enumerate(class_names))
    return {
        "train": dict(_count_classes_in_labels_dir(train_labels_dir, id_to_name)),
        "val": dict(_count_classes_in_labels_dir(val_labels_dir, id_to_name)),
    }


def encode_image_base64(image_bytes):
    return base64.b64encode(image_bytes).decode("ascii")


def render_history_chart_base64(history_rows):
    """history_rows: list of dicts with 'date', 'mAP50', 'mAP50_95'
    (strings or floats), e.g. rows read from PHYSICAL_RUN_HISTORY.csv.
    Returns a base64-encoded PNG chart of mAP50/mAP50-95 over time."""
    dates = [r["date"] for r in history_rows]
    map50 = [float(r["mAP50"]) for r in history_rows]
    map50_95 = [float(r["mAP50_95"]) for r in history_rows]

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(dates, map50, marker="o", label="mAP50")
    ax.plot(dates, map50_95, marker="o", label="mAP50-95")
    ax.set_ylabel("score")
    ax.set_title("Physical Condition model -- validation mAP by run")
    ax.legend()
    fig.autofmt_xdate()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _fmt(value):
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return str(value)


def render_report_html(context):
    """context keys: run_name, run_date, metrics (dict with precision,
    recall, mAP50, mAP50_95), class_counts_by_split (dict with "train" and
    "val" keys, each a per-class count dict from count_classes_by_split),
    class_metrics (dict from load_class_metrics_last_two_runs: {class_name:
    (last_row, previous_row)}, only classes with at least one validation
    example this run are present -- never fabricated as zero for absent
    classes), history_chart_b64, samples (list of dicts: annotated_b64,
    predicted, human, filename), flagged_count_val, flagged_count_all,
    map_doc_html (a standalone HTML document string to embed as a map, or
    None/falsy)."""
    m = context["metrics"]
    split_counts = context["class_counts_by_split"]
    table_classes = ["no_damage"] + PHYSICAL_CLASS_NAMES
    train_counts = split_counts.get("train", {})
    val_counts = split_counts.get("val", {})
    header_cells = "".join(f"<th>{cls}</th>" for cls in table_classes)
    train_cells = "".join(f"<td>{train_counts.get(cls, 0)}</td>" for cls in table_classes)
    val_cells = "".join(f"<td>{val_counts.get(cls, 0)}</td>" for cls in table_classes)
    total_cells = "".join(
        f"<td>{train_counts.get(cls, 0) + val_counts.get(cls, 0)}</td>" for cls in table_classes
    )

    class_metrics = context["class_metrics"]
    class_metrics_rows_html = ""
    for cls in PHYSICAL_CLASS_NAMES:
        entry = class_metrics.get(cls)
        if entry is None:
            class_metrics_rows_html += (
                f'<tr><td>{cls}</td>'
                f'<td colspan="4" class="no-data">no examples this run</td></tr>'
            )
            continue
        last_row, _previous_row = entry
        class_metrics_rows_html += (
            f'<tr><td>{cls}</td>'
            f'<td>{_fmt(last_row.get("precision", ""))}</td>'
            f'<td>{_fmt(last_row.get("recall", ""))}</td>'
            f'<td>{_fmt(last_row.get("mAP50", ""))}</td>'
            f'<td>{_fmt(last_row.get("mAP50_95", ""))}</td></tr>'
        )
    sample_html = "".join(
        f'<div class="sample">'
        f'<img src="data:image/jpeg;base64,{s["annotated_b64"]}" />'
        f'<p>{s["filename"]}<br>predicted: {s["predicted"]}<br>human: {s["human"]}</p>'
        f'</div>'
        for s in context["samples"]
    )
    map_section = (
        f'<iframe srcdoc="{html.escape(context["map_doc_html"])}" '
        f'style="width:100%; height:600px; border:1px solid #ccc;"></iframe>'
        if context.get("map_doc_html")
        else '<p>No flagged signs to map for this run.</p>'
    )
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Physical Condition Model Report -- {context['run_name']}</title>
<style>
body {{ font-family: sans-serif; margin: 2rem; }}
.no-data {{ color: #888; font-style: italic; }}
table {{ border-collapse: collapse; margin-bottom: 1.5rem; }}
td, th {{ border: 1px solid #ccc; padding: 0.4rem 0.8rem; text-align: left; }}
.samples {{ display: flex; flex-wrap: wrap; gap: 1rem; }}
.sample img {{ max-width: 220px; display: block; }}
</style>
</head>
<body>
<h1>Physical Condition Model -- Run Report</h1>
<p>Run: <strong>{context['run_name']}</strong> ({context['run_date']})</p>

<h2>Metrics (this run)</h2>
<table>
<tr><th>precision</th><td>{_fmt(m.get('precision', ''))}</td></tr>
<tr><th>recall</th><td>{_fmt(m.get('recall', ''))}</td></tr>
<tr><th>mAP50</th><td>{_fmt(m.get('mAP50', ''))}</td></tr>
<tr><th>mAP50-95</th><td>{_fmt(m.get('mAP50_95', ''))}</td></tr>
</table>

<h2>Dataset composition (current dataset)</h2>
<table>
<tr><th></th>{header_cells}</tr>
<tr><td>Training Set</td>{train_cells}</tr>
<tr><td>Testing Set</td>{val_cells}</tr>
<tr><td>Total</td>{total_cells}</tr>
</table>

<h2>Accuracy by damage type (this run)</h2>
<table>
<tr><th>damage type</th><th>precision</th><th>recall</th><th>mAP50</th><th>mAP50-95</th></tr>
{class_metrics_rows_html}
</table>

<h2>Accuracy over time</h2>
<img src="data:image/png;base64,{context['history_chart_b64']}" />

<h2>Sample detections</h2>
<div class="samples">{sample_html}</div>

<h2>Interactive Map</h2>
{map_section}

<h2>Flagged entries</h2>
<p>Validation set: <strong>{context['flagged_count_val']}</strong> signs reported.</p>
<p>Full dataset: <strong>{context['flagged_count_all']}</strong> signs reported.</p>
<p>See shapefiles: <code>physical_condition_val_{context['run_name']}.shp</code>, <code>physical_condition_all_{context['run_name']}.shp</code></p>
</body>
</html>
"""


def load_manifest_rows_by_filename():
    """Returns {filename: row_dict} for every row across all manifest CSVs,
    regardless of damage_category -- used to join model predictions back to
    lat/long, SIMS order numbers, etc. Last manifest wins on duplicate
    filenames (this is metadata lookup only, not the training set, where
    duplicates are already excluded by load_rows)."""
    rows_by_filename = {}
    for manifest_path in pydp.find_manifests():
        with open(manifest_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                filename = (row.get("filename") or "").strip()
                if filename:
                    rows_by_filename[filename] = row
    return rows_by_filename
