import prepare_yolo_dataset_physical as pydp


def test_classify_no_damage_is_negative():
    assert pydp.classify_damage_category("no damage") == ([], False, [])


def test_classify_single_physical_token():
    assert pydp.classify_damage_category("faded") == (["faded"], False, [])


def test_classify_white_border_and_all_caps_map_to_old_design():
    assert pydp.classify_damage_category("white-border") == (["old_design"], False, [])
    assert pydp.classify_damage_category("all-caps") == (["old_design"], False, [])


def test_classify_multiple_physical_tokens_deduped():
    assert pydp.classify_damage_category("white-border;all-caps") == (["old_design"], False, [])


def test_classify_multiple_physical_tokens_preserved_in_order():
    assert pydp.classify_damage_category("faded;bent") == (["faded", "bent_damaged"], False, [])


def test_classify_pure_intersection_token_is_dropped():
    assert pydp.classify_damage_category("missing") == ([], True, [])
    assert pydp.classify_damage_category("wrong-direction") == ([], True, [])


def test_classify_mixed_intersection_and_physical_keeps_physical_only():
    assert pydp.classify_damage_category("wrong-direction;faded") == (["faded"], False, [])


def test_classify_unrecognized_token_is_dropped_with_warning():
    assert pydp.classify_damage_category("some-garbage") == ([], True, ["some-garbage"])


def test_classify_pure_artifact_token_is_dropped_cleanly():
    assert pydp.classify_damage_category("artifact") == ([], True, [])


def test_classify_artifact_mixed_with_physical_token_drops_entirely():
    # Unlike intersection tags, an artifact tag means the image itself is
    # untrustworthy -- any co-tagged physical damage is dropped too, not
    # salvaged.
    assert pydp.classify_damage_category("artifact;bent") == ([], True, [])
    assert pydp.classify_damage_category("bent;artifact") == ([], True, [])


def test_load_rows_keeps_physical_and_negative_rows(tmp_path):
    capture_dir = tmp_path / "manual_capture"
    capture_dir.mkdir()
    (capture_dir / "a.jpg").write_bytes(b"x")
    (capture_dir / "b.jpg").write_bytes(b"x")
    manifest = capture_dir / "manifest_1.csv"
    manifest.write_text(
        "filename,damage_category\n"
        "a.jpg,faded\n"
        "b.jpg,no damage\n",
        encoding="utf-8",
    )

    rows, warnings = pydp.load_rows([manifest])

    assert warnings == []
    paths_and_classes = {p.name: c for p, c in rows}
    assert paths_and_classes["a.jpg"] == ["faded"]
    assert paths_and_classes["b.jpg"] == []


def test_load_rows_drops_pure_intersection_row(tmp_path):
    capture_dir = tmp_path / "manual_capture"
    capture_dir.mkdir()
    (capture_dir / "a.jpg").write_bytes(b"x")
    manifest = capture_dir / "manifest_1.csv"
    manifest.write_text(
        "filename,damage_category\n"
        "a.jpg,missing\n",
        encoding="utf-8",
    )

    rows, warnings = pydp.load_rows([manifest])

    assert rows == []
    assert len(warnings) == 1
    assert "a.jpg" in warnings[0]


def test_load_rows_drops_artifact_row_with_accurate_warning(tmp_path):
    capture_dir = tmp_path / "manual_capture"
    capture_dir.mkdir()
    (capture_dir / "a.jpg").write_bytes(b"x")
    manifest = capture_dir / "manifest_1.csv"
    manifest.write_text(
        "filename,damage_category\n"
        "a.jpg,artifact\n",
        encoding="utf-8",
    )

    rows, warnings = pydp.load_rows([manifest])

    assert rows == []
    assert len(warnings) == 1
    assert "artifact" in warnings[0]
    assert "a.jpg" in warnings[0]
    assert "unrecognized" not in warnings[0]


def test_load_rows_drops_artifact_mixed_with_physical_row(tmp_path):
    capture_dir = tmp_path / "manual_capture"
    capture_dir.mkdir()
    (capture_dir / "a.jpg").write_bytes(b"x")
    manifest = capture_dir / "manifest_1.csv"
    manifest.write_text(
        "filename,damage_category\n"
        "a.jpg,artifact;bent\n",
        encoding="utf-8",
    )

    rows, warnings = pydp.load_rows([manifest])

    assert rows == []
    assert len(warnings) == 1
    assert "artifact" in warnings[0]
    assert "unrecognized" not in warnings[0]


def test_load_rows_keeps_mixed_row_with_physical_tag_only(tmp_path):
    capture_dir = tmp_path / "manual_capture"
    capture_dir.mkdir()
    (capture_dir / "a.jpg").write_bytes(b"x")
    manifest = capture_dir / "manifest_1.csv"
    manifest.write_text(
        "filename,damage_category\n"
        "a.jpg,wrong-direction;faded\n",
        encoding="utf-8",
    )

    rows, warnings = pydp.load_rows([manifest])

    assert len(rows) == 1
    assert rows[0][1] == ["faded"]


def test_load_rows_skips_missing_file(tmp_path):
    capture_dir = tmp_path / "manual_capture"
    capture_dir.mkdir()
    manifest = capture_dir / "manifest_1.csv"
    manifest.write_text(
        "filename,damage_category\n"
        "missing.jpg,faded\n",
        encoding="utf-8",
    )

    rows, warnings = pydp.load_rows([manifest])

    assert rows == []
    assert "missing file" in warnings[0]


def test_load_rows_skips_blank_damage_category(tmp_path):
    capture_dir = tmp_path / "manual_capture"
    capture_dir.mkdir()
    (capture_dir / "a.jpg").write_bytes(b"x")
    manifest = capture_dir / "manifest_1.csv"
    manifest.write_text(
        "filename,damage_category\n"
        "a.jpg,\n",
        encoding="utf-8",
    )

    rows, warnings = pydp.load_rows([manifest])

    assert rows == []
    assert "blank" in warnings[0]


def test_load_rows_skips_duplicate_filename_across_manifests(tmp_path):
    capture_dir = tmp_path / "manual_capture"
    capture_dir.mkdir()
    (capture_dir / "a.jpg").write_bytes(b"x")
    manifest1 = capture_dir / "manifest_1.csv"
    manifest1.write_text("filename,damage_category\na.jpg,faded\n", encoding="utf-8")
    manifest2 = capture_dir / "manifest_2.csv"
    manifest2.write_text("filename,damage_category\na.jpg,hanging\n", encoding="utf-8")

    rows, warnings = pydp.load_rows([manifest1, manifest2])

    assert len(rows) == 1
    assert any("duplicate" in w for w in warnings)


def test_find_manifests_discovers_under_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(pydp, "DATA_DIR", tmp_path)
    capture_dir = tmp_path / "raw_images" / "zip_10001" / "manual_capture"
    capture_dir.mkdir(parents=True)
    (capture_dir / "manifest_1.csv").write_text("filename,damage_category\n", encoding="utf-8")

    manifests = pydp.find_manifests()

    assert manifests == [capture_dir / "manifest_1.csv"]


def test_load_class_ids_parses_names_block(tmp_path):
    yaml_path = tmp_path / "data_physical.yaml"
    yaml_path.write_text(
        "path: /whatever\n"
        "train: images/train\n"
        "names:\n"
        "  0: old_design\n"
        "  1: faded\n"
        "  2: bent_damaged\n"
        "  3: hanging\n"
        "  4: vandalized\n",
        encoding="utf-8",
    )

    ids = pydp.load_class_ids(yaml_path)

    assert ids == {"old_design": 0, "faded": 1, "bent_damaged": 2, "hanging": 3, "vandalized": 4}


def test_split_rows_all_go_to_train_below_min_val_threshold():
    rows = [(f"img{i}.jpg", ["faded"]) for i in range(3)]
    train, val = pydp.split_rows(rows)
    assert len(train) == 3
    assert len(val) == 0


def test_split_rows_splits_when_at_min_threshold():
    rows = [(f"img{i}.jpg", ["faded"]) for i in range(5)]
    train, val = pydp.split_rows(rows)
    assert len(train) == 4
    assert len(val) == 1


def test_split_rows_preserves_all_rows_with_multi_label_data():
    rows = (
        [(f"a{i}.jpg", ["old_design"]) for i in range(20)]
        + [(f"b{i}.jpg", ["faded"]) for i in range(15)]
        + [(f"c{i}.jpg", ["old_design", "faded"]) for i in range(8)]
        + [(f"d{i}.jpg", []) for i in range(10)]
    )
    train, val = pydp.split_rows(rows)
    assert len(train) + len(val) == len(rows)
    assert {p for p, _ in train} | {p for p, _ in val} == {p for p, _ in rows}
    assert {p for p, _ in train} & {p for p, _ in val} == set()


def test_split_rows_gives_secondary_only_class_val_representation():
    # "hanging" never appears as the primary (first) label here -- under
    # naive primary-only stratification it would never control its own
    # split and could end up with zero val examples purely by luck.
    rows = (
        [(f"primary{i}.jpg", ["old_design"]) for i in range(20)]
        + [(f"combo{i}.jpg", ["old_design", "hanging"]) for i in range(6)]
    )
    train, val = pydp.split_rows(rows)

    val_names = {p for p, _ in val}
    hanging_in_val = [n for n in val_names if n.startswith("combo")]
    assert len(hanging_in_val) >= 1


def test_split_rows_rare_secondary_class_below_threshold_stays_train_only():
    # Only 2 total "vandalized" occurrences -- too few to honestly split
    # (would require duplicating an image across train and val).
    rows = (
        [(f"primary{i}.jpg", ["old_design"]) for i in range(20)]
        + [(f"combo{i}.jpg", ["old_design", "vandalized"]) for i in range(2)]
    )
    train, val = pydp.split_rows(rows)

    val_names = {p for p, _ in val}
    vandalized_in_val = [n for n in val_names if n.startswith("combo")]
    assert vandalized_in_val == []


def test_write_split_copies_images_and_writes_labels(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    image_path = src_dir / "a.jpg"
    image_path.write_bytes(b"fake jpeg bytes")
    out_images = tmp_path / "out" / "images"
    out_labels = tmp_path / "out" / "labels"
    class_ids = {"old_design": 0, "faded": 1, "bent_damaged": 2, "hanging": 3, "vandalized": 4}

    pydp.write_split("train", [(image_path, ["faded"])], class_ids, out_images, out_labels)

    assert (out_images / "train" / "a.jpg").read_bytes() == b"fake jpeg bytes"
    label_content = (out_labels / "train" / "a.txt").read_text()
    assert label_content.strip() == "1 0.5 0.5 0.9 0.9"


def test_write_split_writes_empty_label_for_negative(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    image_path = src_dir / "b.jpg"
    image_path.write_bytes(b"x")
    out_images = tmp_path / "out" / "images"
    out_labels = tmp_path / "out" / "labels"
    class_ids = {"old_design": 0, "faded": 1, "bent_damaged": 2, "hanging": 3, "vandalized": 4}

    pydp.write_split("train", [(image_path, [])], class_ids, out_images, out_labels)

    assert (out_labels / "train" / "b.txt").read_text() == ""


def test_main_writes_physical_dataset_end_to_end(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    capture_dir = data_dir / "raw_images" / "zip_10001" / "manual_capture"
    capture_dir.mkdir(parents=True)
    for i in range(6):
        (capture_dir / f"img{i}.jpg").write_bytes(b"x")
    manifest = capture_dir / "manifest_1.csv"
    manifest.write_text(
        "filename,damage_category\n"
        "img0.jpg,faded\n"
        "img1.jpg,faded\n"
        "img2.jpg,faded\n"
        "img3.jpg,faded\n"
        "img4.jpg,faded\n"
        "img5.jpg,no damage\n",
        encoding="utf-8",
    )
    yaml_path = tmp_path / "data_physical.yaml"
    yaml_path.write_text(
        "names:\n"
        "  0: old_design\n"
        "  1: faded\n"
        "  2: bent_damaged\n"
        "  3: hanging\n"
        "  4: vandalized\n",
        encoding="utf-8",
    )
    out_images = tmp_path / "out" / "images"
    out_labels = tmp_path / "out" / "labels"

    monkeypatch.setattr(pydp, "DATA_DIR", data_dir)
    monkeypatch.setattr(pydp, "DATA_YAML", yaml_path)
    monkeypatch.setattr(pydp, "OUT_IMAGES", out_images)
    monkeypatch.setattr(pydp, "OUT_LABELS", out_labels)

    pydp.main()

    train_imgs = list((out_images / "train").glob("*.jpg"))
    val_imgs = list((out_images / "val").glob("*.jpg"))
    assert len(train_imgs) + len(val_imgs) == 6
    label_files = list((out_labels / "train").glob("*.txt")) + list((out_labels / "val").glob("*.txt"))
    assert len(label_files) == 6
    faded_labels = [f.read_text().strip() for f in label_files if f.read_text().strip()]
    assert all(content.split()[0] == "1" for content in faded_labels)
