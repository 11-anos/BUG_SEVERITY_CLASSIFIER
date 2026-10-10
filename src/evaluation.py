from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support, precision_score, recall_score

from .model_loader import MODEL_ROOT, get_model_bundle
from .predictor import predict_severity


def evaluate_model_csv(csv_path: str | Path, output_dir: str | Path = MODEL_ROOT.parent / "outputs") -> Dict[str, object]:
    """Evaluate a CSV containing bug descriptions and severity labels."""
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Evaluation CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    required_columns = {"Short Description", "Severity Label"}
    missing = sorted(required_columns - set(df.columns))
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}")

    bundle = get_model_bundle()
    label_mapping = bundle.label_mapping
    label_order = [label_mapping[index] for index in sorted(label_mapping)]
    label_to_index = {label: index for index, label in label_mapping.items()}

    true_labels: List[int] = []
    pred_labels: List[int] = []

    for _, row in df.iterrows():
        description = str(row["Short Description"]).strip()
        actual_label = str(row["Severity Label"]).strip()
        if not description:
            raise ValueError("Encountered an empty Short Description in the evaluation CSV.")
        if actual_label not in label_to_index:
            supported = ", ".join(label_order)
            raise ValueError(f"Unsupported severity label {actual_label!r}. Supported labels are: {supported}.")

        prediction = predict_severity(description)
        true_labels.append(label_to_index[actual_label])
        pred_labels.append(label_to_index[prediction["predicted_severity"]])

    class_ids = [label_to_index[label] for label in label_order]
    accuracy = accuracy_score(true_labels, pred_labels)
    precision_macro = precision_score(true_labels, pred_labels, labels=class_ids, average="macro", zero_division=0)
    recall_macro = recall_score(true_labels, pred_labels, labels=class_ids, average="macro", zero_division=0)
    f1_macro = f1_score(true_labels, pred_labels, labels=class_ids, average="macro", zero_division=0)
    f1_weighted = f1_score(true_labels, pred_labels, labels=class_ids, average="weighted", zero_division=0)

    per_class_precision, per_class_recall, per_class_f1, support = precision_recall_fscore_support(
        true_labels,
        pred_labels,
        labels=class_ids,
        zero_division=0,
    )

    per_class_df = pd.DataFrame(
        {
            "label": label_order,
            "precision": per_class_precision,
            "recall": per_class_recall,
            "f1": per_class_f1,
            "support": support,
        }
    )

    confusion = confusion_matrix(true_labels, pred_labels, labels=class_ids)
    confusion_df = pd.DataFrame(confusion, index=label_order, columns=label_order)

    summary = {
        "accuracy": float(accuracy),
        "macro_precision": float(precision_macro),
        "macro_recall": float(recall_macro),
        "macro_f1": float(f1_macro),
        "weighted_f1": float(f1_weighted),
        "per_class": per_class_df.to_dict(orient="records"),
        "confusion_matrix": confusion_df.to_dict(orient="index"),
    }

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_csv_path = output_dir / "evaluation_metrics.csv"
    per_class_df.to_csv(summary_csv_path, index=False)

    json_path = output_dir / "evaluation_metrics.json"
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)

    confusion_csv_path = output_dir / "confusion_matrix.csv"
    confusion_df.to_csv(confusion_csv_path)

    return summary
