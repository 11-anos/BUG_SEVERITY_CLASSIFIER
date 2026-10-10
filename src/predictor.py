from __future__ import annotations

import math
from typing import Any, Dict

import numpy as np
import torch

from .model_loader import ModelBundle, get_model_bundle


def _validate_probability_distribution(probabilities: list[float], label_mapping: dict[int, str]) -> None:
    if not np.all(np.isfinite(probabilities)):
        raise ValueError("Predicted probabilities contain non-finite values.")

    total = float(np.sum(probabilities))
    if not math.isclose(total, 1.0, rel_tol=1e-5, abs_tol=1e-5):
        raise ValueError(f"Softmax probabilities do not sum to 1.0; sum={total:.12f}")

    if len(probabilities) != len(label_mapping):
        raise ValueError(
            f"Number of probabilities ({len(probabilities)}) does not match label count ({len(label_mapping)})."
        )


def predict_severity(description: str) -> Dict[str, Any]:
    """Infer the severity classification for a single bug description."""
    if not isinstance(description, str):
        raise ValueError("Bug description must be a string value.")

    cleaned = description.strip()
    if not cleaned:
        raise ValueError("Bug description must be a non-empty string.")

    bundle: ModelBundle = get_model_bundle()
    inputs = bundle.tokenizer(
        cleaned,
        truncation=True,
        max_length=128,
        padding=False,
        return_tensors="pt",
    )
    inputs = {key: value.to(bundle.device) for key, value in inputs.items()}

    with torch.inference_mode():
        logits = bundle.model(**inputs).logits

    probabilities = torch.softmax(logits, dim=-1).squeeze(0).detach().cpu().tolist()
    _validate_probability_distribution(probabilities, bundle.label_mapping)

    probability_by_class = {
        bundle.label_mapping[index]: float(probabilities[index])
        for index in sorted(bundle.label_mapping)
    }

    predicted_index = int(np.argmax(probabilities))
    predicted_label = bundle.label_mapping[predicted_index]
    highest_probability = float(probabilities[predicted_index])

    if predicted_label not in probability_by_class:
        raise ValueError(f"Predicted label {predicted_label!r} not found in probability mapping.")

    if not math.isclose(probability_by_class[predicted_label], highest_probability, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError("Predicted class does not match the highest-probability class.")

    result: Dict[str, Any] = {
        "description": cleaned,
        "predicted_severity": predicted_label,
        "highest_probability": highest_probability,
        "probabilities": probability_by_class,
    }
    return result


def run_smoke_tests() -> None:
    """Run the smoke-test examples and print the predictions."""
    examples = [
        "Application crashes when opening a file that does not exist.",
        "Critical security vulnerability allows unauthorized users to access administrator accounts.",
        "Application crashes during startup for every user after the latest update.",
        "Minor typo in the settings page heading.",
        "Application displays an incorrect warning message but all functions work correctly.",
        "Application works as expected with no errors or unexpected behavior.",
    ]

    for description in examples:
        result = predict_severity(description)
        print(f"Input description: {description}")
        print(f"Predicted severity: {result['predicted_severity']}")
        print(f"Highest predicted probability: {result['highest_probability']:.6f}")
        print("Complete probability distribution:")
        for label, probability in result["probabilities"].items():
            print(f"  {label}: {probability:.6f}")
        print("-" * 80)


def run_interactive_cli() -> None:
    """Interactive CLI for repeated prediction requests."""
    print("BugSense AI severity classifier")
    print("Enter 'exit' to quit.")

    while True:
        raw_input = input("\nEnter a bug description:\n").strip()
        if raw_input.lower() == "exit":
            print("Exiting BugSense AI.")
            break

        try:
            result = predict_severity(raw_input)
        except ValueError as exc:
            print(f"Error: {exc}")
            continue

        print(f"Predicted severity: {result['predicted_severity']}")
        print(f"Highest predicted probability: {result['highest_probability']:.6f}")
        print("Complete probability distribution sorted by probability:")
        for label, probability in sorted(result["probabilities"].items(), key=lambda item: item[1], reverse=True):
            print(f"  {label}: {probability:.6f}")
