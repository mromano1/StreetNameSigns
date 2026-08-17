import physical_predict_lib as ppl


def test_empty_predictions_returns_empty_classes():
    assert ppl.predictions_to_response([], threshold=0.25) == {"classes": []}


def test_filters_below_threshold():
    predictions = [("faded", 0.10), ("bent_damaged", 0.82)]
    assert ppl.predictions_to_response(predictions, threshold=0.25) == {
        "classes": [{"class_name": "bent_damaged", "confidence": 0.82}]
    }


def test_sorts_highest_confidence_first():
    predictions = [("faded", 0.30), ("bent_damaged", 0.82), ("hanging", 0.55)]
    result = ppl.predictions_to_response(predictions, threshold=0.25)
    assert [c["class_name"] for c in result["classes"]] == ["bent_damaged", "hanging", "faded"]


def test_rounds_confidence_to_4_decimal_places():
    predictions = [("faded", 0.123456789)]
    result = ppl.predictions_to_response(predictions, threshold=0.1)
    assert result["classes"][0]["confidence"] == 0.1235


def test_keeps_multiple_classes_above_threshold():
    predictions = [("faded", 0.5), ("vandalized", 0.9)]
    result = ppl.predictions_to_response(predictions, threshold=0.25)
    assert len(result["classes"]) == 2


def test_duplicate_class_names_collapse_to_highest_confidence():
    predictions = [("faded", 0.91), ("faded", 0.31)]
    result = ppl.predictions_to_response(predictions, threshold=0.25)
    assert result["classes"] == [{"class_name": "faded", "confidence": 0.91}]
