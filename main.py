from __future__ import annotations

import argparse

from src.evaluation import evaluate_model_csv
from src.model_loader import print_environment_summary
from src.predictor import predict_severity, run_interactive_cli, run_smoke_tests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BugSense AI severity classifier")
    parser.add_argument("--smoke-test", action="store_true", help="Run the smoke-test descriptions.")
    parser.add_argument("--description", type=str, help="Predict the severity for a single description.")
    parser.add_argument("--evaluate", type=str, help="CSV file with Short Description and Severity Label columns.")
    parser.add_argument("--show-env", action="store_true", help="Print Python, PyTorch, and Transformers environment details.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.show_env:
        print_environment_summary()

    if args.description is not None:
        result = predict_severity(args.description)
        print(f"Predicted severity: {result['predicted_severity']}")
        print(f"Highest predicted probability: {result['highest_probability']:.6f}")
        print("Probability distribution:")
        for label, probability in result["probabilities"].items():
            print(f"  {label}: {probability:.6f}")
        return

    if args.evaluate:
        metrics = evaluate_model_csv(args.evaluate)
        print("Evaluation summary:")
        for key, value in metrics.items():
            if key == "per_class":
                continue
            if key == "confusion_matrix":
                continue
            print(f"  {key}: {value}")
        return

    if args.smoke_test:
        run_smoke_tests()
        return

    run_interactive_cli()


if __name__ == "__main__":
    main()
