# Rule Engine Linter VSCode Extension

Runs the C++ rule engine (`engine/rules.py`) and surfaces findings as diagnostics in the Problems panel and inline squiggles. Findings are optionally classified with the BugSense severity model through `predict_batch.py`.

## Build

```bash
npm install
npm run compile
```

Then press F5 in VS Code, or package with `vsce package`.

## Configuration

- `ruleEngine.pythonPath`: Python interpreter for the rule engine (e.g. `.venv/bin/python3`).
- `ruleEngine.scriptPath`: Path to `rules.py` (default: `engine/rules.py`).
- `ruleEngine.scanScriptPath`: Path to `scan.py` (default: `engine/scan.py`).
- `ruleEngine.useModel`: Enable model severity classification (default: `true`).
- `ruleEngine.modelPythonPath`: Python interpreter for the model. Empty uses `ruleEngine.pythonPath`.
- `ruleEngine.modelProjectPath`: Predictor project path. Empty auto-detects `Model/BUG_SEVERITY_CLASSIFIER` or the parent repo root.

## Dependencies

Install the rule engine dependencies:

```bash
python3.12 -m pip install --user -r engine/requirements.txt
```

Install the model dependencies in the interpreter used by `ruleEngine.modelPythonPath`:

```bash
python3 -m pip install -r ../requirements.txt
```

The predictor expects `predict_batch.py` plus a populated `models/BugSense_AI_Model/` directory (`config.json`, tokenizer files, and `model.safetensors` or `pytorch_model.bin`).
