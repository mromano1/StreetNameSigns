import csv

import prepare_physical_dataset_from_annotations as ppda


FIELDNAMES = [
    "source_image", "image_kind", "corner_id", "box_index",
    "bbox_x", "bbox_y", "bbox_w", "bbox_h", "image_width", "image_height",
    "order_number", "sign_code", "sign_location", "damage_category", "notes",
    "tight_crop_path", "flagged", "annotated_at",
]


def _write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            full = {k: "" for k in FIELDNAMES}
            full.update(row)
            writer.writerow(full)


def _row(**overrides):
    row = {
        "source_image": "cb301_000/img.jpg", "corner_id": "cb301_000", "box_index": "0",
        "damage_category": "white-border", "flagged": "",
        "tight_crop_path": "cb301_000/tight_latest_0.jpg",
        "annotated_at": "2026-08-13T00:00:00.000Z",
    }
    row.update(overrides)
    return row


def _make_tight_crop(panoramas_dir, rel_path):
    p = panoramas_dir / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"fake-jpeg")
    return p


def test_load_rows_uses_the_tight_crop_file_as_the_training_image(tmp_path):
    panoramas_dir = tmp_path / "panoramas"
    _make_tight_crop(panoramas_dir, "cb301_000/tight_latest_0.jpg")
    csv_path = tmp_path / "annotations.csv"
    _write_csv(csv_path, [_row()])

    rows, warnings = ppda.load_rows([csv_path], panoramas_dir)

    assert warnings == []
    assert len(rows) == 1
    image_path, class_names = rows[0]
    assert image_path == panoramas_dir / "cb301_000" / "tight_latest_0.jpg"
    assert class_names == ["old_design"]  # white-border maps to old_design, same as the manual-capture source


def test_load_rows_skips_rows_with_no_tight_crop_path(tmp_path):
    panoramas_dir = tmp_path / "panoramas"
    csv_path = tmp_path / "annotations.csv"
    _write_csv(csv_path, [_row(tight_crop_path="")])

    rows, warnings = ppda.load_rows([csv_path], panoramas_dir)

    assert rows == []
    assert len(warnings) == 1
    assert "no tight crop" in warnings[0].lower()


def test_load_rows_skips_rows_whose_tight_crop_file_is_missing(tmp_path):
    panoramas_dir = tmp_path / "panoramas"  # never created
    csv_path = tmp_path / "annotations.csv"
    _write_csv(csv_path, [_row()])

    rows, warnings = ppda.load_rows([csv_path], panoramas_dir)

    assert rows == []
    assert len(warnings) == 1


def test_load_rows_skips_flagged_rows(tmp_path):
    panoramas_dir = tmp_path / "panoramas"
    _make_tight_crop(panoramas_dir, "cb301_000/tight_latest_0.jpg")
    csv_path = tmp_path / "annotations.csv"
    _write_csv(csv_path, [_row(flagged="true")])

    rows, warnings = ppda.load_rows([csv_path], panoramas_dir)

    assert rows == []


def test_load_rows_drops_intersection_only_damage_category(tmp_path):
    panoramas_dir = tmp_path / "panoramas"
    _make_tight_crop(panoramas_dir, "cb301_000/tight_latest_0.jpg")
    csv_path = tmp_path / "annotations.csv"
    _write_csv(csv_path, [_row(damage_category="missing")])

    rows, warnings = ppda.load_rows([csv_path], panoramas_dir)

    assert rows == []
    assert len(warnings) == 1


def test_load_rows_keeps_no_damage_as_a_negative(tmp_path):
    panoramas_dir = tmp_path / "panoramas"
    _make_tight_crop(panoramas_dir, "cb301_000/tight_latest_0.jpg")
    csv_path = tmp_path / "annotations.csv"
    _write_csv(csv_path, [_row(damage_category="no damage")])

    rows, warnings = ppda.load_rows([csv_path], panoramas_dir)

    assert len(rows) == 1
    assert rows[0][1] == []


def test_load_rows_dedupes_across_multiple_csv_paths(tmp_path):
    panoramas_dir = tmp_path / "panoramas"
    _make_tight_crop(panoramas_dir, "cb301_000/tight_latest_0.jpg")
    old_csv = tmp_path / "old.csv"
    new_csv = tmp_path / "new.csv"
    _write_csv(old_csv, [_row(damage_category="bent", annotated_at="2026-08-12T00:00:00.000Z")])
    _write_csv(new_csv, [_row(damage_category="faded", annotated_at="2026-08-13T00:00:00.000Z")])

    rows, warnings = ppda.load_rows([old_csv, new_csv], panoramas_dir)

    assert len(rows) == 1
    assert rows[0][1] == ["faded"]  # the newer save across the two files wins


def test_write_split_does_not_collide_when_two_corners_share_a_crop_filename(tmp_path, monkeypatch):
    # Every corner's tight crops are named tight_{image_kind}_{box_index}.jpg
    # *within its own corner_id folder* -- e.g. both cb301_000/tight_latest_0.jpg
    # and cb301_001/tight_latest_0.jpg exist simultaneously with the same
    # basename. Copying by bare filename (pydp.write_split's own behavior)
    # would let the second overwrite the first.
    panoramas_dir = tmp_path / "panoramas"
    image_a = _make_tight_crop(panoramas_dir, "cb301_000/tight_latest_0.jpg")
    image_b = _make_tight_crop(panoramas_dir, "cb301_001/tight_latest_0.jpg")
    image_a.write_bytes(b"AAAA")
    image_b.write_bytes(b"BBBB")

    out_images = tmp_path / "out" / "images"
    out_labels = tmp_path / "out" / "labels"
    monkeypatch.setattr(ppda, "OUT_IMAGES", out_images)
    monkeypatch.setattr(ppda, "OUT_LABELS", out_labels)

    items = [(image_a, ["old_design"]), (image_b, [])]
    class_ids = {"old_design": 0}

    ppda.write_split("train", items, class_ids)

    copied = sorted(p.name for p in (out_images / "train").iterdir())
    assert len(copied) == 2, f"expected 2 distinct files, got {copied} (collision)"
    assert (out_images / "train" / "cb301_000_tight_latest_0.jpg").read_bytes() == b"AAAA"
    assert (out_images / "train" / "cb301_001_tight_latest_0.jpg").read_bytes() == b"BBBB"
    assert (out_labels / "train" / "cb301_000_tight_latest_0.txt").exists()
    assert (out_labels / "train" / "cb301_001_tight_latest_0.txt").exists()
