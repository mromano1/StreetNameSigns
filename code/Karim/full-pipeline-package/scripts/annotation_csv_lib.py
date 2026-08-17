"""Shared helpers for reading the annotation tool's exported CSV (schema:
annotation_tool/annotate-core.js's RECORD_COLUMNS). Used by
backfill_tight_crops.py and prepare_physical_dataset_from_annotations.py.
"""


def dedupe_latest_boxes(rows):
    """Keeps only the latest annotated_at per (source_image, box_index).
    Export CSV dumps the full accumulated record set every time, so
    revisiting an image (Prev, then Save again) leaves both the old and
    corrected save for the same box in the file -- rows with no
    source_image/box_index (buildFlaggedRecord's shape) are dropped
    entirely, not just left undeduped."""
    latest = {}
    for row in rows:
        source_image = (row.get("source_image") or "").strip()
        box_index = (row.get("box_index") or "").strip()
        if not source_image or not box_index:
            continue
        key = (source_image, box_index)
        annotated_at = row.get("annotated_at") or ""
        existing = latest.get(key)
        if existing is None or existing.get("annotated_at", "") < annotated_at:
            latest[key] = row
    return list(latest.values())
