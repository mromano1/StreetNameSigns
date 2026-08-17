"""
Tests for list_panorama_datasets.py's pure list-building logic. Loaded via
importlib since the filename starts with a digit-free but script-style name
(kept consistent with the other numbered scripts' test-loading pattern).
"""
import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).parent / "list_panorama_datasets.py"
spec = importlib.util.spec_from_file_location("list_panorama_datasets", MODULE_PATH)
lpd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lpd)


def test_root_manifest_becomes_the_original_dataset_pointing_at_the_extension_signs_file():
    # The root/original collection's SIMS data is the extension's own live
    # signs_data.json, not anything under cyclomedia_panoramas/ -- that's
    # true regardless of what's on disk there, so it's not conditioned on
    # signs_relpaths at all.
    result = lpd.build_dataset_list(["fetch_manifest.json"])
    assert result == [
        {
            "label": "original",
            "manifest": "/data/cyclomedia_panoramas/fetch_manifest.json",
            "signs": "/extension/signs_data.json",
        }
    ]


def test_subfolder_manifest_uses_folder_name_as_label():
    result = lpd.build_dataset_list(["demo_cb301/fetch_manifest.json"])
    assert result[0]["label"] == "demo_cb301"
    assert result[0]["manifest"] == "/data/cyclomedia_panoramas/demo_cb301/fetch_manifest.json"


def test_subfolder_with_a_colocated_signs_file_points_at_it():
    result = lpd.build_dataset_list(
        ["demo_cb301/fetch_manifest.json"],
        signs_relpaths=["demo_cb301/signs_data.json"],
    )
    assert result[0]["signs"] == "/data/cyclomedia_panoramas/demo_cb301/signs_data.json"


def test_subfolder_without_a_colocated_signs_file_gets_none():
    # No signs_data.json was generated for this collection yet -- None, not
    # a silent fallback to some other dataset's (corner_id-incompatible)
    # signs file, which would just look like "no SIMS match" for every box
    # with no indication why.
    result = lpd.build_dataset_list(["demo_cb301/fetch_manifest.json"], signs_relpaths=[])
    assert result[0]["signs"] is None


def test_root_dataset_always_sorts_first_then_subfolders_alphabetically():
    result = lpd.build_dataset_list([
        "zzz_folder/fetch_manifest.json",
        "fetch_manifest.json",
        "aaa_folder/fetch_manifest.json",
    ])
    assert [d["label"] for d in result] == ["original", "aaa_folder", "zzz_folder"]


def test_no_manifests_returns_empty_list():
    assert lpd.build_dataset_list([]) == []


def test_windows_backslash_paths_are_normalized_to_forward_slashes():
    # glob on Windows yields OS-native separators; the dropdown needs a
    # clean URL path regardless of host OS.
    result = lpd.build_dataset_list(["demo_cb301\\fetch_manifest.json"])
    assert result[0]["manifest"] == "/data/cyclomedia_panoramas/demo_cb301/fetch_manifest.json"


def test_windows_backslash_signs_relpaths_are_matched_correctly():
    result = lpd.build_dataset_list(
        ["demo_cb301\\fetch_manifest.json"],
        signs_relpaths=["demo_cb301\\signs_data.json"],
    )
    assert result[0]["signs"] == "/data/cyclomedia_panoramas/demo_cb301/signs_data.json"
