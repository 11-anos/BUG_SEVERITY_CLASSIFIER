#!/usr/bin/env python3
"""One-shot batch entrypoint used by the VS Code extension.

Reads JSON from stdin, either a bare array or {"descriptions": [...]}:

    ["Application crashes when opening a file.", "Minor typo in heading."]

Writes a JSON array of predictor results to stdout:

    [{"predicted_severity": "major", "highest_probability": 0.81, ...}, ...]

Run from anywhere; the script directory is added to sys.path automatically.
"""

from __future__ import annotations

import json
import sys

from src.predictor import predict_severity


def main() -> None:
    payload = json.load(sys.stdin)
    if isinstance(payload, dict):
        descriptions = payload.get("descriptions", [])
    else:
        descriptions = payload

    if not isinstance(descriptions, list):
        raise ValueError("expected a JSON array or {'descriptions': [...]}")

    results = [predict_severity(str(description)) for description in descriptions]
    json.dump(results, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
