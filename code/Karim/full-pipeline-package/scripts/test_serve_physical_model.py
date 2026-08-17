import subprocess

import pytest
from fastapi.testclient import TestClient

import serve_physical_model as srv


class FakeModel:
    """Stands in for a real ultralytics YOLO model. report_physical.predict_image
    itself is never unit tested (same convention as report_physical.py's own
    tests) -- /predict is tested by monkeypatching predict_image instead."""


def test_run_retrain_subprocess_runs_three_scripts_in_order(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(srv.subprocess, "run", fake_run)

    srv._run_retrain_subprocess()

    assert len(calls) == 3
    for _cmd, kwargs in calls:
        assert kwargs.get("check") is True
        assert "capture_output" not in kwargs
        assert "text" not in kwargs
    assert calls[0][0] == [srv.sys.executable, str(srv.SCRIPT_DIR / "prepare_yolo_dataset_physical.py")]
    assert calls[1][0] == [srv.sys.executable, str(srv.SCRIPT_DIR / "train_physical_model.py")]
    assert calls[1][1].get("timeout") == 7200
    assert calls[2][0] == [srv.sys.executable, str(srv.SCRIPT_DIR / "report_physical.py")]
    # Mocking subprocess.run means a wrong/typo'd script name would never
    # surface above -- these calls only exercised strings, so also confirm
    # the three scripts genuinely exist on disk at the paths just asserted.
    for path in (
        srv.SCRIPT_DIR / "prepare_yolo_dataset_physical.py",
        srv.SCRIPT_DIR / "train_physical_model.py",
        srv.SCRIPT_DIR / "report_physical.py",
    ):
        assert path.is_file(), f"{path} does not exist"


def test_run_retrain_subprocess_stops_at_first_failure(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            raise subprocess.CalledProcessError(1, cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(srv.subprocess, "run", fake_run)

    with pytest.raises(subprocess.CalledProcessError):
        srv._run_retrain_subprocess()

    assert len(calls) == 1


def test_predict_returns_filtered_sorted_classes(monkeypatch):
    monkeypatch.setattr(
        srv.report_physical,
        "predict_image",
        lambda model, image_path: [("faded", 0.10), ("bent_damaged", 0.82)],
    )
    app = srv.create_app(FakeModel())
    client = TestClient(app)

    resp = client.post("/predict", files={"file": ("crop.jpg", b"fake-bytes", "image/jpeg")})

    assert resp.status_code == 200
    assert resp.json() == {"classes": [{"class_name": "bent_damaged", "confidence": 0.82}]}


def test_predict_allows_cors_from_annotation_tool_origin(monkeypatch):
    monkeypatch.setattr(
        srv.report_physical,
        "predict_image",
        lambda model, image_path: [("faded", 0.82)],
    )
    app = srv.create_app(FakeModel())
    client = TestClient(app)

    resp = client.post(
        "/predict",
        files={"file": ("crop.jpg", b"fake-bytes", "image/jpeg")},
        headers={"Origin": "http://localhost:8000"},
    )

    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:8000"


def test_retrain_status_reports_delta(tmp_path):
    state_path = tmp_path / "state.json"
    srv.retrain_state.write_baseline(5, state_path)
    app = srv.create_app(
        FakeModel(),
        state_path=state_path,
        count_labeled_rows_fn=lambda: 12,
        history_reader_fn=lambda: (None, None),
    )
    client = TestClient(app)

    resp = client.get("/retrain-status")

    assert resp.status_code == 200
    assert resp.json() == {
        "new_since_last_retrain": 7,
        "total_labeled": 12,
        "baseline": 5,
        "last_run": None,
        "previous_run": None,
        "is_retraining": False,
    }


def test_retrain_status_includes_last_and_previous_run(tmp_path):
    state_path = tmp_path / "state.json"
    srv.retrain_state.write_baseline(5, state_path)
    app = srv.create_app(
        FakeModel(),
        state_path=state_path,
        count_labeled_rows_fn=lambda: 12,
        history_reader_fn=lambda: (
            {"run_name": "run2", "precision": "0.9", "recall": "0.8", "mAP50": "0.85", "mAP50_95": "0.6"},
            {"run_name": "run1", "precision": "0.7", "recall": "0.6", "mAP50": "0.65", "mAP50_95": "0.4"},
        ),
    )
    client = TestClient(app)

    resp = client.get("/retrain-status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["last_run"] == {
        "run_name": "run2", "precision": 0.9, "recall": 0.8, "map50": 0.85, "map50_95": 0.6,
    }
    assert body["previous_run"] == {
        "run_name": "run1", "precision": 0.7, "recall": 0.6, "map50": 0.65, "map50_95": 0.4,
    }


def test_retrain_status_last_run_none_when_no_history(tmp_path):
    state_path = tmp_path / "state.json"
    srv.retrain_state.write_baseline(5, state_path)
    app = srv.create_app(
        FakeModel(),
        state_path=state_path,
        count_labeled_rows_fn=lambda: 12,
        history_reader_fn=lambda: (None, None),
    )
    client = TestClient(app)

    resp = client.get("/retrain-status")

    assert resp.json()["last_run"] is None
    assert resp.json()["previous_run"] is None


def test_retrain_status_last_run_none_when_row_malformed(tmp_path):
    state_path = tmp_path / "state.json"
    srv.retrain_state.write_baseline(5, state_path)
    app = srv.create_app(
        FakeModel(),
        state_path=state_path,
        count_labeled_rows_fn=lambda: 12,
        history_reader_fn=lambda: (
            {"run_name": "run2", "recall": "0.8", "mAP50": "0.85", "mAP50_95": "0.6"},
            None,
        ),
    )
    client = TestClient(app)

    resp = client.get("/retrain-status")

    assert resp.status_code == 200
    assert resp.json()["last_run"] is None
    assert resp.json()["previous_run"] is None


def test_retrain_status_reports_is_retraining_false_by_default(tmp_path):
    state_path = tmp_path / "state.json"
    srv.retrain_state.write_baseline(5, state_path)
    app = srv.create_app(
        FakeModel(),
        state_path=state_path,
        count_labeled_rows_fn=lambda: 12,
        history_reader_fn=lambda: (None, None),
    )
    client = TestClient(app)

    resp = client.get("/retrain-status")

    assert resp.json()["is_retraining"] is False


def test_retrain_status_reports_is_retraining_true_while_locked(tmp_path):
    state_path = tmp_path / "state.json"
    srv.retrain_state.write_baseline(5, state_path)
    app = srv.create_app(
        FakeModel(),
        state_path=state_path,
        count_labeled_rows_fn=lambda: 12,
        history_reader_fn=lambda: (None, None),
    )
    client = TestClient(app)

    app.state.retrain_lock.acquire()
    try:
        resp = client.get("/retrain-status")
        assert resp.json()["is_retraining"] is True
    finally:
        app.state.retrain_lock.release()


def test_get_report_returns_html_for_existing_run(tmp_path):
    (tmp_path / "physical_condition_run1.html").write_text("<html>my report</html>", encoding="utf-8")
    app = srv.create_app(FakeModel(), reports_dir=tmp_path)
    client = TestClient(app)

    resp = client.get("/report/run1")

    assert resp.status_code == 200
    assert "my report" in resp.text


def test_get_report_returns_404_for_missing_run(tmp_path):
    app = srv.create_app(FakeModel(), reports_dir=tmp_path)
    client = TestClient(app)

    resp = client.get("/report/does-not-exist")

    assert resp.status_code == 404


def test_retrain_success_updates_baseline(tmp_path):
    state_path = tmp_path / "state.json"
    srv.retrain_state.write_baseline(5, state_path)
    app = srv.create_app(
        FakeModel(),
        state_path=state_path,
        retrain_runner=lambda: None,
        count_labeled_rows_fn=lambda: 18,
    )
    client = TestClient(app)

    resp = client.post("/retrain")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "new_baseline": 18}
    assert srv.retrain_state.read_baseline(state_path) == 18


def test_retrain_rejects_second_call_while_in_progress(tmp_path):
    state_path = tmp_path / "state.json"
    srv.retrain_state.write_baseline(5, state_path)
    app = srv.create_app(
        FakeModel(),
        state_path=state_path,
        retrain_runner=lambda: None,
        count_labeled_rows_fn=lambda: 18,
    )
    client = TestClient(app)

    app.state.retrain_lock.acquire()
    try:
        resp = client.post("/retrain")
        assert resp.status_code == 409
        assert resp.json()["detail"] == "a retrain is already in progress"
        assert srv.retrain_state.read_baseline(state_path) == 5
    finally:
        app.state.retrain_lock.release()


def test_retrain_releases_lock_after_success(tmp_path):
    state_path = tmp_path / "state.json"
    srv.retrain_state.write_baseline(5, state_path)
    app = srv.create_app(
        FakeModel(),
        state_path=state_path,
        retrain_runner=lambda: None,
        count_labeled_rows_fn=lambda: 18,
    )
    client = TestClient(app)

    client.post("/retrain")

    assert app.state.retrain_lock.locked() is False


def test_retrain_releases_lock_after_failure(tmp_path):
    state_path = tmp_path / "state.json"
    srv.retrain_state.write_baseline(5, state_path)

    def failing_runner():
        raise subprocess.CalledProcessError(1, ["nbconvert"], stderr="training blew up")

    app = srv.create_app(
        FakeModel(),
        state_path=state_path,
        retrain_runner=failing_runner,
        count_labeled_rows_fn=lambda: 18,
    )
    client = TestClient(app)

    client.post("/retrain")

    assert app.state.retrain_lock.locked() is False


def test_retrain_with_no_origin_header_still_succeeds(tmp_path):
    state_path = tmp_path / "state.json"
    srv.retrain_state.write_baseline(5, state_path)
    app = srv.create_app(
        FakeModel(),
        state_path=state_path,
        retrain_runner=lambda: None,
        count_labeled_rows_fn=lambda: 18,
    )
    client = TestClient(app)

    resp = client.post("/retrain")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "new_baseline": 18}


def test_retrain_with_foreign_origin_is_rejected(tmp_path):
    state_path = tmp_path / "state.json"
    srv.retrain_state.write_baseline(5, state_path)
    app = srv.create_app(
        FakeModel(),
        state_path=state_path,
        retrain_runner=lambda: None,
        count_labeled_rows_fn=lambda: 18,
    )
    client = TestClient(app)

    resp = client.post("/retrain", headers={"origin": "https://evil.example.com"})

    assert resp.status_code == 403
    assert srv.retrain_state.read_baseline(state_path) == 5


def test_retrain_failure_does_not_update_baseline(tmp_path):
    state_path = tmp_path / "state.json"
    srv.retrain_state.write_baseline(5, state_path)

    def failing_runner():
        raise subprocess.CalledProcessError(1, ["nbconvert"], stderr="training blew up")

    app = srv.create_app(
        FakeModel(),
        state_path=state_path,
        retrain_runner=failing_runner,
        count_labeled_rows_fn=lambda: 18,
    )
    client = TestClient(app)

    resp = client.post("/retrain")

    assert resp.status_code == 500
    assert "training blew up" in resp.json()["detail"]
    assert srv.retrain_state.read_baseline(state_path) == 5
