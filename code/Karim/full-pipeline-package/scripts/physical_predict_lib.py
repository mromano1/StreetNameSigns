"""Pure prediction-response formatting logic for the physical-condition
inference server (see serve_physical_model.py). Kept separate from the
FastAPI wiring so it's testable without loading a real YOLO model -- same
split as physical_report_lib.py vs report_physical.py. See
docs/superpowers/specs/2026-07-31-capture-extension-model-feedback-design.md.
"""


def predictions_to_response(predictions, threshold):
    """predictions: list of (class_name, confidence) tuples, the same shape
    report_physical.predict_image returns. The same class_name can appear
    more than once (e.g. two detection boxes both landing on "faded" at
    different confidences), so this keeps only the highest confidence per
    class_name before filtering/sorting -- otherwise a downstream last-write-
    wins consumer (see extension/damage-prediction.js) could end up showing
    a duplicate's lower confidence instead of its highest. Returns a
    JSON-serializable dict {"classes": [{"class_name": ..., "confidence":
    ...}, ...]}, one entry per distinct class_name, filtered to confidence
    >= threshold and sorted highest-confidence first."""
    best_by_class = {}
    for name, conf in predictions:
        if name not in best_by_class or conf > best_by_class[name]:
            best_by_class[name] = conf
    filtered = [(name, conf) for name, conf in best_by_class.items() if conf >= threshold]
    filtered.sort(key=lambda pair: pair[1], reverse=True)
    return {
        "classes": [
            {"class_name": name, "confidence": round(conf, 4)}
            for name, conf in filtered
        ]
    }
