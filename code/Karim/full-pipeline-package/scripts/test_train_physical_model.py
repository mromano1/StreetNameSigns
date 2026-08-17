import train_physical_model as tpm


def test_main_raises_systemexit_when_no_labeled_training_data(tmp_path, monkeypatch):
    # main()'s own guard clause: refuses to start a real (slow, GPU-bound)
    # YOLO training run against an empty labels/train/ dir, instead of
    # letting ultralytics fail confusingly deep inside model.train().
    data_yaml = tmp_path / "data_physical.yaml"
    data_yaml.write_text("names:\n  0: old_design\n")
    monkeypatch.setattr(tpm, "DATA_YAML", data_yaml)

    train_labels = tmp_path / "labels" / "train"
    train_labels.mkdir(parents=True)  # exists, but empty -- no .txt files
    val_labels = tmp_path / "labels" / "val"
    val_labels.mkdir(parents=True)
    monkeypatch.setattr(tpm, "TRAIN_LABELS_DIR", train_labels)
    monkeypatch.setattr(tpm, "VAL_LABELS_DIR", val_labels)

    try:
        tpm.main()
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert "prepare_yolo_dataset_physical.py" in str(e)
