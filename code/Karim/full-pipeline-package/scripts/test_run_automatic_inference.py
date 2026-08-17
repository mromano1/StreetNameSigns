import run_automatic_inference as rai


def test_clamp_box_leaves_an_in_bounds_box_unchanged():
    assert rai.clamp_box((100, 200, 300, 400), image_width=3200, image_height=2400) == (100, 200, 300, 400)


def test_clamp_box_clamps_negative_and_overflowing_coordinates():
    assert rai.clamp_box((-5, -5, 3205, 2405), image_width=3200, image_height=2400) == (0, 0, 3200, 2400)


def test_clamp_box_clamps_only_the_edge_that_overflows():
    assert rai.clamp_box((100, -10, 300, 400), image_width=3200, image_height=2400) == (100, 0, 300, 400)


def test_summarize_detection_picks_the_highest_confidence_flagged_class():
    predictions = [("faded", 0.4), ("old_design", 0.6), ("bent_damaged", 0.1)]
    row = rai.summarize_detection("C1", 0, box_conf=0.9, damage_predictions=predictions, threshold=0.25)
    assert row["damage"] == "old_design"
    assert row["damage_confidence"] == 0.6
    assert row["corner_id"] == "C1"
    assert row["box_index"] == 0
    assert row["box_confidence"] == 0.9


def test_summarize_detection_is_no_damage_when_nothing_meets_threshold():
    predictions = [("faded", 0.1), ("old_design", 0.05)]
    row = rai.summarize_detection("C1", 0, box_conf=0.9, damage_predictions=predictions, threshold=0.25)
    assert row["damage"] == "no_damage"
    assert row["damage_confidence"] is None


def test_summarize_detection_is_no_damage_for_empty_predictions():
    row = rai.summarize_detection("C1", 0, box_conf=0.9, damage_predictions=[], threshold=0.25)
    assert row["damage"] == "no_damage"


def test_summarize_detection_uses_the_module_default_threshold_when_not_given():
    # Default threshold matches the deployed model's own CONF_THRESHOLD
    # (0.25, from report_physical.py) -- 0.2 should NOT clear it.
    predictions = [("faded", 0.2)]
    row = rai.summarize_detection("C1", 0, box_conf=0.9, damage_predictions=predictions)
    assert row["damage"] == "no_damage"


def test_build_html_report_with_no_rows_says_nothing_was_found():
    html = rai.build_html_report([], {}, board_label="cb211")
    assert "found nothing" in html.lower()
    assert "cb211" in html


def test_build_html_report_includes_each_rows_corner_and_damage_class():
    rows = [
        rai.summarize_detection("cb211_000", 0, 0.8, [("faded", 0.6)]),
        rai.summarize_detection("cb211_001", 0, 0.5, []),
    ]
    html = rai.build_html_report(rows, {}, board_label="cb211")
    assert "cb211_000" in html
    assert "faded" in html
    assert "cb211_001" in html
    assert "no_damage" in html


def test_build_html_report_discloses_the_spatial_models_map50():
    html = rai.build_html_report([], {}, board_label="cb211")
    assert str(rai.SPATIAL_MAP50) in html


def test_build_html_report_embeds_a_crop_thumbnail_when_the_file_exists(tmp_path):
    crop_path = tmp_path / "crop.jpg"
    crop_path.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-for-embedding-test")
    rows = [rai.summarize_detection("C1", 0, 0.8, [("faded", 0.6)])]
    html = rai.build_html_report(rows, {("C1", 0): crop_path}, board_label="cb211")
    assert "data:image/jpeg;base64," in html
