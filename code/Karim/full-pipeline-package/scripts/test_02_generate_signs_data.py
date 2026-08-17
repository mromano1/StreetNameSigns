"""
Tests for 02_generate_signs_data.py's CLI arg parsing. Loaded via importlib
since the filename starts with a digit.
"""
import importlib.util
import json
from pathlib import Path

MODULE_PATH = Path(__file__).parent / "02_generate_signs_data.py"
spec = importlib.util.spec_from_file_location("generate_signs_data", MODULE_PATH)
gsd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gsd)


def test_parse_cli_args_without_out_returns_none_out_path():
    zip_codes, out_path, csv_path = gsd.parse_cli_args(["10001", "10003"])
    assert zip_codes == ["10001", "10003"]
    assert out_path is None
    assert csv_path is None


def test_parse_cli_args_with_out_extracts_path_and_zips():
    zip_codes, out_path, csv_path = gsd.parse_cli_args(["10001", "--out", "some/path.json"])
    assert zip_codes == ["10001"]
    assert out_path == Path("some/path.json")
    assert csv_path is None


def test_parse_cli_args_out_can_appear_before_zips():
    zip_codes, out_path, csv_path = gsd.parse_cli_args(["--out", "some/path.json", "10001", "10003"])
    assert zip_codes == ["10001", "10003"]
    assert out_path == Path("some/path.json")
    assert csv_path is None


def test_parse_cli_args_raises_for_no_args():
    try:
        gsd.parse_cli_args([])
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_parse_cli_args_raises_when_out_has_no_path():
    try:
        gsd.parse_cli_args(["10001", "--out"])
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_parse_cli_args_raises_when_out_is_only_argument():
    try:
        gsd.parse_cli_args(["--out", "some/path.json"])
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_parse_cli_args_with_csv_extracts_path_and_label():
    zip_codes, out_path, csv_path = gsd.parse_cli_args(["cb301", "--csv", "signs_zip_cb301.csv"])
    assert zip_codes == ["cb301"]
    assert csv_path == Path("signs_zip_cb301.csv")
    assert out_path is None


def test_parse_cli_args_csv_can_appear_before_label():
    zip_codes, out_path, csv_path = gsd.parse_cli_args(["--csv", "some/path.csv", "cb301"])
    assert zip_codes == ["cb301"]
    assert csv_path == Path("some/path.csv")


def test_parse_cli_args_with_both_csv_and_out():
    zip_codes, out_path, csv_path = gsd.parse_cli_args(
        ["cb301", "--csv", "in.csv", "--out", "out.json"]
    )
    assert zip_codes == ["cb301"]
    assert csv_path == Path("in.csv")
    assert out_path == Path("out.json")


def test_parse_cli_args_raises_when_csv_has_no_path():
    try:
        gsd.parse_cli_args(["cb301", "--csv"])
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_parse_cli_args_raises_when_csv_is_only_argument():
    try:
        gsd.parse_cli_args(["--csv", "in.csv"])
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_main_reads_from_explicit_csv_path_instead_of_derived_filename(tmp_path):
    # Deliberately does NOT sit next to a signs_zip_demo.csv -- if main()
    # ignored csv_path and fell back to the derived filename, this would
    # fail with FileNotFoundError instead of succeeding.
    csv_path = tmp_path / "wherever_i_want.csv"
    csv_path.write_text(
        "order_number,sign_code,sign_description,sign_location,support,"
        "on_street,from_street,latitude,longitude,sign_x_coord,sign_y_coord\n"
        "12345,R1-1,STOP,NE,Pole,MAIN ST,1ST AVE,40.7,-73.9,1000.0,2000.0\n"
    )
    out_path = tmp_path / "signs_data.json"

    gsd.main(["demo"], out_path=out_path, csv_path=csv_path)

    data = json.loads(out_path.read_text())
    assert len(data["corners"]) == 1
    assert data["corners"][0]["on_street"] == "MAIN ST"
