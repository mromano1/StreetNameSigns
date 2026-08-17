"""
Tests for 01_query_sims_by_zip.py's --include-historical support. Loaded via
importlib since the filename starts with a digit.
"""
import importlib.util
from pathlib import Path

from pyproj import Transformer

MODULE_PATH = Path(__file__).parent / "01_query_sims_by_zip.py"
spec = importlib.util.spec_from_file_location("query_sims_by_zip", MODULE_PATH)
qsz = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qsz)


def test_active_only_excludes_historical_records():
    where_parts = qsz.build_where_parts(0, 100, 0, 100, active_only=True)
    assert "record_type != 'Historical'" in where_parts


def test_include_historical_does_not_exclude_historical_records():
    where_parts = qsz.build_where_parts(0, 100, 0, 100, active_only=False)
    assert "record_type != 'Historical'" not in where_parts


def test_output_filename_default_has_no_history_suffix():
    assert qsz.output_filename("10001", include_historical=False) == "signs_zip_10001.csv"


def test_output_filename_with_history_flag_has_history_suffix():
    assert qsz.output_filename("10001", include_historical=True) == "signs_zip_10001_history.csv"


def _to_wgs():
    return Transformer.from_crs("EPSG:2263", "EPSG:4326", always_xy=True)


def test_normalize_records_derives_lat_lon_from_state_plane_coords():
    raw = [{
        "order_number": "ST01667358",
        "sign_code": "SN-1",
        "sign_x_coord": "1005000",
        "sign_y_coord": "190000",
    }]

    df = qsz.normalize_records(raw, _to_wgs())

    assert 40.5 < df.loc[0, "latitude"] < 41.0
    assert -74.3 < df.loc[0, "longitude"] < -73.7


def test_normalize_records_keeps_only_the_expected_columns():
    raw = [{
        "order_number": "ST01667358",
        "sign_x_coord": "1005000",
        "sign_y_coord": "190000",
        "not_in_cols": "drop me",
    }]

    df = qsz.normalize_records(raw, _to_wgs())

    assert "not_in_cols" not in df.columns
    assert set(df.columns) <= set(qsz.COLS)


def test_normalize_records_returns_an_empty_frame_for_no_records():
    assert qsz.normalize_records([], _to_wgs()).empty
