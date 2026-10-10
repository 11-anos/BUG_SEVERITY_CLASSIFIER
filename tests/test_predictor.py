from __future__ import annotations

import math

import numpy as np

from src.predictor import predict_severity

EXAMPLES = [
    "Application crashes when opening a file that does not exist.",
    "Critical security vulnerability allows unauthorized users to access administrator accounts.",
    "Application crashes during startup for every user after the latest update.",
    "Minor typo in the settings page heading.",
    "Application displays an incorrect warning message but all functions work correctly.",
    "Application works as expected with no errors or unexpected behavior.",
]


def test_predict_severity_validates_output() -> None:
    for description in EXAMPLES:
        result = predict_severity(description)
        assert result["description"] == description
        assert result["predicted_severity"] in result["probabilities"]
        probabilities = list(result["probabilities"].values())
        assert np.all(np.isfinite(probabilities))
        assert math.isclose(float(sum(probabilities)), 1.0, rel_tol=1e-5, abs_tol=1e-5)
        highest_label = max(result["probabilities"], key=result["probabilities"].get)
        assert result["predicted_severity"] == highest_label
        assert result["highest_probability"] == result["probabilities"][highest_label]


def test_predict_severity_rejects_empty_input() -> None:
    try:
        predict_severity("   ")
        raise AssertionError("Expected ValueError for empty bug description.")
    except ValueError:
        pass
