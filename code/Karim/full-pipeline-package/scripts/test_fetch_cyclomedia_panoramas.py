from datetime import date
from unittest.mock import patch

import fetch_cyclomedia_panoramas as fcp


def test_build_fetch_jobs_creates_one_latest_job_per_corner():
    signs_data = {
        "corners": [
            {
                "corner_id": "10001_000",
                "latitude": 40.8,
                "longitude": -73.9,
                "signs": [{"sign_code": "SN-1A", "sign_location": "N/E C"}],
            }
        ]
    }
    jobs = fcp.build_fetch_jobs(signs_data, signs_history=None)

    assert len(jobs) == 1
    job = jobs[0]
    assert job["image_kind"] == "latest"
    assert job["corner_id"] == "10001_000"
    assert job["lat"] == 40.8
    assert job["lon"] == -73.9
    assert job["heading"] == 45.0


def test_build_fetch_jobs_defaults_heading_when_no_classifiable_sign_location():
    signs_data = {
        "corners": [
            {
                "corner_id": "10001_000",
                "latitude": 40.8,
                "longitude": -73.9,
                "signs": [{"sign_code": "SN-1A", "sign_location": "N MALL"}],
            }
        ]
    }
    jobs = fcp.build_fetch_jobs(signs_data, signs_history=None)

    assert jobs[0]["heading"] == 0.0


def test_build_fetch_jobs_adds_prior_to_replacement_job():
    signs_data = {"corners": []}
    signs_history = {
        "threads": [
            {
                "corner_id": "10001_000",
                "lat_r": 40.8,
                "lon_r": -73.9,
                "sign_code": "SN-1A",
                "sign_location": "N/E C",
                "current": {"order_number": "A", "order_completed_on_date": "2024-03-06T00:00:00"},
                "prior_to_replacement": {"order_number": "B", "order_completed_on_date": "2023-01-01T00:00:00"},
            }
        ]
    }
    jobs = fcp.build_fetch_jobs(signs_data, signs_history)

    prior_jobs = [j for j in jobs if j["image_kind"] == "prior_to_replacement"]
    assert len(prior_jobs) == 1
    job = prior_jobs[0]
    assert job["corner_id"] == "10001_000"
    assert job["sign_code"] == "SN-1A"
    assert job["heading"] == 45.0
    assert job["before_date"] == date(2024, 3, 6)


def test_build_fetch_jobs_skips_threads_without_prior_to_replacement():
    signs_data = {"corners": []}
    signs_history = {
        "threads": [
            {
                "corner_id": "10001_000", "lat_r": 40.8, "lon_r": -73.9,
                "sign_code": "SN-1A", "sign_location": "N/E C",
                "current": {"order_number": "A", "order_completed_on_date": "2024-03-06T00:00:00"},
                "prior_to_replacement": None,
            }
        ]
    }
    jobs = fcp.build_fetch_jobs(signs_data, signs_history)
    assert jobs == []


def test_build_fetch_jobs_handles_missing_signs_history():
    signs_data = {"corners": []}
    jobs = fcp.build_fetch_jobs(signs_data, signs_history=None)
    assert jobs == []


def test_run_job_latest_calls_find_nearest_recording_and_renders(tmp_path):
    job = {"image_kind": "latest", "corner_id": "10001_000", "lat": 40.8, "lon": -73.9, "heading": 45.0}

    with patch("fetch_cyclomedia_panoramas.cc.find_nearest_recording", return_value="REC1") as find_mock, \
         patch("fetch_cyclomedia_panoramas.cc.render_recording", return_value=b"JPEG") as render_mock:
        entry = fcp.run_job(job, output_dir=tmp_path)

    find_mock.assert_called_once_with(40.8, -73.9)
    render_mock.assert_called_once_with(
        "REC1", 45.0, width=fcp.RENDER_WIDTH, height=fcp.RENDER_HEIGHT, fov=fcp.WIDE_HFOV
    )
    assert entry["status"] == "ok"
    assert entry["recording_id"] == "REC1"
    saved_path = tmp_path / entry["path"]
    assert saved_path.exists()
    assert saved_path.read_bytes() == b"JPEG"


def test_run_job_prior_to_replacement_calls_date_lookup(tmp_path):
    job = {
        "image_kind": "prior_to_replacement", "corner_id": "10001_000",
        "lat": 40.8, "lon": -73.9, "heading": 45.0, "before_date": date(2024, 3, 6),
        "sign_code": "SN-1A",
    }

    with patch("fetch_cyclomedia_panoramas.cc.find_nearest_recording_at_date", return_value="REC2") as find_mock, \
         patch("fetch_cyclomedia_panoramas.cc.render_recording", return_value=b"OLDJPEG"):
        entry = fcp.run_job(job, output_dir=tmp_path)

    find_mock.assert_called_once_with(40.8, -73.9, before_date=date(2024, 3, 6))
    assert entry["status"] == "ok"
    assert entry["recording_id"] == "REC2"


def test_run_job_records_failure_without_raising(tmp_path):
    job = {"image_kind": "latest", "corner_id": "10001_000", "lat": 40.8, "lon": -73.9, "heading": 45.0}

    with patch("fetch_cyclomedia_panoramas.cc.find_nearest_recording", return_value=None):
        entry = fcp.run_job(job, output_dir=tmp_path)

    assert entry["status"] == "failed"
    assert "no recording" in entry["error"].lower()


def test_run_job_records_failure_on_cyclomedia_error(tmp_path):
    import cyclomedia_client as cc

    job = {"image_kind": "latest", "corner_id": "10001_000", "lat": 40.8, "lon": -73.9, "heading": 45.0}

    with patch("fetch_cyclomedia_panoramas.cc.find_nearest_recording", return_value="REC1"), \
         patch("fetch_cyclomedia_panoramas.cc.render_recording", side_effect=cc.CyclomediaError("boom")):
        entry = fcp.run_job(job, output_dir=tmp_path)

    assert entry["status"] == "failed"
    assert "boom" in entry["error"]


def test_run_job_records_failure_on_oserror_instead_of_raising(tmp_path):
    # run_job's docstring promises it never raises -- mkdir/write_bytes sit
    # outside the cc.CyclomediaError try/except, so a Windows long-path (or
    # any other filesystem) OSError used to propagate straight out of
    # run_job and crash the whole batch loop in main(), losing every
    # already-fetched job's manifest entry. This must be caught the same
    # way cc.CyclomediaError already is.
    job = {"image_kind": "latest", "corner_id": "10001_000", "lat": 40.8, "lon": -73.9, "heading": 45.0}

    with patch("fetch_cyclomedia_panoramas.cc.find_nearest_recording", return_value="REC1"), \
         patch("fetch_cyclomedia_panoramas.cc.render_recording", return_value=b"JPEG"), \
         patch("pathlib.Path.mkdir", side_effect=OSError("[WinError 3] The system cannot find the path specified")):
        entry = fcp.run_job(job, output_dir=tmp_path)

    assert entry["status"] == "failed"
    assert "cannot find the path" in entry["error"]


def test_run_job_skips_when_output_already_exists(tmp_path):
    job = {"image_kind": "latest", "corner_id": "10001_000", "lat": 40.8, "lon": -73.9, "heading": 45.0}
    out_path = tmp_path / fcp.job_relative_path(job)
    out_path.parent.mkdir(parents=True)
    out_path.write_bytes(b"already there")

    with patch("fetch_cyclomedia_panoramas.cc.find_nearest_recording") as find_mock:
        entry = fcp.run_job(job, output_dir=tmp_path)

    find_mock.assert_not_called()
    assert entry["status"] == "skipped"


def test_parse_cli_args_without_output_dir_returns_none():
    from pathlib import Path
    signs_path, history_path, output_dir, limit, multi_angle = fcp.parse_cli_args(["signs.json"])
    assert signs_path == "signs.json"
    assert history_path is None
    assert output_dir is None


def test_parse_cli_args_with_history_path():
    from pathlib import Path
    signs_path, history_path, output_dir, limit, multi_angle = fcp.parse_cli_args(["signs.json", "history.json"])
    assert signs_path == "signs.json"
    assert history_path == "history.json"
    assert output_dir is None


def test_parse_cli_args_with_output_dir_flag():
    from pathlib import Path
    signs_path, history_path, output_dir, limit, multi_angle = fcp.parse_cli_args(["signs.json", "--output-dir", "some/dir"])
    assert signs_path == "signs.json"
    assert history_path is None
    assert output_dir == Path("some/dir")


def test_parse_cli_args_output_dir_can_appear_before_positional_args():
    from pathlib import Path
    signs_path, history_path, output_dir, limit, multi_angle = fcp.parse_cli_args(["--output-dir", "some/dir", "signs.json", "history.json"])
    assert signs_path == "signs.json"
    assert history_path == "history.json"
    assert output_dir == Path("some/dir")


def test_parse_cli_args_raises_when_output_dir_has_no_path():
    try:
        fcp.parse_cli_args(["signs.json", "--output-dir"])
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_parse_cli_args_raises_for_no_args():
    try:
        fcp.parse_cli_args([])
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_parse_cli_args_without_limit_returns_none():
    signs_path, history_path, output_dir, limit, multi_angle = fcp.parse_cli_args(["signs.json"])
    assert limit is None


def test_parse_cli_args_with_limit_flag():
    signs_path, history_path, output_dir, limit, multi_angle = fcp.parse_cli_args(["signs.json", "--limit", "10"])
    assert signs_path == "signs.json"
    assert limit == 10


def test_parse_cli_args_limit_can_appear_before_positional_args():
    signs_path, history_path, output_dir, limit, multi_angle = fcp.parse_cli_args(["--limit", "5", "signs.json"])
    assert signs_path == "signs.json"
    assert limit == 5


def test_parse_cli_args_limit_and_output_dir_together():
    from pathlib import Path
    signs_path, history_path, output_dir, limit, multi_angle = fcp.parse_cli_args(
        ["signs.json", "--output-dir", "some/dir", "--limit", "20"]
    )
    assert signs_path == "signs.json"
    assert output_dir == Path("some/dir")
    assert limit == 20


def test_parse_cli_args_raises_when_limit_has_no_value():
    try:
        fcp.parse_cli_args(["signs.json", "--limit"])
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_parse_cli_args_raises_when_limit_is_not_an_integer():
    try:
        fcp.parse_cli_args(["signs.json", "--limit", "abc"])
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def _corner(corner_id, x, y):
    return {"corner_id": corner_id, "x_2263": x, "y_2263": y, "signs": []}


def test_bearing_deg_north_is_zero():
    assert fcp._bearing_deg(0, 0, 0, 100) == 0


def test_bearing_deg_east_is_ninety():
    assert fcp._bearing_deg(0, 0, 100, 0) == 90


def test_bearing_deg_wraps_to_positive():
    # Due west: dx=-100, dy=0 -> should read 270, not -90.
    assert fcp._bearing_deg(0, 0, -100, 0) == 270


def test_sort_corners_by_bearing_orders_around_centroid():
    ne = _corner("NE", 100, 100)
    se = _corner("SE", 100, -100)
    sw = _corner("SW", -100, -100)
    nw = _corner("NW", -100, 100)
    sorted_corners = fcp._sort_corners_by_bearing([sw, ne, nw, se], center_x=0, center_y=0)
    assert [c["corner_id"] for c in sorted_corners] == ["NE", "SE", "SW", "NW"]


def test_adjacent_pairs_wraps_around_and_excludes_diagonals():
    a, b, c, d = _corner("A", 0, 0), _corner("B", 1, 0), _corner("C", 2, 0), _corner("D", 3, 0)
    pairs = fcp._adjacent_pairs([a, b, c, d])
    pair_ids = [(p[0]["corner_id"], p[1]["corner_id"]) for p in pairs]
    assert pair_ids == [("A", "B"), ("B", "C"), ("C", "D"), ("D", "A")]
    assert ("A", "C") not in pair_ids  # never a diagonal


def test_adjacent_pairs_two_corners_produces_exactly_one_pair():
    # Naive wrap-around (i, i+1 mod n) would produce the SAME physical
    # segment twice for n=2 (A->B and B->A) -- a real duplicate-job bug
    # caught while designing this: a 2-corner cluster only has one side.
    a, b = _corner("A", 0, 0), _corner("B", 10, 0)
    pairs = fcp._adjacent_pairs([a, b])
    assert len(pairs) == 1
    assert (pairs[0][0]["corner_id"], pairs[0][1]["corner_id"]) == ("A", "B")


def test_cluster_corners_into_intersections_groups_a_four_way():
    corners = [
        _corner("NE", 100, 100), _corner("SE", 100, -100),
        _corner("SW", -100, -100), _corner("NW", -100, 100),
    ]
    clusters = fcp.cluster_corners_into_intersections(corners, threshold_ft=500)
    assert len(clusters) == 1
    assert {c["corner_id"] for c in clusters[0]} == {"NE", "SE", "SW", "NW"}


def test_cluster_corners_into_intersections_drops_isolated_corners():
    close_pair = [_corner("A", 0, 0), _corner("B", 10, 0)]
    isolated = [_corner("C", 100_000, 100_000)]
    clusters = fcp.cluster_corners_into_intersections(close_pair + isolated, threshold_ft=50)
    assert len(clusters) == 1
    assert {c["corner_id"] for c in clusters[0]} == {"A", "B"}


def test_cluster_corners_into_intersections_drops_oversized_cluster(capsys):
    # One cluster of MAX_INTERSECTION_CLUSTER_SIZE + 1 corners, all mutually
    # within threshold_ft -- real neighborhood-scale over-clustering (like
    # cb101's 49-corner cluster at the reviewer-measured default threshold),
    # not a plausible intersection. Must be dropped entirely, not turned
    # into a job with a huge intersection_id/path.
    oversized = [_corner(f"C{i}", i, 0) for i in range(fcp.MAX_INTERSECTION_CLUSTER_SIZE + 1)]
    clusters = fcp.cluster_corners_into_intersections(oversized, threshold_ft=1000)

    assert clusters == []
    captured = capsys.readouterr()
    assert str(fcp.MAX_INTERSECTION_CLUSTER_SIZE + 1) in captured.out
    assert "C0" in captured.out


def test_cluster_corners_into_intersections_keeps_cluster_at_the_cap():
    at_cap = [_corner(f"C{i}", i, 0) for i in range(fcp.MAX_INTERSECTION_CLUSTER_SIZE)]
    clusters = fcp.cluster_corners_into_intersections(at_cap, threshold_ft=1000)
    assert len(clusters) == 1
    assert len(clusters[0]) == fcp.MAX_INTERSECTION_CLUSTER_SIZE


def test_build_intersection_jobs_creates_center_and_side_jobs():
    corner_a = _corner("A", 1000000, 200000)
    corner_b = _corner("B", 1000100, 200000)
    clusters = [[corner_a, corner_b]]

    jobs = fcp.build_intersection_jobs(clusters)

    assert len(jobs) == 2
    center_job = next(j for j in jobs if j["image_kind"] == "center")
    side_job = next(j for j in jobs if j["image_kind"] == "side")

    assert center_job["corner_ids"] == ["A", "B"]
    assert center_job["intersection_id"] == "A+B"
    assert abs(center_job["lat"] - 40.715616389571) < 0.0001
    assert abs(center_job["lon"] - (-73.94300470345063)) < 0.0001
    assert center_job["heading"] == 0.0  # no signs given -> falls back to DEFAULT_HEADING

    assert side_job["corner_ids"] == ["A", "B"]
    assert side_job["side_corner_ids"] == ("A", "B")
    assert abs(side_job["lat"] - 40.715616389571) < 0.0001
    assert abs(side_job["lon"] - (-73.94300470345063)) < 0.0001
    # Midpoint == centroid for a 2-corner cluster, so the bearing between
    # them is the degenerate atan2(0, 0) case -- Python defines this as 0.0.
    assert side_job["heading"] == 0.0


def test_build_intersection_jobs_uses_a_signs_heading_when_available():
    corner_a = {"corner_id": "A", "x_2263": 1000000, "y_2263": 200000,
                "signs": [{"sign_location": "N/E C"}]}
    corner_b = _corner("B", 1000100, 200000)
    clusters = [[corner_a, corner_b]]

    jobs = fcp.build_intersection_jobs(clusters)
    center_job = next(j for j in jobs if j["image_kind"] == "center")
    assert center_job["heading"] == 45.0


def test_build_intersection_jobs_three_corners_makes_three_side_jobs():
    corners = [_corner("A", 0, 0), _corner("B", 100, 0), _corner("C", 50, 100)]
    jobs = fcp.build_intersection_jobs([corners])
    center_jobs = [j for j in jobs if j["image_kind"] == "center"]
    side_jobs = [j for j in jobs if j["image_kind"] == "side"]
    assert len(center_jobs) == 1
    assert len(side_jobs) == 3


def test_build_intersection_jobs_bounds_long_intersection_id():
    # Defense-in-depth on top of cluster_corners_into_intersections's own
    # size cap (see test_cluster_corners_into_intersections_drops_oversized_
    # cluster) -- a future cap increase, or any other path that hands
    # build_intersection_jobs an oversized cluster directly, must not
    # reintroduce a 489-char intersection_id / directory name (the real
    # cb101 crash this whole finding is about).
    many_corners = [_corner(f"cb101_{i:03d}", i, 0) for i in range(20)]
    joined = "+".join(sorted(c["corner_id"] for c in many_corners))
    assert len(joined) > 100  # sanity: this really would have exceeded the bound

    jobs = fcp.build_intersection_jobs([many_corners])
    center_job = next(j for j in jobs if j["image_kind"] == "center")

    assert len(center_job["intersection_id"]) <= 100
    # No information lost -- corner_ids still carries every member, only
    # the derived directory-name string is bounded.
    assert center_job["corner_ids"] == sorted(c["corner_id"] for c in many_corners)
    # Deterministic: same input -> same bounded id (so re-running the fetch
    # against the same board resumes/dedupes correctly instead of drifting).
    jobs_again = fcp.build_intersection_jobs([many_corners])
    center_job_again = next(j for j in jobs_again if j["image_kind"] == "center")
    assert center_job["intersection_id"] == center_job_again["intersection_id"]


def test_build_intersection_jobs_handles_multiple_clusters():
    cluster_1 = [_corner("A", 1000000, 200000), _corner("B", 1000100, 200000)]
    cluster_2 = [_corner("C", 5000, 5000), _corner("D", 5100, 5000)]
    jobs = fcp.build_intersection_jobs([cluster_1, cluster_2])
    intersection_ids = {j["intersection_id"] for j in jobs}
    assert intersection_ids == {"A+B", "C+D"}


def test_job_relative_path_for_center_job():
    from pathlib import Path
    job = {"image_kind": "center", "intersection_id": "A+B", "corner_ids": ["A", "B"]}
    assert fcp.job_relative_path(job) == Path("intersections") / "A+B" / "center.jpg"


def test_job_relative_path_for_side_job():
    from pathlib import Path
    job = {
        "image_kind": "side", "intersection_id": "A+B",
        "corner_ids": ["A", "B"], "side_corner_ids": ("A", "B"),
    }
    assert fcp.job_relative_path(job) == Path("intersections") / "A+B" / "side_A_B.jpg"


def test_run_job_works_for_a_center_job(tmp_path):
    job = {
        "image_kind": "center", "intersection_id": "A+B", "corner_ids": ["A", "B"],
        "lat": 40.8, "lon": -73.9, "heading": 10.0,
    }
    with patch("fetch_cyclomedia_panoramas.cc.find_nearest_recording", return_value="REC1"), \
         patch("fetch_cyclomedia_panoramas.cc.render_recording", return_value=b"JPEG"):
        entry = fcp.run_job(job, output_dir=tmp_path)

    assert entry["status"] == "ok"
    saved_path = tmp_path / entry["path"]
    assert saved_path == tmp_path / "intersections" / "A+B" / "center.jpg"
    assert saved_path.exists()
    assert saved_path.read_bytes() == b"JPEG"


def test_parse_cli_args_without_multi_angle_flag_defaults_false():
    signs_path, history_path, output_dir, limit, multi_angle = fcp.parse_cli_args(["signs.json"])
    assert multi_angle is False


def test_parse_cli_args_with_multi_angle_flag():
    signs_path, history_path, output_dir, limit, multi_angle = fcp.parse_cli_args(
        ["signs.json", "--multi-angle"]
    )
    assert signs_path == "signs.json"
    assert multi_angle is True


def test_parse_cli_args_multi_angle_with_other_flags():
    signs_path, history_path, output_dir, limit, multi_angle = fcp.parse_cli_args(
        ["signs.json", "--multi-angle", "--limit", "10"]
    )
    assert multi_angle is True
    assert limit == 10
