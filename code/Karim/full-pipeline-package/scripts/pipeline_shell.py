"""
Interactive terminal wizard for the Community-Board-to-trained-model
pipeline. Personal dev/testing tool -- NOT the team handoff deliverable
(that's a separate single-notebook plan). Wires together scripts that
already exist and work; stubs (via pipeline_shell_core.section_missing)
the two pieces that genuinely don't exist yet: automatic-mode inference,
and a report/shapefile scoped to a newly-selected Community Board's own
signs. See docs/superpowers/specs/2026-08-13-pipeline-shell-design.md.

Usage:
    python pipeline_shell.py
"""
import os
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
os.chdir(SCRIPT_DIR)  # every relative path in this file assumes cwd == scripts/

import community_board_lookup as cbl  # noqa: E402
import pipeline_shell_core as core  # noqa: E402


def run_step(command: list[str]) -> None:
    """Runs a wizard step as a subprocess, streaming its own stdout/stderr
    live (inherited, not captured) so the operator sees exactly what the
    underlying script prints -- same reasoning as
    serve_physical_model.py's _run_retrain_subprocess. On failure, prints
    which command failed and propagates that command's own exit code via
    SystemExit(int) -- not a string, which Python's SystemExit always
    maps to exit status 1 regardless of the original code."""
    result = subprocess.run(command)
    if result.returncode != 0:
        print(f"Step failed (exit {result.returncode}): {' '.join(command)}")
        raise SystemExit(result.returncode)


def prompt_board() -> str:
    """Prompts until a valid Community Board is entered. Returns the
    resolved boro_cd code (e.g. "304"), not the raw input."""
    while True:
        raw = input('Community Board (e.g. "304" or "Brooklyn CD 4"): ').strip()
        boro_cd = cbl.resolve_boro_cd(raw)
        if boro_cd:
            print(f"  -> {cbl.boro_cd_to_label(boro_cd)} (boro_cd {boro_cd})")
            return boro_cd
        print(f'  Could not read "{raw}" as a Community Board. Try a code like 304, or "Brooklyn CD 4".')


def prompt_limit() -> int | None:
    """How many corners to fetch panoramas for, capped to the first N in
    signs_data.json's corner order (see fetch_cyclomedia_panoramas.py's
    own --limit docstring -- not a random or representative sample, just
    a cheap way to get a small demo dataset instead of a full board,
    which is hundreds of real Cyclomedia API calls). Blank means no
    cap -- fetch the whole board."""
    while True:
        raw = input(
            "\nHow many corners to fetch panoramas for? "
            "(blank = whole board -- every real Community Board has hundreds; "
            "try e.g. 50 for a quick demo): "
        ).strip()
        if not raw:
            return None
        try:
            limit = int(raw)
        except ValueError:
            print("  Please enter a whole number, or leave blank for no limit.")
            continue
        if limit <= 0:
            print("  Please enter a positive number, or leave blank for no limit.")
            continue
        return limit


def prompt_multi_angle() -> bool:
    """Whether to also fetch center/side shots per intersection, on top of
    the existing one-per-corner fetch -- see
    fetch_cyclomedia_panoramas.py's --multi-angle docstring. Roughly
    doubles API calls/runtime for a typical 4-way intersection, so
    defaults to no."""
    raw = input(
        "\nAlso fetch extra angles per intersection (one from the center, "
        "one per side)? Roughly doubles fetch time/API calls. [y/N]: "
    ).strip().lower()
    return raw == "y"


def print_available_datasets() -> None:
    datasets = core.list_available_datasets()
    if not datasets:
        print("\nNo panoramas fetched yet -- this will be the first pull.")
        return
    print("\nAlready fetched:")
    for d in datasets:
        print(f"  {d['label']}: {d['image_count']} image(s)")


def main():
    print("=" * 60)
    print("  GTECH 78803 Pipeline Shell")
    print("=" * 60)

    print_available_datasets()

    boro_cd = prompt_board()
    limit = prompt_limit()
    multi_angle = prompt_multi_angle()

    print("\nStep 1/4: Querying SIMS signs for this board...")
    run_step(core.build_query_command(boro_cd))

    print("\nStep 2/4: Generating signs_data.json...")
    run_step(core.build_generate_signs_data_command(boro_cd))

    print("\nStep 3/4: Fetching Cyclomedia panoramas (this makes real API calls, may take a while)...")
    run_step(core.build_fetch_panoramas_command(boro_cd, limit=limit, multi_angle=multi_angle))

    print("\nStep 4/4: Registering the dataset for the annotation tool's dropdown...")
    run_step(core.build_list_datasets_command())

    print(f"\nDone. Dataset ready: {core.dataset_dir(boro_cd)}")

    mode = prompt_mode()
    if mode == "automatic":
        run_automatic_branch(boro_cd)
    else:
        run_manual_branch(boro_cd)


def prompt_mode() -> str:
    while True:
        raw = input('\nManual (annotate yourself) or Automatic (use the current model)? [manual/automatic]: ').strip().lower()
        if raw in ("manual", "m"):
            return "manual"
        if raw in ("automatic", "auto", "a"):
            return "automatic"
        print('  Please type "manual" or "automatic".')


def run_automatic_branch(boro_cd: str) -> None:
    """Runs the CURRENT spatial + physical models over this board's
    freshly-fetched panoramas (run_automatic_inference.py), no human
    review -- explicitly experimental (the spatial model's own sanity-check
    mAP50 is 0.056, see run_automatic_inference.SPATIAL_MAP50), not a
    validated damage assessment. Opens the resulting HTML report in the
    browser. What this does NOT do: assemble the full shapefile/
    interactive-map deliverable report_physical.py produces for the
    deployed model -- that script only ever evaluates its own fixed
    train/val split, not arbitrary new imagery, and wiring Community
    Board fields into it is a separate, larger, still-unstarted piece."""
    import webbrowser

    import run_automatic_inference

    board_label = core.board_label(boro_cd)
    dataset_dir = SCRIPT_DIR / core.dataset_dir(boro_cd)
    report_path, rows = run_automatic_inference.main(dataset_dir, board_label=board_label)
    webbrowser.open(report_path.resolve().as_uri())

    print(core.section_missing(
        "Full shapefile / interactive-map report for this board",
        "report_physical.py (the deployed model's own report generator) only ever "
        "evaluates its own fixed train/val split, not arbitrary new imagery -- so "
        "there's no shapefile/interactive-map deliverable for this board's signs "
        "the way there is for the deployed dataset. What you just saw is a simple "
        "HTML summary of the raw model output, not that.",
        [
            "the HTML report just opened, with per-box crops + damage classifications",
            "physical_report_lib.py's shapefile-writing helpers, if this gets built out later",
        ],
    ))


def launch_servers() -> list:
    """Starts the three local servers the annotation tool needs, each in
    its own visible console window (so the operator can see their logs
    and stop them by closing the window, same as double-clicking the
    .bat files by hand). The annotation server's .bat file opens the
    tool in the default browser.
    Returns the Popen handles (unused today, but keeps the door open for
    the caller to check .poll() later without re-deriving them)."""
    bat_files = [
        SCRIPT_DIR.parent / "annotation_tool" / "start_annotation_server.bat",
        SCRIPT_DIR.parent / "start_tight_crop_server.bat",
        SCRIPT_DIR.parent / "start_model_server.bat",
    ]
    procs = [
        subprocess.Popen([str(bat)], creationflags=subprocess.CREATE_NEW_CONSOLE)
        for bat in bat_files
    ]
    return procs


def prompt_annotation_csv() -> str:
    input("\nAnnotate in the browser tab that just opened. When you've clicked "
          "Export CSV, press Enter here.")
    while True:
        raw = input("Path to the exported CSV: ").strip().strip('"')
        ok, message = core.validate_annotation_csv(raw)
        if ok:
            return raw
        print(f"  {message}")


def run_manual_branch(boro_cd: str) -> None:
    print("\nLaunching annotation tool servers and opening your browser...")
    launch_servers()
    csv_path = prompt_annotation_csv()

    print("\nBackfilling tight crops for any box saved before the servers were up...")
    run_step(core.build_backfill_command(csv_path))
    backfilled_csv = core.backfilled_csv_path(csv_path)

    print("\nBuilding the physical-model training dataset from your annotations...")
    run_step(core.build_prepare_physical_command([backfilled_csv]))

    answer = input("\nTrain on this dataset now? This will NOT touch the deployed model "
                    "or its dataset. [y/N]: ").strip().lower()
    if answer != "y":
        print("Skipping training. Nothing more to do -- run the shell again once you've "
              "annotated more to build a larger dataset.")
        return

    train_physical_from_annotations(boro_cd)

    print(core.section_missing(
        "Report/shapefile scoped to this Community Board's own signs",
        "report_physical.py only ever evaluates against its own hardcoded "
        "data/yolo_dataset_physical/images/{train,val} -- it doesn't run "
        "inference over arbitrary new imagery. There's no existing way to get "
        "a report scoped to this board's signs without either merging this "
        "run's dataset into the deployed one (a deliberate decision, not this "
        "shell's call) or modifying the production report script.",
        [
            "the training run's own metrics, printed above",
            "report_physical.py's shapefile-writing helpers, if this gets built out later",
        ],
    ))


def train_physical_from_annotations(boro_cd: str) -> None:
    from datetime import datetime
    from ultralytics import YOLO

    run_name = core.training_run_name(core.board_label(boro_cd), datetime.now())
    kwargs = core.training_kwargs(
        "../yolo/data_physical_from_annotations.yaml",
        str(SCRIPT_DIR.parent / "yolo" / "runs_physical_shell"),
        run_name,
    )
    print(f"\nTraining run '{run_name}'...")
    model = YOLO(str(SCRIPT_DIR.parent / "yolo26n.pt"))
    results = model.train(**kwargs)
    print("\n=== FINAL METRICS ===")
    print("mAP50:", results.results_dict.get("metrics/mAP50(B)"))
    print("mAP50-95:", results.results_dict.get("metrics/mAP50-95(B)"))


if __name__ == "__main__":
    main()
