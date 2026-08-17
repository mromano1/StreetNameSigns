from datetime import date
from unittest.mock import MagicMock, patch

import pytest

import cyclomedia_client as cc


@pytest.fixture(autouse=True)
def fake_creds(monkeypatch):
    monkeypatch.setenv("CYCLOMEDIA_USERNAME", "testuser")
    monkeypatch.setenv("CYCLOMEDIA_PASSWORD", "testpass")
    monkeypatch.setenv("CYCLOMEDIA_API_KEY", "testkey")


def _fake_response(status_code=200, json_data=None, text="", content=b""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    resp.content = content
    return resp


def test_find_nearest_recording_returns_first_feature_id():
    fake_json = {"features": [{"properties": {"imageId": "REC123"}}]}
    with patch("cyclomedia_client.requests.get", return_value=_fake_response(200, fake_json)) as mock_get:
        result = cc.find_nearest_recording(40.7, -73.9)
    assert result == "REC123"
    _, kwargs = mock_get.call_args
    assert kwargs["params"]["typeName"] == "atlas:Recording"
    assert kwargs["params"]["version"] == "1.1.0"
    assert "-73.9" in kwargs["params"]["filter"]


def test_find_nearest_recording_returns_none_when_empty():
    with patch("cyclomedia_client.requests.get", return_value=_fake_response(200, {"features": []})):
        result = cc.find_nearest_recording(40.7, -73.9)
    assert result is None


def test_find_nearest_recording_raises_on_error_status():
    with patch("cyclomedia_client.requests.get", return_value=_fake_response(500, text="server error")):
        with pytest.raises(cc.CyclomediaError, match="500"):
            cc.find_nearest_recording(40.7, -73.9)


def test_fetch_cyclomedia_image_raises_when_no_recording_found():
    with patch("cyclomedia_client.find_nearest_recording", return_value=None):
        with pytest.raises(cc.CyclomediaError, match="No Cyclomedia recording"):
            cc.fetch_cyclomedia_image(40.7, -73.9, heading=90)


def test_fetch_cyclomedia_image_returns_bytes_on_success():
    with patch("cyclomedia_client.find_nearest_recording", return_value="REC123"), patch(
        "cyclomedia_client.requests.get", return_value=_fake_response(200, content=b"JPEGDATA")
    ) as mock_get:
        result = cc.fetch_cyclomedia_image(40.7, -73.9, heading=90)
    assert result == b"JPEGDATA"
    args, kwargs = mock_get.call_args
    assert "REC123" in args[0]
    assert kwargs["params"]["yaw"] == 90
    assert kwargs["params"]["apiKey"] == "testkey"


def test_fetch_cyclomedia_image_raises_on_error_status():
    with patch("cyclomedia_client.find_nearest_recording", return_value="REC123"), patch(
        "cyclomedia_client.requests.get", return_value=_fake_response(404, text="not found")
    ):
        with pytest.raises(cc.CyclomediaError, match="404"):
            cc.fetch_cyclomedia_image(40.7, -73.9, heading=90)


def test_fetch_cyclomedia_image_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("CYCLOMEDIA_API_KEY", raising=False)
    with patch("cyclomedia_client.find_nearest_recording", return_value="REC123"):
        with pytest.raises(cc.CyclomediaError, match="CYCLOMEDIA_API_KEY"):
            cc.fetch_cyclomedia_image(40.7, -73.9, heading=90)


def test_find_nearest_recording_picks_closest_not_first():
    # Real API order is not guaranteed to be distance-sorted -- the second
    # feature here is much closer to (40.7, -73.9) than the first.
    fake_json = {
        "features": [
            {"properties": {"imageId": "FAR"}, "geometry": {"coordinates": [-73.95, 40.75]}},
            {"properties": {"imageId": "NEAR"}, "geometry": {"coordinates": [-73.9001, 40.7001]}},
        ]
    }
    with patch("cyclomedia_client.requests.get", return_value=_fake_response(200, fake_json)):
        result = cc.find_nearest_recording(40.7, -73.9)
    assert result == "NEAR"


def test_find_nearest_recording_handles_missing_geometry():
    # Backward-compat: a feature with no geometry (as in the other tests'
    # fixtures) must not crash the distance comparison.
    fake_json = {"features": [{"properties": {"imageId": "REC123"}}]}
    with patch("cyclomedia_client.requests.get", return_value=_fake_response(200, fake_json)):
        result = cc.find_nearest_recording(40.7, -73.9)
    assert result == "REC123"


def test_render_recording_returns_bytes_on_success():
    with patch(
        "cyclomedia_client.requests.get", return_value=_fake_response(200, content=b"JPEGDATA")
    ) as mock_get:
        result = cc.render_recording("REC123", heading=90)
    assert result == b"JPEGDATA"
    args, kwargs = mock_get.call_args
    assert "REC123" in args[0]
    assert kwargs["params"]["yaw"] == 90
    assert kwargs["params"]["apiKey"] == "testkey"


def test_render_recording_raises_on_error_status():
    with patch("cyclomedia_client.requests.get", return_value=_fake_response(404, text="not found")):
        with pytest.raises(cc.CyclomediaError, match="404"):
            cc.render_recording("REC123", heading=90)


def test_find_nearest_recording_at_date_excludes_expired_only_filter():
    # Unlike find_nearest_recording, this must NOT filter out expired
    # recordings -- that's the whole point of a historical-date lookup.
    with patch("cyclomedia_client.requests.get", return_value=_fake_response(200, {"features": []})) as mock_get:
        cc.find_nearest_recording_at_date(40.7, -73.9, before_date=date(2023, 1, 1))
    _, kwargs = mock_get.call_args
    assert "PropertyIsNull" not in kwargs["params"]["filter"]


def test_find_nearest_recording_at_date_picks_latest_on_or_before_cutoff():
    fake_json = {
        "features": [
            {"properties": {"imageId": "TOO_LATE", cc.RECORDING_DATE_FIELD: "2023-06-01T00:00:00Z"},
             "geometry": {"coordinates": [-73.9, 40.7]}},
            {"properties": {"imageId": "GOOD", cc.RECORDING_DATE_FIELD: "2022-01-01T00:00:00Z"},
             "geometry": {"coordinates": [-73.9, 40.7]}},
            {"properties": {"imageId": "TOO_EARLY", cc.RECORDING_DATE_FIELD: "2020-01-01T00:00:00Z"},
             "geometry": {"coordinates": [-73.9, 40.7]}},
        ]
    }
    with patch("cyclomedia_client.requests.get", return_value=_fake_response(200, fake_json)):
        result = cc.find_nearest_recording_at_date(40.7, -73.9, before_date=date(2023, 1, 1))
    assert result == "GOOD"


def test_find_nearest_recording_at_date_returns_none_when_nothing_before_cutoff():
    fake_json = {
        "features": [
            {"properties": {"imageId": "TOO_LATE", cc.RECORDING_DATE_FIELD: "2023-06-01T00:00:00Z"},
             "geometry": {"coordinates": [-73.9, 40.7]}},
        ]
    }
    with patch("cyclomedia_client.requests.get", return_value=_fake_response(200, fake_json)):
        result = cc.find_nearest_recording_at_date(40.7, -73.9, before_date=date(2023, 1, 1))
    assert result is None


def test_find_nearest_recording_at_date_skips_features_missing_date_field():
    fake_json = {
        "features": [
            {"properties": {"imageId": "NO_DATE"}, "geometry": {"coordinates": [-73.9, 40.7]}},
        ]
    }
    with patch("cyclomedia_client.requests.get", return_value=_fake_response(200, fake_json)):
        result = cc.find_nearest_recording_at_date(40.7, -73.9, before_date=date(2023, 1, 1))
    assert result is None


@pytest.mark.parametrize("sign_location,expected", [
    ("N/E C", "NE"),
    ("S/W C", "SW"),
    ("n/e c", "NE"),
    ("N C", "N"),
    ("N CURB", "N"),
    ("E C", "E"),
    ("N MALL", None),
    ("N WSD", None),
    ("", None),
    (None, None),
])
def test_compass_from_sign_location(sign_location, expected):
    assert cc.compass_from_sign_location(sign_location) == expected


@pytest.mark.parametrize("sign_location,expected_heading", [
    ("N/E C", 45.0),
    ("S/W C", 225.0),
    ("N C", 0.0),
    ("N MALL", None),
    (None, None),
])
def test_heading_candidates_for_corner(sign_location, expected_heading):
    assert cc.heading_candidates_for_corner(sign_location) == expected_heading
