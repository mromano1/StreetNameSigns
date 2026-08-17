import backfill_tight_crops as bfc


def _row(**overrides):
    row = {
        "source_image": "cb301_000/img.jpg", "image_kind": "latest",
        "corner_id": "cb301_000", "box_index": "0",
        "bbox_x": "10", "bbox_y": "20", "bbox_w": "100", "bbox_h": "50",
        "image_width": "1000", "image_height": "500",
        "tight_crop_path": "", "flagged": "", "annotated_at": "2026-08-13T00:00:00.000Z",
    }
    row.update(overrides)
    return row


def test_dedupe_latest_keeps_only_the_newer_save_of_a_re_annotated_box():
    rows = [
        _row(box_index="0", bbox_x="10", annotated_at="2026-08-12T22:43:06.900Z"),
        _row(box_index="0", bbox_x="999", annotated_at="2026-08-13T16:58:41.756Z"),
    ]
    result = bfc.dedupe_latest(rows)
    assert len(result) == 1
    assert result[0]["bbox_x"] == "999"


def test_dedupe_latest_keeps_distinct_boxes():
    rows = [_row(box_index="0"), _row(box_index="1")]
    assert len(bfc.dedupe_latest(rows)) == 2


def test_dedupe_latest_skips_rows_with_no_box_index():
    rows = [_row(box_index="")]
    assert bfc.dedupe_latest(rows) == []


def test_backfill_fills_tight_crop_path_from_successful_post():
    rows = [_row(tight_crop_path="")]
    calls = []

    def fake_post(payload):
        calls.append(payload)
        return {"path": "cb301_000/tight_latest_0.jpg", "image_base64": "xx"}

    updated, successes, failures = bfc.backfill(rows, post_fn=fake_post)

    assert successes == 1
    assert failures == []
    assert updated[0]["tight_crop_path"] == "cb301_000/tight_latest_0.jpg"
    assert calls[0] == {
        "corner_id": "cb301_000", "image_kind": "latest", "box_index": 0,
        "box": {"x": 10.0, "y": 20.0, "w": 100.0, "h": 50.0},
    }


def test_backfill_records_a_failure_when_post_fn_returns_none():
    rows = [_row(tight_crop_path="")]
    updated, successes, failures = bfc.backfill(rows, post_fn=lambda payload: None)

    assert successes == 0
    assert failures == [("cb301_000/img.jpg", "0")]
    assert updated[0]["tight_crop_path"] == ""


def test_backfill_skips_rows_that_already_have_a_tight_crop_path():
    rows = [_row(tight_crop_path="already/here.jpg")]
    calls = []
    updated, successes, failures = bfc.backfill(rows, post_fn=lambda p: calls.append(p))

    assert calls == []
    assert successes == 0
    assert failures == []


def test_backfill_skips_flagged_rows():
    rows = [_row(flagged="true", tight_crop_path="")]
    calls = []
    updated, successes, failures = bfc.backfill(rows, post_fn=lambda p: calls.append(p))

    assert calls == []
    assert successes == 0
    assert failures == []
