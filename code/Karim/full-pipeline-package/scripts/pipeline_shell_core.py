"""
Pure, no-I/O logic for pipeline_shell.py -- path derivation, subprocess
command construction, validation, and the "section missing" banner.
Everything here is a plain function with no subprocess/file/network
calls, so it's fully unit-testable; pipeline_shell.py is the thin
input()-driven glue that actually runs commands and talks to the
terminal, same untested-glue split as annotate.js/annotate-core.js and
serve_tight_crop.py/tight_crop_lib.py elsewhere in this codebase.
"""

import json
import sys
from pathlib import Path

import tight_crop_lib as tcl


def board_label(boro_cd: str) -> str:
    """Matches 01_query_sims_by_community_board.py's own
    board_output_label() -- the "cb"-prefixed label used everywhere
    downstream (CSV filename, corner_id prefix, dataset folder name) so a
    Community Board pull can never be confused with a ZIP-based one."""
    return f"cb{boro_cd}"


def dataset_dir(boro_cd: str) -> str:
    """Where this board's panoramas, fetch_manifest.json, and
    signs_data.json all live together -- relative to scripts/, matching
    every other path in this pipeline."""
    return f"../data/cyclomedia_panoramas/{board_label(boro_cd)}"


def signs_csv_filename(boro_cd: str) -> str:
    """The CSV 01_query_sims_by_community_board.py writes (to the current
    directory) -- must match that script's own naming exactly, since it
    decides the real filename, not this function."""
    return f"signs_zip_{board_label(boro_cd)}.csv"


def signs_data_path(boro_cd: str) -> str:
    """Co-located inside dataset_dir(), not a sibling file at the
    panoramas root -- list_panorama_datasets.py's signs-file discovery
    only looks inside each dataset's own subfolder."""
    return f"{dataset_dir(boro_cd)}/signs_data.json"


def list_available_datasets(panoramas_dir="../data/cyclomedia_panoramas") -> list[dict]:
    """What's already been fetched, read fresh from disk every call --
    doesn't trust datasets.json (list_panorama_datasets.py's own output),
    which can go stale since it's only regenerated when that script is
    re-run by hand. Reuses tight_crop_lib.discover_manifest_paths (the
    same root + subfolder scan the tight-crop server already relies on)
    rather than re-deriving discovery logic a third time.

    Returns [{"label": ..., "image_count": ...}, ...], sorted with the
    root/original collection first, then subfolders alphabetically --
    same ordering convention as list_panorama_datasets.build_dataset_list.
    image_count counts "ok" (fetched this run) and "skipped" (file already
    existed from an earlier run -- still a real file on disk) jobs; only
    "failed" (no file exists) is excluded. Getting this wrong is a real bug
    that shipped once already (2026-08-14): re-fetching an already-complete
    dataset flips every job from "ok" to "skipped" (main() rewrites the
    whole manifest from each run's own results), and an "ok"-only count
    then reports "0 image(s)" for a folder that actually has hundreds of
    real files in it."""
    panoramas_dir = Path(panoramas_dir)
    datasets = []
    for manifest_path in tcl.discover_manifest_paths(panoramas_dir):
        manifest = json.loads(manifest_path.read_text())
        image_count = sum(1 for j in manifest.get("jobs", []) if j.get("status") in ("ok", "skipped"))
        label = "original" if manifest_path.parent == panoramas_dir else manifest_path.parent.name
        datasets.append({"label": label, "image_count": image_count})
    datasets.sort(key=lambda d: (d["label"] != "original", d["label"]))
    return datasets


def section_missing(name: str, why: str, what_exists: list[str]) -> str:
    """Formats (doesn't print -- pipeline_shell.py does that) the banner
    for a pipeline stage that genuinely doesn't exist yet. Never called
    for something merely untested or unverified -- only for real gaps,
    named plainly, with what already exists to build on."""
    lines = [
        "=" * 60,
        f"  SECTION MISSING: {name}",
        "=" * 60,
        why,
        "",
        "What already exists to build on:",
    ]
    lines.extend(f"  - {item}" for item in what_exists)
    lines.append("=" * 60)
    return "\n".join(lines)


def build_query_command(boro_cd: str) -> list[str]:
    return [sys.executable, "01_query_sims_by_community_board.py", boro_cd]


def build_generate_signs_data_command(boro_cd: str) -> list[str]:
    return [
        sys.executable, "02_generate_signs_data.py", board_label(boro_cd),
        "--csv", signs_csv_filename(boro_cd),
        "--out", signs_data_path(boro_cd),
    ]


def build_fetch_panoramas_command(boro_cd: str, limit: int | None = None, multi_angle: bool = False) -> list[str]:
    """limit: caps the fetch to the first N corners, for a cheap/quick
    demo pull instead of a full board (which can be hundreds of real
    Cyclomedia API calls) -- see fetch_cyclomedia_panoramas.py's own
    --limit docstring for what "first N" means (corner order in
    signs_data.json, not a random or representative sample).
    multi_angle: also fetch one "center" and one "side"-per-adjacent-pair
    shot per intersection, on top of the existing one-per-corner fetch --
    see fetch_cyclomedia_panoramas.py's own --multi-angle docstring.
    Roughly doubles API calls/runtime for a typical 4-way intersection."""
    command = [
        sys.executable, "fetch_cyclomedia_panoramas.py", signs_data_path(boro_cd),
        "--output-dir", dataset_dir(boro_cd),
    ]
    if limit is not None:
        command += ["--limit", str(limit)]
    if multi_angle:
        command += ["--multi-angle"]
    return command


def build_list_datasets_command() -> list[str]:
    return [sys.executable, "list_panorama_datasets.py"]


def build_backfill_command(csv_path: str) -> list[str]:
    return [sys.executable, "backfill_tight_crops.py", csv_path]


def build_prepare_physical_command(csv_paths: list[str]) -> list[str]:
    return [sys.executable, "prepare_physical_dataset_from_annotations.py", *csv_paths]


EXPECTED_ANNOTATION_CSV_HEADER = (
    "source_image,image_kind,corner_id,box_index,bbox_x,bbox_y,bbox_w,bbox_h,"
    "image_width,image_height,order_number,sign_code,sign_location,damage_category,"
    "notes,tight_crop_path,flagged,annotated_at"
)


def validate_annotation_csv(path: str) -> tuple[bool, str]:
    """Checks a pasted CSV path before handing it to backfill_tight_crops.py
    -- catches a typo'd path or the wrong file immediately, with a clear
    message, instead of a cryptic failure several steps later."""
    p = Path(path)
    if not p.exists():
        return False, f"File not found: {path}"
    if not p.is_file():
        return False, f"Path is not a file (it's a directory): {path}"
    first_line = p.read_text(encoding="utf-8").splitlines()[0] if p.stat().st_size else ""
    if first_line.strip() != EXPECTED_ANNOTATION_CSV_HEADER:
        return False, (
            "This doesn't look like an annotation tool export -- header doesn't match "
            "RECORD_COLUMNS from annotation_tool/annotate-core.js."
        )
    return True, ""


def training_run_name(board_label_str: str, now) -> str:
    """now: a datetime -- injected rather than read internally (via
    datetime.now()) so this stays deterministic and testable."""
    return f"shell_{board_label_str}_{now.strftime('%Y%m%d_%H%M%S')}"


def backfilled_csv_path(csv_path: str) -> str:
    """Matches backfill_tight_crops.py's own output-naming convention
    exactly (out_path = csv_path.with_name(csv_path.stem + "_with_tight_crops.csv"))
    -- kept here, tested, rather than reimplemented inline in
    pipeline_shell.py's untested glue layer."""
    return str(Path(csv_path).with_name(Path(csv_path).stem + "_with_tight_crops.csv"))


def training_kwargs(data_yaml_path: str, runs_dir: str, run_name: str) -> dict:
    """Kwargs for YOLO(...).train(**kwargs) -- same hyperparameters as the
    physical/spatial sanity-check training runs this session (epochs=50,
    batch=8, AdamW, imgsz=640), pointed at a shell-scoped project/name so
    this run can never collide with or overwrite yolo/runs_physical/."""
    return {
        "data": data_yaml_path,
        "epochs": 50,
        "batch": 8,
        "optimizer": "AdamW",
        "imgsz": 640,
        "project": runs_dir,
        "name": run_name,
        "exist_ok": True,
    }
