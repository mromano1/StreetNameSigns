import base64
import csv
import struct
from pathlib import Path

import physical_report_lib as lib
import shapefile as pyshp


def test_write_shapefile_writes_points_and_fields(tmp_path):
    records = [
        {
            "x": 990862.0, "y": 211362.0, "order_numbers": "ST1", "sign_codes": "SN-1A",
            "corner_id": "10001_000", "predicted_classes": "faded", "confidences": "0.81",
            "human_label": "faded", "filename": "a.jpg", "capture_date": "2026-07-15",
        },
        {
            "x": 990900.0, "y": 211400.0, "order_numbers": "ST2", "sign_codes": "SN-2A",
            "corner_id": "10001_001", "predicted_classes": "old_design", "confidences": "0.60",
            "human_label": "old_design", "filename": "b.jpg", "capture_date": "2026-07-16",
        },
    ]
    out_path = tmp_path / "test_report.shp"

    lib.write_shapefile(records, out_path)

    reader = pyshp.Reader(str(out_path))
    shape_records = reader.shapeRecords()
    assert len(shape_records) == 2
    first = shape_records[0]
    assert first.shape.points[0] == (990862.0, 211362.0)
    as_dict = first.record.as_dict()
    assert as_dict["order_num"] == "ST1"
    assert as_dict["pred_class"] == "faded"
    reader.close()

    prj_path = out_path.with_suffix(".prj")
    assert prj_path.exists()
    assert "EPSG:2263" not in prj_path.read_text()  # ESRI WKT has no literal "EPSG:2263" string
    assert "New_York_Long_Island" in prj_path.read_text()


def test_write_shapefile_field_names_fit_dbf_limit():
    for _dict_key, dbf_name in lib.SHAPEFILE_FIELDS:
        assert len(dbf_name) <= 10, f"{dbf_name!r} exceeds the 10-char DBF field name limit"


def test_write_shapefile_handles_empty_records(tmp_path):
    out_path = tmp_path / "empty_report.shp"

    lib.write_shapefile([], out_path)

    reader = pyshp.Reader(str(out_path))
    assert len(reader.shapeRecords()) == 0
    reader.close()


def test_reproject_matches_known_point():
    # Same test point as test_cyclomedia_auth.py: Madison Ave & E 39th St.
    x, y = lib.reproject_lat_lon_to_2263(40.746814, -73.976137)
    assert abs(x - 990862) < 2
    assert abs(y - 211362) < 2


def test_build_shapefile_record_returns_none_below_threshold():
    row = {"latitude": "40.746814", "longitude": "-73.976137"}
    record = lib.build_shapefile_record(row, [("faded", 0.1)], threshold=0.25)
    assert record is None


def test_build_shapefile_record_returns_record_above_threshold():
    row = {
        "latitude": "40.746814", "longitude": "-73.976137",
        "order_numbers": "ST01647077", "sign_codes": "SN-749A",
        "corner_id": "10001_609", "damage_category": "faded",
        "filename": "a.jpg", "timestamp": "2026-07-15T00:13:21.623Z",
    }
    record = lib.build_shapefile_record(row, [("faded", 0.81)], threshold=0.25)
    assert record["predicted_classes"] == "faded"
    assert record["confidences"] == "0.81"
    assert record["order_numbers"] == "ST01647077"
    assert record["sign_codes"] == "SN-749A"
    assert record["corner_id"] == "10001_609"
    assert record["human_label"] == "faded"
    assert record["filename"] == "a.jpg"
    assert record["capture_date"] == "2026-07-15"
    assert abs(record["x"] - 990862) < 2
    assert abs(record["y"] - 211362) < 2


def test_build_shapefile_record_includes_latitude_longitude():
    row = {
        "latitude": "40.746814", "longitude": "-73.976137",
        "filename": "a.jpg",
    }
    record = lib.build_shapefile_record(row, [("faded", 0.81)], threshold=0.25)
    assert record["latitude"] == 40.746814
    assert record["longitude"] == -73.976137


def test_build_shapefile_record_joins_multiple_predictions():
    row = {"latitude": "40.746814", "longitude": "-73.976137"}
    record = lib.build_shapefile_record(
        row, [("faded", 0.81), ("old_design", 0.5)], threshold=0.25
    )
    assert record["predicted_classes"] == "faded;old_design"
    assert record["confidences"] == "0.81;0.50"


def test_build_shapefile_record_drops_predictions_below_threshold_individually():
    row = {"latitude": "40.746814", "longitude": "-73.976137"}
    record = lib.build_shapefile_record(
        row, [("faded", 0.81), ("old_design", 0.1)], threshold=0.25
    )
    assert record["predicted_classes"] == "faded"


def test_build_shapefile_record_returns_none_when_coordinates_missing():
    # External seed images and some manual-capture batches have no
    # latitude/longitude recorded; such rows can't be placed on a map.
    row = {"latitude": "", "longitude": ""}
    record = lib.build_shapefile_record(row, [("faded", 0.81)], threshold=0.25)
    assert record is None


def test_build_shapefile_record_dedupes_duplicate_class_predictions():
    # The model can emit more than one overlapping detection box for the
    # same class on a single-sign image -- these should collapse to one
    # entry, not show up as "old_design;old_design".
    row = {"latitude": "40.746814", "longitude": "-73.976137"}
    record = lib.build_shapefile_record(
        row, [("old_design", 0.81), ("old_design", 0.60)], threshold=0.25
    )
    assert record["predicted_classes"] == "old_design"
    assert record["confidences"] == "0.81"


def test_build_shapefile_record_dedupe_keeps_highest_confidence():
    row = {"latitude": "40.746814", "longitude": "-73.976137"}
    record = lib.build_shapefile_record(
        row, [("old_design", 0.40), ("old_design", 0.90)], threshold=0.25
    )
    assert record["confidences"] == "0.90"


def test_build_shapefile_record_dedupe_preserves_distinct_classes():
    row = {"latitude": "40.746814", "longitude": "-73.976137"}
    record = lib.build_shapefile_record(
        row, [("old_design", 0.81), ("faded", 0.5), ("old_design", 0.3)], threshold=0.25
    )
    assert record["predicted_classes"] == "old_design;faded"
    assert record["confidences"] == "0.81;0.50"


def test_physical_class_colors_has_an_entry_per_class():
    for cls in lib.PHYSICAL_CLASS_NAMES:
        assert cls in lib.PHYSICAL_CLASS_COLORS
        assert lib.PHYSICAL_CLASS_COLORS[cls] != lib.DEFAULT_CLASS_COLOR


def test_physical_class_colors_are_all_distinct():
    colors = list(lib.PHYSICAL_CLASS_COLORS.values())
    assert len(colors) == len(set(colors))


def test_select_diverse_sample_paths_spreads_across_categories():
    paths = [Path(f"{i}.jpg") for i in range(4)]
    rows = {
        "0.jpg": {"damage_category": "old_design"},
        "1.jpg": {"damage_category": "old_design"},
        "2.jpg": {"damage_category": "faded"},
        "3.jpg": {"damage_category": "bent_damaged"},
    }
    selected = lib.select_diverse_sample_paths(paths, rows, n_samples=3)
    categories = [rows[p.name]["damage_category"] for p in selected]
    assert set(categories) == {"old_design", "faded", "bent_damaged"}


def test_select_diverse_sample_paths_round_robins_in_first_seen_order():
    paths = [Path(f"{i}.jpg") for i in range(5)]
    rows = {
        "0.jpg": {"damage_category": "old_design"},
        "1.jpg": {"damage_category": "old_design"},
        "2.jpg": {"damage_category": "old_design"},
        "3.jpg": {"damage_category": "faded"},
        "4.jpg": {"damage_category": "faded"},
    }
    selected = lib.select_diverse_sample_paths(paths, rows, n_samples=4)
    assert [p.name for p in selected] == ["0.jpg", "3.jpg", "1.jpg", "4.jpg"]


def test_select_diverse_sample_paths_buckets_multi_label_by_first_token():
    paths = [Path("a.jpg"), Path("b.jpg")]
    rows = {
        "a.jpg": {"damage_category": "old_design;hanging"},
        "b.jpg": {"damage_category": "faded"},
    }
    selected = lib.select_diverse_sample_paths(paths, rows, n_samples=2)
    assert len(selected) == 2


def test_select_diverse_sample_paths_handles_missing_row_and_blank_category():
    paths = [Path("known.jpg"), Path("unknown.jpg")]
    rows = {"known.jpg": {"damage_category": "faded"}}
    selected = lib.select_diverse_sample_paths(paths, rows, n_samples=2)
    assert len(selected) == 2


def test_select_diverse_sample_paths_caps_at_n_samples():
    paths = [Path(f"{i}.jpg") for i in range(10)]
    rows = {f"{i}.jpg": {"damage_category": "faded"} for i in range(10)}
    selected = lib.select_diverse_sample_paths(paths, rows, n_samples=3)
    assert len(selected) == 3


def test_select_diverse_sample_paths_returns_fewer_than_n_if_not_enough_images():
    paths = [Path("a.jpg"), Path("b.jpg")]
    rows = {"a.jpg": {"damage_category": "faded"}, "b.jpg": {"damage_category": "old_design"}}
    selected = lib.select_diverse_sample_paths(paths, rows, n_samples=5)
    assert len(selected) == 2


def test_build_run_history_row_fills_all_class_columns():
    row = lib.build_run_history_row(
        run_name="street_sign_physical_2026-07-29",
        date_str="2026-07-29",
        class_counts={"no_damage": 10, "faded": 5},
        precision=0.6, recall=0.5, map50=0.4, map50_95=0.3,
    )
    assert row["run_name"] == "street_sign_physical_2026-07-29"
    assert row["no_damage"] == 10
    assert row["faded"] == 5
    assert row["old_design"] == 0
    assert row["bent_damaged"] == 0
    assert row["hanging"] == 0
    assert row["vandalized"] == 0
    assert row["total_images"] == 15
    assert row["precision"] == 0.6


def test_append_run_history_writes_header_once(tmp_path):
    csv_path = tmp_path / "PHYSICAL_RUN_HISTORY.csv"
    row1 = lib.build_run_history_row(
        "run1", "2026-07-28", {"no_damage": 1}, 0.1, 0.1, 0.1, 0.1
    )
    row2 = lib.build_run_history_row(
        "run2", "2026-07-29", {"faded": 2}, 0.2, 0.2, 0.2, 0.2
    )

    lib.append_run_history(row1, csv_path)
    lib.append_run_history(row2, csv_path)

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]["run_name"] == "run1"
    assert rows[1]["run_name"] == "run2"


def test_load_last_two_runs_returns_none_none_when_no_file(tmp_path):
    result = lib.load_last_two_runs(tmp_path / "missing.csv")
    assert result == (None, None)


def test_load_last_two_runs_returns_row_none_with_one_row(tmp_path):
    csv_path = tmp_path / "history.csv"
    row = lib.build_run_history_row("run1", "2026-08-01", {"no_damage": 5}, 0.8, 0.7, 0.75, 0.5)
    lib.append_run_history(row, csv_path)

    last_row, previous_row = lib.load_last_two_runs(csv_path)

    assert last_row["run_name"] == "run1"
    assert previous_row is None


def test_load_last_two_runs_returns_last_and_previous_with_multiple_rows(tmp_path):
    csv_path = tmp_path / "history.csv"
    row1 = lib.build_run_history_row("run1", "2026-08-01", {"no_damage": 5}, 0.8, 0.7, 0.75, 0.5)
    row2 = lib.build_run_history_row("run2", "2026-08-02", {"no_damage": 6}, 0.9, 0.8, 0.85, 0.6)
    lib.append_run_history(row1, csv_path)
    lib.append_run_history(row2, csv_path)

    last_row, previous_row = lib.load_last_two_runs(csv_path)

    assert last_row["run_name"] == "run2"
    assert previous_row["run_name"] == "run1"


def test_build_class_metrics_rows_maps_summary_entries(tmp_path):
    summary = [
        {"Class": "faded", "Images": 5, "Instances": 5, "Box-P": 0.9, "Box-R": 0.8, "Box-F1": 0.85, "mAP50": 0.75, "mAP50-95": 0.5},
        {"Class": "hanging", "Images": 2, "Instances": 2, "Box-P": 0.6, "Box-R": 0.4, "Box-F1": 0.48, "mAP50": 0.3, "mAP50-95": 0.2},
    ]

    rows = lib.build_class_metrics_rows("run1", "2026-08-03", summary)

    assert rows == [
        {"run_name": "run1", "date": "2026-08-03", "class_name": "faded", "precision": 0.9, "recall": 0.8, "mAP50": 0.75, "mAP50_95": 0.5},
        {"run_name": "run1", "date": "2026-08-03", "class_name": "hanging", "precision": 0.6, "recall": 0.4, "mAP50": 0.3, "mAP50_95": 0.2},
    ]


def test_build_class_metrics_rows_handles_empty_summary():
    assert lib.build_class_metrics_rows("run1", "2026-08-03", []) == []


def test_append_class_metrics_writes_header_once(tmp_path):
    csv_path = tmp_path / "class_metrics.csv"
    rows1 = lib.build_class_metrics_rows("run1", "2026-08-03", [
        {"Class": "faded", "Box-P": 0.9, "Box-R": 0.8, "mAP50": 0.75, "mAP50-95": 0.5},
    ])
    rows2 = lib.build_class_metrics_rows("run2", "2026-08-04", [
        {"Class": "faded", "Box-P": 0.95, "Box-R": 0.85, "mAP50": 0.8, "mAP50-95": 0.55},
    ])

    lib.append_class_metrics(rows1, csv_path)
    lib.append_class_metrics(rows2, csv_path)

    with open(csv_path, newline="", encoding="utf-8") as f:
        written = list(csv.DictReader(f))
    assert len(written) == 2
    assert written[0]["run_name"] == "run1"
    assert written[1]["run_name"] == "run2"


def test_load_class_metrics_last_two_runs_returns_empty_dict_when_no_file(tmp_path):
    assert lib.load_class_metrics_last_two_runs(tmp_path / "missing.csv") == {}


def test_load_class_metrics_last_two_runs_pairs_matching_classes(tmp_path):
    csv_path = tmp_path / "class_metrics.csv"
    lib.append_class_metrics(
        lib.build_class_metrics_rows("run1", "2026-08-03", [
            {"Class": "faded", "Box-P": 0.7, "Box-R": 0.6, "mAP50": 0.65, "mAP50-95": 0.4},
            {"Class": "hanging", "Box-P": 0.5, "Box-R": 0.5, "mAP50": 0.5, "mAP50-95": 0.3},
        ]),
        csv_path,
    )
    lib.append_class_metrics(
        lib.build_class_metrics_rows("run2", "2026-08-04", [
            {"Class": "faded", "Box-P": 0.9, "Box-R": 0.8, "mAP50": 0.75, "mAP50-95": 0.5},
        ]),
        csv_path,
    )

    result = lib.load_class_metrics_last_two_runs(csv_path)

    assert set(result.keys()) == {"faded"}
    last_row, previous_row = result["faded"]
    assert last_row["run_name"] == "run2"
    assert last_row["precision"] == "0.9"
    assert previous_row["run_name"] == "run1"
    assert previous_row["precision"] == "0.7"


def test_load_class_metrics_last_two_runs_previous_none_for_class_new_to_last_run(tmp_path):
    csv_path = tmp_path / "class_metrics.csv"
    lib.append_class_metrics(
        lib.build_class_metrics_rows("run1", "2026-08-03", [
            {"Class": "faded", "Box-P": 0.7, "Box-R": 0.6, "mAP50": 0.65, "mAP50-95": 0.4},
        ]),
        csv_path,
    )
    lib.append_class_metrics(
        lib.build_class_metrics_rows("run2", "2026-08-04", [
            {"Class": "faded", "Box-P": 0.9, "Box-R": 0.8, "mAP50": 0.75, "mAP50-95": 0.5},
            {"Class": "vandalized", "Box-P": 1.0, "Box-R": 1.0, "mAP50": 1.0, "mAP50-95": 1.0},
        ]),
        csv_path,
    )

    result = lib.load_class_metrics_last_two_runs(csv_path)

    assert set(result.keys()) == {"faded", "vandalized"}
    assert result["vandalized"][1] is None  # no "vandalized" row in run1


def test_resolve_report_path_returns_path_when_report_exists(tmp_path):
    (tmp_path / "physical_condition_run1.html").write_text("<html>report</html>", encoding="utf-8")

    result = lib.resolve_report_path(tmp_path, "run1")

    assert result is not None
    assert result.name == "physical_condition_run1.html"
    assert result.read_text(encoding="utf-8") == "<html>report</html>"


def test_resolve_report_path_returns_none_when_report_missing(tmp_path):
    result = lib.resolve_report_path(tmp_path, "does-not-exist")
    assert result is None


def test_resolve_report_path_rejects_traversal_outside_reports_dir(tmp_path):
    # run_name = "a/../../secret" resolves (after the "physical_condition_"
    # filename prefix fuses onto its first segment) to reports_dir's
    # PARENT directory -- a genuine escape, not just a nonexistent path
    # inside reports_dir. The secret file is placed at exactly that
    # location so this test would only pass by accident if the
    # relative_to() containment check were ever removed or broken.
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    outside_secret = tmp_path / "secret.html"
    outside_secret.write_text("<html>secret</html>", encoding="utf-8")

    result = lib.resolve_report_path(reports_dir, "a/../../secret")

    assert result is None


def test_resolve_report_path_returns_none_for_null_byte_run_name(tmp_path):
    result = lib.resolve_report_path(tmp_path, "evil\x00")
    assert result is None


def test_count_classes_in_dataset_counts_by_first_label_and_negatives(tmp_path):
    train_dir = tmp_path / "labels" / "train"
    val_dir = tmp_path / "labels" / "val"
    train_dir.mkdir(parents=True)
    val_dir.mkdir(parents=True)
    (train_dir / "a.txt").write_text("1 0.5 0.5 0.9 0.9\n")  # class id 1 = faded
    (train_dir / "b.txt").write_text("")  # negative
    (val_dir / "c.txt").write_text("0 0.5 0.5 0.9 0.9\n")  # class id 0 = old_design

    counts = lib.count_classes_in_dataset(
        train_dir, val_dir,
        ["old_design", "faded", "bent_damaged", "hanging", "vandalized"],
    )

    assert counts == {"faded": 1, "no_damage": 1, "old_design": 1}


def test_count_classes_by_split_keeps_train_and_val_separate(tmp_path):
    train_dir = tmp_path / "labels" / "train"
    val_dir = tmp_path / "labels" / "val"
    train_dir.mkdir(parents=True)
    val_dir.mkdir(parents=True)
    (train_dir / "a.txt").write_text("1 0.5 0.5 0.9 0.9\n")  # class id 1 = faded
    (train_dir / "b.txt").write_text("")  # negative
    (val_dir / "c.txt").write_text("0 0.5 0.5 0.9 0.9\n")  # class id 0 = old_design

    result = lib.count_classes_by_split(
        train_dir, val_dir,
        ["old_design", "faded", "bent_damaged", "hanging", "vandalized"],
    )

    assert result == {
        "train": {"faded": 1, "no_damage": 1},
        "val": {"old_design": 1},
    }


def test_count_classes_by_split_omits_class_absent_from_a_split(tmp_path):
    train_dir = tmp_path / "labels" / "train"
    val_dir = tmp_path / "labels" / "val"
    train_dir.mkdir(parents=True)
    val_dir.mkdir(parents=True)
    (train_dir / "a.txt").write_text("1 0.5 0.5 0.9 0.9\n")  # faded, only in train

    result = lib.count_classes_by_split(
        train_dir, val_dir,
        ["old_design", "faded", "bent_damaged", "hanging", "vandalized"],
    )

    assert "faded" not in result["val"]
    assert result["val"] == {}


def test_encode_image_base64_roundtrips():
    raw = b"\x00\x01\x02fake jpeg bytes"
    encoded = lib.encode_image_base64(raw)
    assert base64.b64decode(encoded) == raw


def test_render_history_chart_base64_produces_valid_png():
    history_rows = [
        {"date": "2026-07-28", "mAP50": "0.3", "mAP50_95": "0.2"},
        {"date": "2026-07-29", "mAP50": "0.4", "mAP50_95": "0.3"},
    ]
    encoded = lib.render_history_chart_base64(history_rows)
    png_bytes = base64.b64decode(encoded)
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_report_html_includes_key_content():
    context = {
        "run_name": "street_sign_physical_2026-07-29",
        "run_date": "2026-07-29",
        "metrics": {"precision": "0.6", "recall": "0.5", "mAP50": "0.4", "mAP50_95": "0.3"},
        "class_counts_by_split": {
            "train": {"no_damage": 8, "old_design": 4, "faded": 2},
            "val": {"no_damage": 2, "old_design": 1, "faded": 1},
        },
        "class_metrics": {
            "faded": ({"precision": "0.81", "recall": "0.7", "mAP50": "0.75", "mAP50_95": "0.6"}, None),
        },
        "history_chart_b64": base64.b64encode(b"\x89PNG\r\n\x1a\nrest").decode("ascii"),
        "samples": [
            {"annotated_b64": base64.b64encode(b"jpegbytes").decode("ascii"),
             "predicted": "faded:0.81", "human": "faded", "filename": "a.jpg"},
        ],
        "flagged_count_val": 3,
        "flagged_count_all": 12,
    }

    html = lib.render_report_html(context)

    assert "street_sign_physical_2026-07-29" in html
    assert "0.6" in html
    assert "faded:0.81" in html
    assert "a.jpg" in html
    assert "3" in html and "12" in html
    assert "Training Set" in html
    assert "Testing Set" in html
    assert "Total" in html


def test_render_report_html_embeds_map_iframe_when_present():
    context = {
        "run_name": "run1", "run_date": "2026-07-29",
        "metrics": {"precision": "0.6", "recall": "0.5", "mAP50": "0.4", "mAP50_95": "0.3"},
        "class_counts_by_split": {"train": {}, "val": {}},
        "class_metrics": {},
        "history_chart_b64": "", "samples": [],
        "flagged_count_val": 0, "flagged_count_all": 0,
        "map_doc_html": "<html><body>fake map content</body></html>",
    }

    html_out = lib.render_report_html(context)

    assert "<iframe" in html_out
    assert "fake map content" in html_out
    assert "No flagged signs to map" not in html_out


def test_render_report_html_shows_placeholder_when_no_map():
    context = {
        "run_name": "run1", "run_date": "2026-07-29",
        "metrics": {"precision": "0.6", "recall": "0.5", "mAP50": "0.4", "mAP50_95": "0.3"},
        "class_counts_by_split": {"train": {}, "val": {}},
        "class_metrics": {},
        "history_chart_b64": "", "samples": [],
        "flagged_count_val": 0, "flagged_count_all": 0,
        "map_doc_html": None,
    }

    html_out = lib.render_report_html(context)

    assert "No flagged signs to map" in html_out
    assert "<iframe" not in html_out


def test_render_report_html_dataset_table_sums_train_and_val_for_total():
    context = {
        "run_name": "run1",
        "run_date": "2026-07-29",
        "metrics": {"precision": "0.6", "recall": "0.5", "mAP50": "0.4", "mAP50_95": "0.3"},
        "class_counts_by_split": {
            "train": {"no_damage": 8, "faded": 2},
            "val": {"no_damage": 2, "old_design": 1},
        },
        "class_metrics": {},
        "history_chart_b64": "",
        "samples": [],
        "flagged_count_val": 0,
        "flagged_count_all": 0,
    }

    html = lib.render_report_html(context)

    # no_damage: 8 (train) + 2 (val) = 10; faded: 2 + 0 = 2; old_design: 0 + 1 = 1
    assert "<td>10</td>" in html
    assert "<td>2</td>" in html
    assert "<td>1</td>" in html


def test_render_report_html_dataset_table_headers_are_damage_types():
    context = {
        "run_name": "run1",
        "run_date": "2026-07-29",
        "metrics": {"precision": "0.6", "recall": "0.5", "mAP50": "0.4", "mAP50_95": "0.3"},
        "class_counts_by_split": {"train": {}, "val": {}},
        "class_metrics": {},
        "history_chart_b64": "",
        "samples": [],
        "flagged_count_val": 0,
        "flagged_count_all": 0,
    }

    html = lib.render_report_html(context)

    for cls in ["no_damage", "old_design", "faded", "bent_damaged", "hanging", "vandalized"]:
        assert f"<th>{cls}</th>" in html


def test_render_report_html_class_metrics_table_shows_precision_recall_map():
    context = {
        "run_name": "run1",
        "run_date": "2026-07-29",
        "metrics": {"precision": "0.6", "recall": "0.5", "mAP50": "0.4", "mAP50_95": "0.3"},
        "class_counts_by_split": {"train": {}, "val": {}},
        "class_metrics": {
            "faded": (
                {"precision": "0.81", "recall": "0.7", "mAP50": "0.75", "mAP50_95": "0.6"},
                None,
            ),
        },
        "history_chart_b64": "",
        "samples": [],
        "flagged_count_val": 0,
        "flagged_count_all": 0,
    }

    html = lib.render_report_html(context)

    assert "Accuracy by damage type" in html
    assert "<td>0.810</td>" in html
    assert "<td>0.700</td>" in html
    assert "<td>0.750</td>" in html
    assert "<td>0.600</td>" in html


def test_render_report_html_class_metrics_table_lists_every_damage_type():
    context = {
        "run_name": "run1",
        "run_date": "2026-07-29",
        "metrics": {"precision": "0.6", "recall": "0.5", "mAP50": "0.4", "mAP50_95": "0.3"},
        "class_counts_by_split": {"train": {}, "val": {}},
        "class_metrics": {},
        "history_chart_b64": "",
        "samples": [],
        "flagged_count_val": 0,
        "flagged_count_all": 0,
    }

    html = lib.render_report_html(context)

    for cls in lib.PHYSICAL_CLASS_NAMES:
        assert f"<td>{cls}</td>" in html


def test_render_report_html_class_metrics_table_never_fabricates_zero_for_absent_class():
    """A class absent from class_metrics (zero validation examples this run)
    must show a "no examples this run" marker, never a numeric 0 -- a 0
    would misleadingly read as "0% accuracy" rather than "no data",
    matching the project's established "absent, not zero" convention for
    per-class metrics."""
    context = {
        "run_name": "run1",
        "run_date": "2026-07-29",
        "metrics": {"precision": "0.6", "recall": "0.5", "mAP50": "0.4", "mAP50_95": "0.3"},
        "class_counts_by_split": {"train": {}, "val": {}},
        "class_metrics": {},
        "history_chart_b64": "",
        "samples": [],
        "flagged_count_val": 0,
        "flagged_count_all": 0,
    }

    html = lib.render_report_html(context)

    assert "no examples this run" in html
    assert "<td>0.000</td>" not in html


def test_shapefile_row_to_record_maps_dbf_names_back_to_dict_keys():
    row = {
        "order_num": "ST1", "sign_codes": "SN-1A", "corner_id": "10001_000",
        "pred_class": "faded", "confidence": "0.81", "human_lbl": "faded",
        "filename": "a.jpg", "cap_date": "2026-07-15",
    }
    record = lib.shapefile_row_to_record(row)
    assert record["order_numbers"] == "ST1"
    assert record["predicted_classes"] == "faded"
    assert record["confidences"] == "0.81"
    assert record["human_label"] == "faded"
    assert record["filename"] == "a.jpg"
    assert record["capture_date"] == "2026-07-15"


def test_shapefile_row_to_record_defaults_missing_fields_to_empty_string():
    record = lib.shapefile_row_to_record({})
    assert record["predicted_classes"] == ""
    assert record["filename"] == ""


def test_group_records_by_predicted_class_single_class():
    records = [{"predicted_classes": "faded", "filename": "a.jpg"}]
    grouped = lib.group_records_by_predicted_class(records)
    assert grouped == {"faded": [records[0]]}


def test_group_records_by_predicted_class_multi_class_appears_in_each_group():
    records = [{"predicted_classes": "faded;old_design", "filename": "a.jpg"}]
    grouped = lib.group_records_by_predicted_class(records)
    assert grouped["faded"] == [records[0]]
    assert grouped["old_design"] == [records[0]]


def test_group_records_by_predicted_class_ignores_empty_classes():
    records = [{"predicted_classes": "", "filename": "a.jpg"}]
    grouped = lib.group_records_by_predicted_class(records)
    assert grouped == {}


def test_build_map_popup_html_includes_image_and_metadata():
    record = {
        "predicted_classes": "faded", "confidences": "0.81",
        "human_label": "faded", "corner_id": "10001_609", "filename": "a.jpg",
    }
    html = lib.build_map_popup_html(record, image_b64="Zm9v")
    assert "Zm9v" in html
    assert "faded" in html
    assert "0.81" in html
    assert "10001_609" in html
    assert "a.jpg" in html


def test_build_map_popup_html_omits_image_tag_when_no_image():
    record = {
        "predicted_classes": "faded", "confidences": "0.81",
        "human_label": "faded", "corner_id": "x", "filename": "a.jpg",
    }
    html = lib.build_map_popup_html(record, image_b64=None)
    assert "<img" not in html


def test_build_map_popup_html_includes_sims_number_and_coordinates():
    record = {
        "predicted_classes": "faded", "confidences": "0.81",
        "human_label": "faded", "corner_id": "10001_609",
        "filename": "a.jpg", "order_numbers": "ST01647077",
        "latitude": 40.746814, "longitude": -73.976137,
    }
    html = lib.build_map_popup_html(record, image_b64=None)
    assert "ST01647077" in html
    assert "40.746814" in html
    assert "-73.976137" in html


def test_build_map_popup_html_omits_coordinates_when_missing():
    record = {
        "predicted_classes": "faded", "confidences": "0.81",
        "human_label": "faded", "corner_id": "x", "filename": "a.jpg",
    }
    html = lib.build_map_popup_html(record, image_b64=None)
    assert "Lat/Long" not in html


def test_load_manifest_rows_by_filename_returns_full_row(tmp_path, monkeypatch):
    import prepare_yolo_dataset_physical as pydp
    monkeypatch.setattr(pydp, "DATA_DIR", tmp_path)
    capture_dir = tmp_path / "raw_images" / "zip_10001" / "manual_capture"
    capture_dir.mkdir(parents=True)
    manifest = capture_dir / "manifest_1.csv"
    manifest.write_text(
        "filename,damage_category,latitude,longitude\n"
        "a.jpg,faded,40.7,-73.9\n",
        encoding="utf-8",
    )

    rows_by_filename = lib.load_manifest_rows_by_filename()

    assert rows_by_filename["a.jpg"]["damage_category"] == "faded"
    assert rows_by_filename["a.jpg"]["latitude"] == "40.7"
