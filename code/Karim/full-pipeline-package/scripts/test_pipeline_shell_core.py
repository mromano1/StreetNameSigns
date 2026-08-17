import json
import sys
from pathlib import Path

import pipeline_shell_core as core


def test_board_label_prefixes_boro_cd_with_cb():
    assert core.board_label("304") == "cb304"


def test_dataset_dir_is_a_subfolder_of_cyclomedia_panoramas():
    assert core.dataset_dir("304") == "../data/cyclomedia_panoramas/cb304"


def test_signs_csv_filename_matches_the_query_scripts_own_naming():
    # Must match 01_query_sims_by_community_board.py's own
    # output_filename()/board_output_label() convention exactly, since
    # that script -- not this one -- decides the real filename.
    assert core.signs_csv_filename("304") == "signs_zip_cb304.csv"


def test_signs_data_path_is_co_located_inside_the_dataset_dir():
    # Co-located with fetch_manifest.json inside the dataset folder, not a
    # sibling file at the panoramas root -- list_panorama_datasets.py's
    # signs-file discovery (added today) only looks inside each
    # subfolder.
    assert core.signs_data_path("304") == "../data/cyclomedia_panoramas/cb304/signs_data.json"


def test_section_missing_includes_name_why_and_what_exists():
    banner = core.section_missing(
        "Automatic box detection",
        "No script runs spatial-model inference over fresh panoramas yet.",
        ["today's sanity-check spatial model", "serve_physical_model.py's /predict endpoint"],
    )
    assert "SECTION MISSING: Automatic box detection" in banner
    assert "No script runs spatial-model inference over fresh panoramas yet." in banner
    assert "today's sanity-check spatial model" in banner
    assert "serve_physical_model.py's /predict endpoint" in banner


def test_section_missing_returns_a_string_not_none():
    # Formatter only -- pipeline_shell.py does the printing, so this must
    # return the banner rather than print it directly (keeps it testable
    # without capturing stdout).
    result = core.section_missing("X", "why", [])
    assert isinstance(result, str)


def test_build_query_command():
    assert core.build_query_command("304") == [
        sys.executable, "01_query_sims_by_community_board.py", "304",
    ]


def test_build_generate_signs_data_command():
    assert core.build_generate_signs_data_command("304") == [
        sys.executable, "02_generate_signs_data.py", "cb304",
        "--csv", "signs_zip_cb304.csv",
        "--out", "../data/cyclomedia_panoramas/cb304/signs_data.json",
    ]


def test_build_fetch_panoramas_command():
    assert core.build_fetch_panoramas_command("304") == [
        sys.executable, "fetch_cyclomedia_panoramas.py",
        "../data/cyclomedia_panoramas/cb304/signs_data.json",
        "--output-dir", "../data/cyclomedia_panoramas/cb304",
    ]


def test_build_fetch_panoramas_command_with_limit():
    assert core.build_fetch_panoramas_command("304", limit=50) == [
        sys.executable, "fetch_cyclomedia_panoramas.py",
        "../data/cyclomedia_panoramas/cb304/signs_data.json",
        "--output-dir", "../data/cyclomedia_panoramas/cb304",
        "--limit", "50",
    ]


def test_build_fetch_panoramas_command_with_multi_angle():
    assert core.build_fetch_panoramas_command("304", multi_angle=True) == [
        sys.executable, "fetch_cyclomedia_panoramas.py",
        "../data/cyclomedia_panoramas/cb304/signs_data.json",
        "--output-dir", "../data/cyclomedia_panoramas/cb304",
        "--multi-angle",
    ]


def test_build_fetch_panoramas_command_with_limit_and_multi_angle():
    assert core.build_fetch_panoramas_command("304", limit=50, multi_angle=True) == [
        sys.executable, "fetch_cyclomedia_panoramas.py",
        "../data/cyclomedia_panoramas/cb304/signs_data.json",
        "--output-dir", "../data/cyclomedia_panoramas/cb304",
        "--limit", "50",
        "--multi-angle",
    ]


def test_build_list_datasets_command():
    assert core.build_list_datasets_command() == [sys.executable, "list_panorama_datasets.py"]


def test_build_backfill_command():
    assert core.build_backfill_command("some/annotations.csv") == [
        sys.executable, "backfill_tight_crops.py", "some/annotations.csv",
    ]


def test_build_prepare_physical_command_accepts_multiple_csvs():
    assert core.build_prepare_physical_command(["a.csv", "b.csv"]) == [
        sys.executable, "prepare_physical_dataset_from_annotations.py", "a.csv", "b.csv",
    ]


from datetime import datetime


ANNOTATION_CSV_HEADER = (
    "source_image,image_kind,corner_id,box_index,bbox_x,bbox_y,bbox_w,bbox_h,"
    "image_width,image_height,order_number,sign_code,sign_location,damage_category,"
    "notes,tight_crop_path,flagged,annotated_at"
)


def test_validate_annotation_csv_accepts_a_real_annotation_export(tmp_path):
    csv_path = tmp_path / "annotations.csv"
    csv_path.write_text(ANNOTATION_CSV_HEADER + "\n")
    ok, message = core.validate_annotation_csv(str(csv_path))
    assert ok is True
    assert message == ""


def test_validate_annotation_csv_rejects_a_missing_file(tmp_path):
    ok, message = core.validate_annotation_csv(str(tmp_path / "nope.csv"))
    assert ok is False
    assert "not found" in message.lower()


def test_validate_annotation_csv_rejects_wrong_header(tmp_path):
    csv_path = tmp_path / "wrong.csv"
    csv_path.write_text("a,b,c\n")
    ok, message = core.validate_annotation_csv(str(csv_path))
    assert ok is False
    assert "header" in message.lower()


def test_validate_annotation_csv_rejects_a_directory_path(tmp_path):
    ok, message = core.validate_annotation_csv(str(tmp_path))
    assert ok is False
    assert "not a file" in message.lower()


def test_training_run_name_includes_board_label_and_timestamp():
    now = datetime(2026, 8, 13, 14, 30, 0)
    assert core.training_run_name("cb304", now) == "shell_cb304_20260813_143000"


def test_training_kwargs_points_at_the_given_data_yaml_and_runs_dir():
    kwargs = core.training_kwargs(
        "../yolo/data_physical_from_annotations.yaml", "../yolo/runs_physical_shell", "shell_cb304_20260813_143000",
    )
    assert kwargs["data"] == "../yolo/data_physical_from_annotations.yaml"
    assert kwargs["project"] == "../yolo/runs_physical_shell"
    assert kwargs["name"] == "shell_cb304_20260813_143000"
    assert kwargs["exist_ok"] is True


def test_backfilled_csv_path_matches_backfill_tight_crops_naming():
    # Compared via Path, not a hardcoded "/"-joined literal, so this
    # passes on Windows too, where Path.with_name() (the exact mechanism
    # backfill_tight_crops.py's own out_path uses) renders with "\\".
    expected = str(Path("some/annotations.csv").with_name("annotations_with_tight_crops.csv"))
    assert core.backfilled_csv_path("some/annotations.csv") == expected


def _write_manifest(dir_path, jobs):
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "fetch_manifest.json").write_text(json.dumps({"jobs": jobs}))


def test_list_available_datasets_counts_ok_and_skipped_but_not_failed(tmp_path):
    # "skipped" means fetch_cyclomedia_panoramas.py found the file already
    # on disk from an earlier run and didn't re-fetch it -- the file is
    # just as real as an "ok" one (real bug, found live 2026-08-14: a
    # dataset re-fetched after already being complete had every job
    # flip from "ok" to "skipped", and this then showed "0 image(s)" for
    # a folder that actually had hundreds of real files in it).
    _write_manifest(tmp_path, [
        {"status": "ok"}, {"status": "skipped"}, {"status": "failed"},
    ])
    datasets = core.list_available_datasets(tmp_path)
    assert datasets == [{"label": "original", "image_count": 2}]


def test_list_available_datasets_includes_subfolder_pulls(tmp_path):
    _write_manifest(tmp_path, [{"status": "ok"}])
    _write_manifest(tmp_path / "demo_cb301", [{"status": "ok"}] * 50)
    datasets = core.list_available_datasets(tmp_path)
    assert {"label": "original", "image_count": 1} in datasets
    assert {"label": "demo_cb301", "image_count": 50} in datasets


def test_list_available_datasets_sorts_original_first(tmp_path):
    _write_manifest(tmp_path, [{"status": "ok"}])
    _write_manifest(tmp_path / "zzz", [{"status": "ok"}])
    _write_manifest(tmp_path / "aaa", [{"status": "ok"}])
    datasets = core.list_available_datasets(tmp_path)
    assert [d["label"] for d in datasets] == ["original", "aaa", "zzz"]


def test_list_available_datasets_empty_dir_returns_empty_list(tmp_path):
    assert core.list_available_datasets(tmp_path) == []
