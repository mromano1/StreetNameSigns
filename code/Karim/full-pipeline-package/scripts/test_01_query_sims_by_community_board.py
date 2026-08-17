"""
Tests for 01_query_sims_by_community_board.py. Loaded via importlib since the
filename starts with a digit (same pattern as test_01_query_sims_by_zip.py).
"""
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
from pyproj import Transformer
from shapely.geometry import Polygon

MODULE_PATH = Path(__file__).parent / "01_query_sims_by_community_board.py"
spec = importlib.util.spec_from_file_location("query_sims_by_community_board", MODULE_PATH)
qcb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qcb)


# --- output naming ---


def test_board_output_label_prefixes_boro_cd_with_cb():
    assert qcb.board_output_label("304") == "cb304"


def test_output_filename_reuses_the_zip_scripts_pattern():
    # Deliberately signs_zip_*: 02_generate_signs_data.py hardcodes that
    # prefix, so this keeps it working unmodified via `02 ... cb304`.
    assert qcb.output_filename("304", include_historical=False) == "signs_zip_cb304.csv"


def test_output_filename_with_history_flag_has_history_suffix():
    assert qcb.output_filename("304", include_historical=True) == "signs_zip_cb304_history.csv"


# --- bounding box in EPSG:2263 ---


def _brooklyn_square():
    # A small square straddling part of Brooklyn, in WGS84 lon/lat.
    return Polygon([(-73.95, 40.68), (-73.90, 40.68), (-73.90, 40.71), (-73.95, 40.71)])


def test_board_bbox_2263_returns_min_max_in_where_clause_order():
    to_sp = Transformer.from_crs("EPSG:4326", "EPSG:2263", always_xy=True)
    x_min, x_max, y_min, y_max = qcb.board_bbox_2263(_brooklyn_square(), to_sp)

    assert x_min < x_max
    assert y_min < y_max
    # State Plane feet for NYC are ~1.0e6 easting / ~1.5e5-2.7e5 northing.
    assert 900_000 < x_min < 1_100_000
    assert 100_000 < y_min < 300_000


def test_board_bbox_2263_covers_the_polygons_own_corners():
    to_sp = Transformer.from_crs("EPSG:4326", "EPSG:2263", always_xy=True)
    x_min, x_max, y_min, y_max = qcb.board_bbox_2263(_brooklyn_square(), to_sp)

    for lon, lat in _brooklyn_square().exterior.coords:
        x, y = to_sp.transform(lon, lat)
        assert x_min <= x <= x_max
        assert y_min <= y <= y_max


# --- point-in-polygon second pass ---


def _df(rows):
    return pd.DataFrame(rows, columns=["order_number", "latitude", "longitude"])


def test_filter_points_in_polygon_keeps_only_records_inside():
    polygon = _brooklyn_square()
    df = _df([
        ("ST1", 40.69, -73.92),   # inside
        ("ST2", 40.60, -73.92),   # south of the square
        ("ST3", 40.69, -74.20),   # west of the square
    ])

    result = qcb.filter_points_in_polygon(df, polygon)

    assert list(result["order_number"]) == ["ST1"]


def test_filter_points_in_polygon_drops_records_with_missing_coords():
    df = _df([("ST1", 40.69, -73.92), ("ST2", None, None)])

    result = qcb.filter_points_in_polygon(df, _brooklyn_square())

    assert list(result["order_number"]) == ["ST1"]


def test_filter_points_in_polygon_handles_an_empty_frame():
    result = qcb.filter_points_in_polygon(_df([]), _brooklyn_square())
    assert result.empty


# --- optional Socrata app token ---


def test_app_token_headers_is_empty_when_no_token_is_configured():
    assert qcb.app_token_headers(env={}) == {}


def test_app_token_headers_uses_socrata_app_token():
    headers = qcb.app_token_headers(env={"SOCRATA_APP_TOKEN": "abc123"})
    assert headers == {"X-App-Token": "abc123"}


def test_app_token_headers_accepts_the_nyc_open_data_alias():
    headers = qcb.app_token_headers(env={"NYC_OPEN_DATA_APP_TOKEN": "xyz789"})
    assert headers == {"X-App-Token": "xyz789"}


def test_app_token_headers_ignores_a_blank_token():
    assert qcb.app_token_headers(env={"SOCRATA_APP_TOKEN": "   "}) == {}


# --- paginated fetch ---


def _resp(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def test_fetch_all_records_pages_until_a_short_page_arrives():
    page1 = [{"order_number": "ST1"}, {"order_number": "ST2"}]
    page2 = [{"order_number": "ST3"}]

    with patch.object(qcb.requests, "get", side_effect=[_resp(page1), _resp(page2)]) as mock_get:
        records = qcb.fetch_all_records("1=1", page_limit=2)

    assert [r["order_number"] for r in records] == ["ST1", "ST2", "ST3"]
    offsets = [call.kwargs["params"]["$offset"] for call in mock_get.call_args_list]
    assert offsets == [0, 2]


def test_fetch_all_records_stops_immediately_on_an_empty_first_page():
    with patch.object(qcb.requests, "get", side_effect=[_resp([])]) as mock_get:
        records = qcb.fetch_all_records("1=1", page_limit=2)

    assert records == []
    assert mock_get.call_count == 1


def test_fetch_all_records_orders_by_id_for_stable_pagination():
    with patch.object(qcb.requests, "get", side_effect=[_resp([])]) as mock_get:
        qcb.fetch_all_records("1=1", page_limit=2)

    params = mock_get.call_args.kwargs["params"]
    assert params["$order"] == ":id"
    assert params["$where"] == "1=1"


def test_fetch_all_records_sends_the_app_token_header_when_present():
    with patch.object(qcb.requests, "get", side_effect=[_resp([])]) as mock_get:
        qcb.fetch_all_records("1=1", page_limit=2, headers={"X-App-Token": "abc123"})

    assert mock_get.call_args.kwargs["headers"] == {"X-App-Token": "abc123"}


# --- reuse of the ZIP script's query contract ---


def test_where_clause_comes_from_the_zip_scripts_builder():
    where_parts = qcb.qsz.build_where_parts(0, 100, 0, 100, active_only=True)
    assert "record_type != 'Historical'" in where_parts
    assert "(sign_code like 'SN-%' OR sign_code like 'SI-%')" in where_parts


def test_columns_come_from_the_zip_scripts_col_list():
    assert qcb.COLS is qcb.qsz.COLS
    assert qcb.COLS[0] == "order_number"
