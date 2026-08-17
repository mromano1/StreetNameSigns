import json
from unittest.mock import MagicMock, patch

import community_board_lookup as cbl


def test_boro_cd_to_label_manhattan():
    assert cbl.boro_cd_to_label("105") == "Manhattan CD 5"


def test_boro_cd_to_label_queens_double_digit():
    assert cbl.boro_cd_to_label("410") == "Queens CD 10"


def test_boro_cd_to_label_joint_interest_area():
    # Queens' highest real CD is 14; 83 is a Joint Interest Area code.
    assert cbl.boro_cd_to_label("483") == "Queens JIA"


def test_boro_cd_to_label_unknown_borough_digit():
    assert cbl.boro_cd_to_label("910") == ""


def test_boro_cd_to_label_empty_input():
    assert cbl.boro_cd_to_label("") == ""


def _square_feature(boro_cd, min_lon, min_lat, max_lon, max_lat):
    return {
        "type": "Feature",
        "properties": {"boro_cd": boro_cd},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [min_lon, min_lat], [max_lon, min_lat],
                [max_lon, max_lat], [min_lon, max_lat],
                [min_lon, min_lat],
            ]],
        },
    }


def _fixture_geojson():
    return {
        "type": "FeatureCollection",
        "features": [
            _square_feature("105", -74.0, 40.7, -73.9, 40.8),   # Manhattan CD 5
            _square_feature("306", -74.1, 40.6, -74.0, 40.7),   # Brooklyn CD 6
        ],
    }


def test_build_community_board_index_and_lookup_inside_polygon():
    index = cbl.build_community_board_index(_fixture_geojson())
    assert cbl.lookup_community_board(40.75, -73.95, index) == "Manhattan CD 5"


def test_lookup_community_board_returns_empty_outside_all_polygons():
    index = cbl.build_community_board_index(_fixture_geojson())
    assert cbl.lookup_community_board(0.0, 0.0, index) == ""


def test_fetch_community_districts_geojson_uses_existing_cache(tmp_path):
    cache_path = tmp_path / "cd.geojson"
    cache_path.write_text(json.dumps(_fixture_geojson()), encoding="utf-8")

    with patch("community_board_lookup.requests.get") as mock_get:
        result = cbl.fetch_community_districts_geojson(cache_path)

    mock_get.assert_not_called()
    assert result == _fixture_geojson()


def test_fetch_community_districts_geojson_writes_cache_when_missing(tmp_path):
    cache_path = tmp_path / "cd.geojson"
    fake_resp = MagicMock()
    fake_resp.json.return_value = _fixture_geojson()
    fake_resp.raise_for_status.return_value = None

    with patch("community_board_lookup.requests.get", return_value=fake_resp) as mock_get:
        result = cbl.fetch_community_districts_geojson(cache_path)

    mock_get.assert_called_once()
    assert result == _fixture_geojson()
    assert cache_path.exists()
    assert json.loads(cache_path.read_text(encoding="utf-8")) == _fixture_geojson()


def test_load_community_board_index_end_to_end(tmp_path):
    cache_path = tmp_path / "cd.geojson"
    cache_path.write_text(json.dumps(_fixture_geojson()), encoding="utf-8")

    index = cbl.load_community_board_index(cache_path)

    assert cbl.lookup_community_board(40.65, -74.05, index) == "Brooklyn CD 6"


# --- reverse direction: label/boro_cd -> boro_cd -> polygon ---


def test_label_to_boro_cd_round_trips_boro_cd_to_label():
    assert cbl.label_to_boro_cd("Manhattan CD 5") == "105"
    assert cbl.label_to_boro_cd("Brooklyn CD 4") == "304"
    assert cbl.label_to_boro_cd("Queens CD 10") == "410"


def test_label_to_boro_cd_is_case_and_space_insensitive():
    assert cbl.label_to_boro_cd("brooklyn cd 4") == "304"
    assert cbl.label_to_boro_cd("  BROOKLYN   CD4  ") == "304"


def test_label_to_boro_cd_accepts_label_without_cd_keyword():
    assert cbl.label_to_boro_cd("Staten Island 3") == "503"


def test_label_to_boro_cd_rejects_unknown_borough():
    assert cbl.label_to_boro_cd("Yonkers CD 4") == ""


def test_label_to_boro_cd_rejects_district_above_boroughs_real_max():
    # Brooklyn's highest real CD is 18.
    assert cbl.label_to_boro_cd("Brooklyn CD 19") == ""


def test_label_to_boro_cd_rejects_jia_label_and_empty_input():
    # "Queens JIA" maps to several boro_cd codes, so it has no unique reverse.
    assert cbl.label_to_boro_cd("Queens JIA") == ""
    assert cbl.label_to_boro_cd("") == ""


def test_resolve_boro_cd_passes_through_a_raw_code():
    assert cbl.resolve_boro_cd("304") == "304"


def test_resolve_boro_cd_zero_pads_a_short_code():
    # The dataset's keys are 3 characters, so "34" has to become "304".
    assert cbl.resolve_boro_cd("34") == "304"


def test_resolve_boro_cd_accepts_a_human_label():
    assert cbl.resolve_boro_cd("Brooklyn CD 4") == "304"


def test_resolve_boro_cd_accepts_a_joint_interest_area_code():
    # A raw JIA code is unambiguous even though its label isn't reversible.
    assert cbl.resolve_boro_cd("483") == "483"


def test_resolve_boro_cd_rejects_unrecognized_input():
    assert cbl.resolve_boro_cd("999") == ""
    assert cbl.resolve_boro_cd("nonsense") == ""
    assert cbl.resolve_boro_cd("") == ""


def test_build_community_board_polygon_finds_polygon_by_label():
    polygon = cbl.build_community_board_polygon(_fixture_geojson(), "Brooklyn CD 6")
    assert polygon is not None
    assert polygon.contains(cbl.Point(-74.05, 40.65))
    assert not polygon.contains(cbl.Point(-73.95, 40.75))


def test_build_community_board_polygon_finds_polygon_by_boro_cd():
    polygon = cbl.build_community_board_polygon(_fixture_geojson(), "105")
    assert polygon is not None
    assert polygon.contains(cbl.Point(-73.95, 40.75))


def test_build_community_board_polygon_returns_none_for_absent_board():
    assert cbl.build_community_board_polygon(_fixture_geojson(), "Bronx CD 1") is None


def test_build_community_board_polygon_returns_none_for_unresolvable_input():
    assert cbl.build_community_board_polygon(_fixture_geojson(), "nonsense") is None


def test_build_community_board_polygon_unions_multiple_features_sharing_a_code():
    geojson = {
        "type": "FeatureCollection",
        "features": [
            _square_feature("306", -74.1, 40.6, -74.0, 40.7),
            _square_feature("306", -74.3, 40.6, -74.2, 40.7),
        ],
    }
    polygon = cbl.build_community_board_polygon(geojson, "306")
    assert polygon.contains(cbl.Point(-74.05, 40.65))
    assert polygon.contains(cbl.Point(-74.25, 40.65))


def test_load_community_board_polygon_end_to_end(tmp_path):
    cache_path = tmp_path / "cd.geojson"
    cache_path.write_text(json.dumps(_fixture_geojson()), encoding="utf-8")

    with patch("community_board_lookup.requests.get") as mock_get:
        polygon = cbl.load_community_board_polygon(cache_path, "Brooklyn CD 6")

    mock_get.assert_not_called()
    assert polygon.contains(cbl.Point(-74.05, 40.65))
