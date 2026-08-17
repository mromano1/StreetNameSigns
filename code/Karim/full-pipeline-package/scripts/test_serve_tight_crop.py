import base64
import io
import json
import os

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import serve_tight_crop as srv


class FakeCyclomediaError(Exception):
    pass


def _write_manifest(dir_path, jobs):
    dir_path.mkdir(parents=True, exist_ok=True)
    manifest_path = dir_path / "fetch_manifest.json"
    manifest_path.write_text(json.dumps({"jobs": jobs}))
    return manifest_path


def _fake_jpeg_bytes(width=100, height=100):
    # A real, decodable JPEG -- needed now that the endpoint actually opens
    # and crops render_fn's return value (crop_image_vertically), not just
    # passes the bytes through untouched.
    img = Image.new("RGB", (width, height), color=(120, 60, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_tight_crop_returns_path_and_base64_image_for_the_root_collection(tmp_path):
    panoramas_dir = tmp_path / "panoramas"
    _write_manifest(
        panoramas_dir,
        [{"corner_id": "C1", "image_kind": "latest", "status": "ok", "recording_id": "R1", "heading": 45.0}],
    )

    calls = []

    def fake_render(recording_id, heading, width, height, fov):
        calls.append((recording_id, heading, width, height, fov))
        return _fake_jpeg_bytes(width=width, height=height)

    app = srv.create_app(panoramas_dir, render_fn=fake_render)
    client = TestClient(app)

    resp = client.post(
        "/tight-crop",
        json={"corner_id": "C1", "image_kind": "latest", "box_index": 0, "box": {"x": 1590, "y": 1000, "w": 20, "h": 20}},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["path"] == os.path.join("C1", "tight_latest_0.jpg")
    assert len(calls) == 1
    assert calls[0][0] == "R1"

    # Response and saved file are the CROPPED result (crop_image_vertically
    # re-encodes), not render_fn's raw bytes verbatim -- check it's a real,
    # decodable image instead of exact byte equality.
    saved = panoramas_dir / "C1" / "tight_latest_0.jpg"
    assert saved.exists()
    Image.open(saved).verify()
    assert base64.b64decode(body["image_base64"]) == saved.read_bytes()


def test_tight_crop_requests_a_taller_output_for_a_box_far_from_vertical_center(tmp_path):
    # No pitch parameter exists in the Cyclomedia render API -- a box near
    # the top of the frame can only be kept in view by requesting a taller
    # output, not by aiming the camera up. Regression test for the actual
    # /tight-crop request/response, not just the underlying lib function.
    panoramas_dir = tmp_path / "panoramas"
    _write_manifest(
        panoramas_dir,
        [{"corner_id": "C1", "image_kind": "latest", "status": "ok", "recording_id": "R1", "heading": 45.0}],
    )
    calls = []

    def fake_render(recording_id, heading, width, height, fov):
        calls.append((recording_id, heading, width, height, fov))
        return _fake_jpeg_bytes()  # small fixed fake -- crop_image_vertically clamps to its real size regardless

    app = srv.create_app(panoramas_dir, render_fn=fake_render)
    client = TestClient(app)

    client.post(
        "/tight-crop",
        json={"corner_id": "C1", "image_kind": "latest", "box_index": 0, "box": {"x": 1590, "y": 10, "w": 20, "h": 20}},
    )

    assert len(calls) == 1
    requested_height = calls[0][3]
    assert requested_height > srv.RENDER_HEIGHT  # taller than the original capture's own height


def test_tight_crop_clamps_requested_height_to_the_apis_own_limit(tmp_path):
    # A box right at the very edge of a wide capture can call for a height
    # past what the real Atlas Render API accepts -- confirmed live
    # (2026-08-14): a request above 8192 gets rejected outright with
    # "The field Height must be between 0 and 8192." Clamp rather than
    # fail the whole request.
    panoramas_dir = tmp_path / "panoramas"
    _write_manifest(
        panoramas_dir,
        [{"corner_id": "C1", "image_kind": "latest", "status": "ok", "recording_id": "R1", "heading": 45.0}],
    )
    calls = []

    def fake_render(recording_id, heading, width, height, fov):
        calls.append((recording_id, heading, width, height, fov))
        return _fake_jpeg_bytes()  # small fixed fake -- crop_image_vertically clamps to its real size regardless

    app = srv.create_app(panoramas_dir, render_fn=fake_render)
    client = TestClient(app)

    client.post(
        "/tight-crop",
        # Tiny box right at the top edge -- a huge vertical offset paired
        # with a tiny (tightly-zoomed) hfov, the combination most likely to
        # blow past the real API's height ceiling.
        json={"corner_id": "C1", "image_kind": "latest", "box_index": 0, "box": {"x": 1599, "y": 1, "w": 2, "h": 2}},
    )

    assert len(calls) == 1
    assert calls[0][3] <= srv.MAX_RENDER_HEIGHT


def test_tight_crop_finds_a_job_in_a_subfolder_dataset_and_saves_there(tmp_path):
    panoramas_dir = tmp_path / "panoramas"
    # An unrelated root collection exists too -- must not be picked over
    # the subfolder match, and must not be searched-and-stop-there.
    _write_manifest(panoramas_dir, [{"corner_id": "OTHER", "image_kind": "latest", "status": "ok", "recording_id": "R_root", "heading": 0.0}])
    _write_manifest(
        panoramas_dir / "demo_cb301",
        [{"corner_id": "cb301_000", "image_kind": "latest", "status": "ok", "recording_id": "R_cb301", "heading": 225.0}],
    )

    app = srv.create_app(panoramas_dir, render_fn=lambda *a, **k: _fake_jpeg_bytes())
    client = TestClient(app)

    resp = client.post(
        "/tight-crop",
        json={"corner_id": "cb301_000", "image_kind": "latest", "box_index": 0, "box": {"x": 1590, "y": 1000, "w": 20, "h": 20}},
    )

    assert resp.status_code == 200
    body = resp.json()
    # Returned path includes the dataset subfolder, so a caller can always
    # resolve it against panoramas_dir regardless of which collection it
    # came from.
    assert body["path"] == os.path.join("demo_cb301", "cb301_000", "tight_latest_0.jpg")

    saved = panoramas_dir / "demo_cb301" / "cb301_000" / "tight_latest_0.jpg"
    assert saved.exists()
    Image.open(saved).verify()


def test_tight_crop_resolves_recording_id_for_a_skipped_job(tmp_path):
    # "skipped" means the file already existed on disk from an earlier
    # run, so fetch_cyclomedia_panoramas.py never called Cyclomedia for
    # it and never cached a recording_id in the manifest -- the tight-crop
    # server has to look one up fresh, same as run_job originally did.
    panoramas_dir = tmp_path / "panoramas"
    _write_manifest(
        panoramas_dir,
        [{"corner_id": "C1", "image_kind": "latest", "status": "skipped", "lat": 40.7, "lon": -73.9, "heading": 45.0}],
    )

    find_calls = []

    def fake_find_recording(lat, lon):
        find_calls.append((lat, lon))
        return "R_resolved"

    render_calls = []

    def fake_render(recording_id, heading, width, height, fov):
        render_calls.append(recording_id)
        return _fake_jpeg_bytes()

    app = srv.create_app(panoramas_dir, render_fn=fake_render, find_recording_fn=fake_find_recording)
    client = TestClient(app)

    resp = client.post(
        "/tight-crop",
        json={"corner_id": "C1", "image_kind": "latest", "box_index": 0, "box": {"x": 1590, "y": 1000, "w": 20, "h": 20}},
    )

    assert resp.status_code == 200
    assert find_calls == [(40.7, -73.9)]
    assert render_calls == ["R_resolved"]


def test_tight_crop_returns_502_when_skipped_jobs_recording_cannot_be_resolved(tmp_path):
    panoramas_dir = tmp_path / "panoramas"
    _write_manifest(
        panoramas_dir,
        [{"corner_id": "C1", "image_kind": "latest", "status": "skipped", "lat": 40.7, "lon": -73.9, "heading": 45.0}],
    )
    app = srv.create_app(panoramas_dir, render_fn=lambda *a, **k: b"", find_recording_fn=lambda lat, lon: None)
    client = TestClient(app)

    resp = client.post(
        "/tight-crop",
        json={"corner_id": "C1", "image_kind": "latest", "box_index": 0, "box": {"x": 0, "y": 0, "w": 10, "h": 10}},
    )
    assert resp.status_code == 502


def test_tight_crop_uses_the_ok_jobs_cached_recording_id_without_resolving(tmp_path):
    # An "ok" job already has a recording_id -- find_recording_fn must
    # never be called for it (would be a wasted extra API call).
    panoramas_dir = tmp_path / "panoramas"
    _write_manifest(
        panoramas_dir,
        [{"corner_id": "C1", "image_kind": "latest", "status": "ok", "recording_id": "R1", "heading": 45.0}],
    )

    def unexpected_find(lat, lon):
        raise AssertionError("find_recording_fn should not be called for an 'ok' job")

    app = srv.create_app(panoramas_dir, render_fn=lambda *a, **k: _fake_jpeg_bytes(), find_recording_fn=unexpected_find)
    client = TestClient(app)

    resp = client.post(
        "/tight-crop",
        json={"corner_id": "C1", "image_kind": "latest", "box_index": 0, "box": {"x": 0, "y": 0, "w": 10, "h": 10}},
    )
    assert resp.status_code == 200


def test_tight_crop_returns_404_when_no_dataset_has_a_matching_job(tmp_path):
    panoramas_dir = tmp_path / "panoramas"
    _write_manifest(panoramas_dir, [])
    app = srv.create_app(panoramas_dir, render_fn=lambda *a, **k: b"")
    client = TestClient(app)

    resp = client.post(
        "/tight-crop",
        json={"corner_id": "MISSING", "image_kind": "latest", "box_index": 0, "box": {"x": 0, "y": 0, "w": 10, "h": 10}},
    )
    assert resp.status_code == 404


def test_tight_crop_returns_502_on_cyclomedia_error(tmp_path):
    panoramas_dir = tmp_path / "panoramas"
    _write_manifest(
        panoramas_dir,
        [{"corner_id": "C1", "image_kind": "latest", "status": "ok", "recording_id": "R1", "heading": 45.0}],
    )

    def failing_render(*args, **kwargs):
        raise srv.cc.CyclomediaError("boom")

    app = srv.create_app(panoramas_dir, render_fn=failing_render)
    client = TestClient(app)

    resp = client.post(
        "/tight-crop",
        json={"corner_id": "C1", "image_kind": "latest", "box_index": 0, "box": {"x": 0, "y": 0, "w": 10, "h": 10}},
    )
    assert resp.status_code == 502


def test_tight_crop_allows_cors_from_annotation_tool_origin(tmp_path):
    panoramas_dir = tmp_path / "panoramas"
    _write_manifest(
        panoramas_dir,
        [{"corner_id": "C1", "image_kind": "latest", "status": "ok", "recording_id": "R1", "heading": 45.0}],
    )
    app = srv.create_app(panoramas_dir, render_fn=lambda *a, **k: _fake_jpeg_bytes())
    client = TestClient(app)

    resp = client.post(
        "/tight-crop",
        json={"corner_id": "C1", "image_kind": "latest", "box_index": 0, "box": {"x": 0, "y": 0, "w": 10, "h": 10}},
        headers={"Origin": "http://localhost:8000"},
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:8000"
