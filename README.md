# BugSense AI

BugSense AI loads a saved DistilBERT severity classifier from a local ZIP archive and predicts the severity of a bug description.

## Project structure

- `models/BugSense_AI_Model/` - extracted saved model files
- `src/model_loader.py` - archive extraction and model loading
- `src/predictor.py` - single-description inference and CLI
- `src/evaluation.py` - optional CSV evaluation workflow
- `main.py` - entrypoint for smoke tests, single-input prediction, CLI, and evaluation
- `tests/test_predictor.py` - smoke/inference validation tests
- `outputs/` - evaluation CSV/JSON outputs

## Model archive

The project expects the saved model ZIP at this exact path:

`/home/sanju/Downloads/BugSense_AI_Model.zip`

The code checks the archive exists and extracts it safely to `./models/BugSense_AI_Model/` using Python's `zipfile` module.

## Installation

This project is designed for the currently selected VS Code Python environment. If the dependency stack is not already present, install it with:

```bash
python3 -m pip install -r requirements.txt
```

## Run the classifier

From the project root:

```bash
python3 main.py
```

This starts the interactive CLI. You can also run a single prediction:

```bash
python3 main.py --description "Application crashes when opening a file that does not exist."
```

Run the smoke tests:

```bash
python3 main.py --smoke-test
```

## Run the tests

```bash
python3 -m pytest tests/test_predictor.py -q
```

## Optional evaluation workflow

Use a CSV file with these columns:

- `Short Description`
- `Severity Label`

Example:

```bash
python3 main.py --evaluate path/to/labels.csv
```

This saves evaluation metrics to `outputs/evaluation_metrics.csv`, `outputs/evaluation_metrics.json`, and `outputs/confusion_matrix.csv`.

The saved label mapping is the source of truth for class names and ordering:

- 0 = blocker
- 1 = critical
- 2 = major
- 3 = minor
- 4 = normal
- 5 = trivial

The evaluation workflow is intentionally separate from inference. Smoke tests are not a substitute for a genuine evaluation dataset.

## Notes

- The model is loaded locally from disk and is not retrained here.
- If the ZIP is missing, execution stops with a clear error.
- No model weights or API keys are committed to version control.
