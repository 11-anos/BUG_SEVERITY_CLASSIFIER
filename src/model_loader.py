from __future__ import annotations

import json
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Dict

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = PROJECT_ROOT / "models"
MODEL_DIR = MODEL_ROOT / "BugSense_AI_Model"
MODEL_ZIP_PATH = Path("/home/sanju/Downloads/BugSense_AI_Model.zip")


@dataclass
class ModelBundle:
    model_dir: Path
    tokenizer: AutoTokenizer
    model: AutoModelForSequenceClassification
    device: torch.device
    label_mapping: Dict[int, str]


def print_environment_summary() -> None:
    """Print the Python and ML runtime environment details."""
    import transformers

    print("Python version:", sys.version.replace("\n", " "))
    print("PyTorch version:", torch.__version__)
    print("Transformers version:", transformers.__version__)
    print("CUDA available:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("GPU name:", torch.cuda.get_device_name(0))
    else:
        print("GPU name:", "None")


def _is_safe_member(member_name: str) -> bool:
    if not member_name or member_name in {".", "/"}:
        return False
    pure = PurePosixPath(member_name)
    return not pure.is_absolute() and ".." not in pure.parts and not member_name.startswith("/")


def extract_model_zip(zip_path: Path = MODEL_ZIP_PATH, target_dir: Path = MODEL_DIR) -> Path:
    """Safely extract the model archive to the project-local model directory."""
    if not zip_path.is_file():
        raise FileNotFoundError(f"Model ZIP not found at {zip_path}. Please verify the file exists.")

    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            member_name = info.filename.strip("/")
            if not member_name or member_name in {".", "/"}:
                continue
            if not _is_safe_member(member_name):
                raise ValueError(f"Unsafe archive member detected: {info.filename!r}")

            normalized_name = member_name
            for prefix in ("BugSense_AI_Model/", "models/BugSense_AI_Model/"):
                if normalized_name.startswith(prefix):
                    normalized_name = normalized_name[len(prefix) :]
                    break

            if not normalized_name:
                continue

            output_path = target_dir / normalized_name
            if ".." in PurePosixPath(normalized_name).parts:
                raise ValueError(f"Path traversal attempt in archive: {info.filename!r}")

            if info.is_dir():
                output_path.mkdir(parents=True, exist_ok=True)
                continue

            output_path.parent.mkdir(parents=True, exist_ok=True)
            if output_path.exists() and output_path.is_dir():
                raise ValueError(f"Refusing to overwrite directory with file: {output_path}")

            with archive.open(info, "r") as src, open(output_path, "wb") as dst:
                dst.write(src.read())

    return target_dir


def find_model_directory(search_root: Path = MODEL_ROOT) -> Path:
    """Locate the extracted model directory containing config.json and the weights."""
    if not search_root.exists():
        raise FileNotFoundError(f"Model extraction root does not exist: {search_root}")

    candidates = []
    if (search_root / "config.json").exists():
        candidates.append(search_root)

    for child in sorted(search_root.iterdir()):
        if child.is_dir() and (child / "config.json").exists():
            candidates.append(child)

    for candidate in candidates:
        has_weights = (candidate / "model.safetensors").exists() or (candidate / "pytorch_model.bin").exists()
        if has_weights:
            return candidate

    if candidates:
        return candidates[0]

    raise FileNotFoundError(f"No model directory with config.json and weights was found under {search_root}.")


def prepare_model_directory() -> Path:
    """Ensure the model archive is extracted and resolve the actual saved model directory."""
    if MODEL_DIR.exists() and (MODEL_DIR / "config.json").exists():
        return find_model_directory(MODEL_DIR)

    if MODEL_ZIP_PATH.is_file():
        extract_model_zip(MODEL_ZIP_PATH, MODEL_DIR)
        return find_model_directory(MODEL_DIR)

    raise FileNotFoundError(
        f"Model archive is missing: {MODEL_ZIP_PATH}. The project expects a saved model ZIP at that exact location."
    )


def load_label_mapping(model_dir: Path) -> Dict[int, str]:
    """Load the saved mapping from label_mapping.json, otherwise fall back to config id2label."""
    mapping_path = model_dir / "label_mapping.json"
    if mapping_path.exists():
        with open(mapping_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        raw_mapping = payload.get("id2label")
        if not isinstance(raw_mapping, dict):
            raise ValueError(f"label_mapping.json exists but id2label is invalid in {mapping_path}.")
    else:
        config_path = model_dir / "config.json"
        if not config_path.exists():
            raise FileNotFoundError(f"Expected config.json in {model_dir}.")
        with open(config_path, "r", encoding="utf-8") as handle:
            config = json.load(handle)
        raw_mapping = config.get("id2label")
        if not isinstance(raw_mapping, dict):
            raise ValueError(f"No valid id2label mapping found in {config_path}.")

    mapping: Dict[int, str] = {}
    for key, value in raw_mapping.items():
        try:
            index = int(key)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid label index in mapping: {key!r}") from None
        mapping[index] = str(value)

    if not mapping:
        raise ValueError(f"Label mapping is empty for {model_dir}.")

    ordered_mapping = {index: mapping[index] for index in sorted(mapping)}
    return ordered_mapping


@torch.inference_mode()
def _load_model_bundle() -> ModelBundle:
    model_dir = prepare_model_directory()
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(str(model_dir), local_files_only=True)

    saved_mapping = load_label_mapping(model_dir)
    model_labels = getattr(model.config, "id2label", {})
    mapped_labels = {int(key): str(value) for key, value in model_labels.items()}

    if not mapped_labels:
        raise ValueError(f"Model config in {model_dir} does not define a valid id2label mapping.")

    if len(saved_mapping) != model.config.num_labels:
        raise ValueError(
            f"Saved label mapping length {len(saved_mapping)} does not match model output dimension {model.config.num_labels}."
        )

    expected = sorted(saved_mapping)
    if list(saved_mapping) != expected:
        raise ValueError(f"Saved label mapping indices are not contiguous integers: {saved_mapping}")

    for index in saved_mapping:
        if index not in mapped_labels:
            raise ValueError(
                f"Model id2label is missing class index {index}. Saved mapping: {saved_mapping}; model mapping: {mapped_labels}."
            )

    if saved_mapping != mapped_labels:
        pass

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.eval()
    return ModelBundle(model_dir=model_dir, tokenizer=tokenizer, model=model, device=device, label_mapping=saved_mapping)


@torch.inference_mode()
def get_model_bundle() -> ModelBundle:
    """Return the loaded tokenizer, model, device, and label mapping."""
    return _load_model_bundle()
