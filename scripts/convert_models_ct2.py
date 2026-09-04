"""Convert downloaded Hugging Face MT models to CTranslate2 INT8 format."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("convert_models_ct2")

POSSIBLE_TOKENIZER_FILES = [
    "source.spm",
    "target.spm",
    "vocab.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "sentencepiece.bpe.model",
    "tokenizer.json",
]


def convert_model(
    model_dir: str | Path,
    output_dir: Optional[str | Path] = None,
    quantization: str = "int8",
) -> Path:
    from ctranslate2.converters import TransformersConverter

    source_path = Path(model_dir).resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Source model path '{source_path}' does not exist.")

    if output_dir is None:
        target_path = Path(f"{source_path}-ct2").resolve()
    else:
        target_path = Path(output_dir).resolve()

    target_path.mkdir(parents=True, exist_ok=True)

    # Detect present tokenizer files to copy
    copy_files = [f for f in POSSIBLE_TOKENIZER_FILES if (source_path / f).exists()]
    logger.info("Converting '%s' to CTranslate2 (%s)...", source_path.name, quantization)
    logger.info("Copying tokenizer files: %s", copy_files)

    converter = TransformersConverter(
        model_name_or_path=str(source_path),
        copy_files=copy_files,
    )
    converter.convert(
        output_dir=str(target_path),
        quantization=quantization,
        force=True,
    )
    logger.info("Successfully converted to '%s'.", target_path)
    return target_path


def main():
    parser = argparse.ArgumentParser(description="Convert HuggingFace MT models to CTranslate2 INT8")
    parser.add_argument(
        "--model-dir",
        type=str,
        default=None,
        help="Specific model directory to convert (e.g. models/mt/opus-mt-tc-big-tr-en)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory (defaults to <model-dir>-ct2)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Convert all available models in models/mt/",
    )
    parser.add_argument(
        "--quantization",
        type=str,
        default="int8",
        choices=["int8", "float16", "int8_float16", "int8_float32", "float32"],
        help="Quantization type (default: int8)",
    )
    args = parser.parse_args()

    mt_root = Path("models/mt")
    if args.all or args.model_dir is None:
        if not mt_root.exists():
            logger.error("No models/mt directory found. Run download_models.py first.")
            return

        converted = 0
        for candidate in sorted(mt_root.iterdir()):
            if candidate.is_dir() and not candidate.name.endswith("-ct2"):
                # Only convert if it has weights and not already a CT2 folder
                has_weights = (
                    (candidate / "pytorch_model.bin").exists()
                    or (candidate / "model.safetensors").exists()
                    or (candidate / "tf_model.h5").exists()
                )
                if has_weights:
                    convert_model(candidate, quantization=args.quantization)
                    converted += 1
        if converted == 0:
            logger.info("No unquantized HuggingFace models found to convert in models/mt/.")
    else:
        convert_model(args.model_dir, output_dir=args.output_dir, quantization=args.quantization)


if __name__ == "__main__":
    main()

