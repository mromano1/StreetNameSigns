import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import report_physical as rp


def _fake_result(names, classes, confs):
    import numpy as np
    result = SimpleNamespace(
        names=names,
        boxes=SimpleNamespace(
            cls=SimpleNamespace(tolist=lambda: classes),
            conf=SimpleNamespace(tolist=lambda: confs),
        ),
    )
    # Mock plot() to return a fake annotated image (simple blank image)
    result.plot = lambda: np.zeros((100, 100, 3), dtype=np.uint8)
    return result


def test_predict_image_extracts_name_confidence_pairs(tmp_path):
    image_path = tmp_path / "a.jpg"
    image_path.write_bytes(b"x")
    result = _fake_result({0: "faded", 1: "old_design"}, [0, 1], [0.81, 0.4])
    model = MagicMock(return_value=[result])

    preds = rp.predict_image(model, image_path)

    assert preds == [("faded", 0.81), ("old_design", 0.4)]
    model.assert_called_once_with(str(image_path), verbose=False)


def test_latest_run_name_picks_most_recently_modified(tmp_path, monkeypatch):
    monkeypatch.setattr(rp, "RUNS_DIR", tmp_path)
    for name in ["run_a", "run_b"]:
        weights = tmp_path / name / "weights"
        weights.mkdir(parents=True)
        (weights / "best.pt").write_bytes(b"x")
        time.sleep(0.02)

    assert rp.latest_run_name() == "run_b"


def test_latest_run_name_raises_when_no_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(rp, "RUNS_DIR", tmp_path)
    try:
        rp.latest_run_name()
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_load_run_metrics_returns_last_matching_row(tmp_path, monkeypatch):
    history_path = tmp_path / "PHYSICAL_RUN_HISTORY.csv"
    history_path.write_text(
        "date,run_name,precision,recall,mAP50,mAP50_95\n"
        "2026-07-28,street_sign_physical,0.5,0.4,0.3,0.2\n"
        "2026-07-29,street_sign_physical,0.6,0.5,0.4,0.3\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(rp, "HISTORY_PATH", history_path)

    row = rp.load_run_metrics("street_sign_physical")

    assert row["date"] == "2026-07-29"
    assert row["precision"] == "0.6"


def test_load_run_metrics_returns_none_when_no_match(tmp_path, monkeypatch):
    history_path = tmp_path / "PHYSICAL_RUN_HISTORY.csv"
    history_path.write_text("date,run_name,precision,recall,mAP50,mAP50_95\n", encoding="utf-8")
    monkeypatch.setattr(rp, "HISTORY_PATH", history_path)

    assert rp.load_run_metrics("nonexistent") is None


def test_build_records_skips_images_with_no_manifest_row(tmp_path):
    image_path = tmp_path / "unknown.jpg"
    image_path.write_bytes(b"x")
    model = MagicMock(return_value=[_fake_result({0: "faded"}, [0], [0.9])])

    records = rp.build_records(model, [image_path], rows_by_filename={})

    assert records == []


def test_build_records_builds_record_for_known_image(tmp_path):
    image_path = tmp_path / "known.jpg"
    image_path.write_bytes(b"x")
    model = MagicMock(return_value=[_fake_result({0: "faded"}, [0], [0.9])])
    rows_by_filename = {
        "known.jpg": {
            "filename": "known.jpg", "latitude": "40.746814", "longitude": "-73.976137",
            "order_numbers": "ST1", "sign_codes": "SN-1A", "corner_id": "10001_000",
            "timestamp": "2026-07-15T00:13:21.623Z", "damage_category": "faded",
        }
    }

    records = rp.build_records(model, [image_path], rows_by_filename)

    assert len(records) == 1
    assert records[0]["predicted_classes"] == "faded"


def test_build_samples_formats_predictions_and_looks_up_human_label(tmp_path):
    image_path = tmp_path / "known.jpg"
    image_path.write_bytes(b"x")
    model = MagicMock(return_value=[_fake_result({0: "faded"}, [0], [0.81])])
    rows_by_filename = {"known.jpg": {"damage_category": "faded"}}

    samples = rp.build_samples(model, [image_path], rows_by_filename)

    assert len(samples) == 1
    assert samples[0]["predicted"] == "faded:0.81"
    assert samples[0]["human"] == "faded"
    assert samples[0]["filename"] == "known.jpg"
    assert samples[0]["annotated_b64"]  # non-empty string


def test_build_samples_handles_no_detections(tmp_path):
    image_path = tmp_path / "clean.jpg"
    image_path.write_bytes(b"x")
    model = MagicMock(return_value=[_fake_result({}, [], [])])
    rows_by_filename = {"clean.jpg": {"damage_category": "no damage"}}

    samples = rp.build_samples(model, [image_path], rows_by_filename)

    assert samples[0]["predicted"] == "(no detections)"


def test_build_samples_defaults_human_label_when_no_manifest_row(tmp_path):
    image_path = tmp_path / "unknown.jpg"
    image_path.write_bytes(b"x")
    model = MagicMock(return_value=[_fake_result({0: "faded"}, [0], [0.5])])

    samples = rp.build_samples(model, [image_path], rows_by_filename={})

    assert samples[0]["human"] == ""


def test_build_interactive_map_html_returns_none_for_no_records():
    assert rp.build_interactive_map_html(MagicMock(), [], []) is None


def test_build_interactive_map_html_builds_map_with_layers(tmp_path):
    image_path = tmp_path / "a.jpg"
    image_path.write_bytes(b"x")
    model = MagicMock(return_value=[_fake_result({0: "faded"}, [0], [0.9])])
    records = [{
        "latitude": 40.746814, "longitude": -73.976137,
        "predicted_classes": "faded", "confidences": "0.90",
        "human_label": "faded", "corner_id": "10001_000",
        "order_numbers": "ST1", "filename": "a.jpg",
    }]

    result = rp.build_interactive_map_html(model, records, [tmp_path])

    assert result is not None
    assert "faded (1)" in result
    assert "leaflet" in result.lower()


def test_build_interactive_map_html_handles_missing_image_gracefully(tmp_path):
    model = MagicMock(return_value=[_fake_result({0: "faded"}, [0], [0.9])])
    records = [{
        "latitude": 40.746814, "longitude": -73.976137,
        "predicted_classes": "faded", "confidences": "0.90",
        "human_label": "faded", "corner_id": "10001_000",
        "order_numbers": "ST1", "filename": "missing.jpg",
    }]

    result = rp.build_interactive_map_html(model, records, [tmp_path])

    assert result is not None


def test_build_interactive_map_html_groups_multiple_classes_into_separate_layers(tmp_path):
    model = MagicMock(return_value=[_fake_result({0: "faded"}, [0], [0.9])])
    records = [
        {
            "latitude": 40.746814, "longitude": -73.976137,
            "predicted_classes": "faded", "confidences": "0.90",
            "human_label": "faded", "corner_id": "10001_000",
            "order_numbers": "ST1", "filename": "missing1.jpg",
        },
        {
            "latitude": 40.747000, "longitude": -73.977000,
            "predicted_classes": "vandalized", "confidences": "0.80",
            "human_label": "vandalized", "corner_id": "10001_001",
            "order_numbers": "ST2", "filename": "missing2.jpg",
        },
    ]

    result = rp.build_interactive_map_html(model, records, [tmp_path])

    assert "faded (1)" in result
    assert "vandalized (1)" in result
