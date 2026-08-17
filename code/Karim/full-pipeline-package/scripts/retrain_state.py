"""Tracks how many labeled captures have accumulated since the last
physical-condition model retrain, by comparing a persisted baseline count
against a fresh scan of the manifest CSVs -- the same source of truth
prepare_yolo_dataset_physical.py uses. See
docs/superpowers/specs/2026-07-31-capture-extension-model-feedback-design.md.
"""
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import prepare_yolo_dataset_physical as pydp  # noqa: E402

DEFAULT_STATE_PATH = SCRIPT_DIR.parent / "data" / "physical_retrain_state.json"


def current_labeled_row_count():
    """Counts usable labeled rows across all manifest CSVs -- the same rows
    prepare_yolo_dataset_physical.main() would use for the next dataset
    build."""
    rows, _warnings = pydp.load_rows(pydp.find_manifests())
    return len(rows)


def read_baseline(state_path=None):
    state_path = Path(state_path) if state_path else DEFAULT_STATE_PATH
    if not state_path.exists():
        return 0
    return json.loads(state_path.read_text(encoding="utf-8")).get("row_count_at_last_retrain", 0)


def write_baseline(count, state_path=None):
    state_path = Path(state_path) if state_path else DEFAULT_STATE_PATH
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"row_count_at_last_retrain": count}), encoding="utf-8")


def compute_delta(current_count, baseline_count):
    """Never negative -- a baseline can exceed the current count if manifest
    files were removed/reorganized since the last retrain; treat that as
    "nothing new" rather than a negative count."""
    return max(0, current_count - baseline_count)
