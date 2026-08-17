import annotation_csv_lib as lib


def _row(**overrides):
    row = {"source_image": "cb301_000/img.jpg", "box_index": "0", "annotated_at": "2026-08-13T00:00:00.000Z"}
    row.update(overrides)
    return row


def test_dedupe_latest_boxes_keeps_the_newer_save_of_a_re_annotated_box():
    rows = [
        _row(annotated_at="2026-08-12T22:43:06.900Z", tag="old"),
        _row(annotated_at="2026-08-13T16:58:41.756Z", tag="new"),
    ]
    result = lib.dedupe_latest_boxes(rows)
    assert len(result) == 1
    assert result[0]["tag"] == "new"


def test_dedupe_latest_boxes_keeps_distinct_boxes():
    rows = [_row(box_index="0"), _row(box_index="1")]
    assert len(lib.dedupe_latest_boxes(rows)) == 2


def test_dedupe_latest_boxes_skips_rows_with_no_box_index():
    assert lib.dedupe_latest_boxes([_row(box_index="")]) == []


def test_dedupe_latest_boxes_skips_rows_with_no_source_image():
    assert lib.dedupe_latest_boxes([_row(source_image="")]) == []
