"""Manual offline model downloader for pinned Hugging Face models."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

MODELS = {
    "whisper": {
        "repo_id": "openai/whisper-large-v3-turbo",
        "destination": "models/asr/whisper-large-v3-turbo",
        "license": "MIT",
        "purpose": "ASR bring-up (TR & EN)",
    },
    "mt-tr-en": {
        "repo_id": "Helsinki-NLP/opus-mt-tc-big-tr-en",
        "destination": "models/mt/opus-mt-tc-big-tr-en",
        "license": "CC-BY-4.0",
        "purpose": "Outgoing TR->EN Translation",
    },
    "mt-en-tr": {
        "repo_id": "Helsinki-NLP/opus-mt-tc-big-en-tr",
        "destination": "models/mt/opus-mt-tc-big-en-tr",
        "license": "CC-BY-4.0",
        "purpose": "Incoming EN->TR Translation",
    },
    "mt-tr-fr": {
        "repo_id": "Helsinki-NLP/opus-mt-tr-fr",
        "destination": "models/mt/opus-mt-tr-fr",
        "license": "CC-BY-4.0",
        "purpose": "Outgoing TR->FR Translation",
    },
    "xtts": {
        "repo_id": "coqui/XTTS-v2",
        "destination": "models/tts/xtts-v2",
        "license": "CPML (Personal / Non-commercial)",
        "purpose": "Cross-language Voice Cloning TTS",
    },
}


def download_model(key: str, info: dict):
    print(f"\n--- Downloading: {key} ---")
    print(f"Repo ID:     {info['repo_id']}")
    print(f"Destination: {info['destination']}")
    print(f"License:     {info['license']}")
    print(f"Purpose:     {info['purpose']}")

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("Error: huggingface_hub is required. Install via: pip install huggingface_hub")
        sys.exit(1)

    dest_path = Path(info["destination"])
    dest_path.mkdir(parents=True, exist_ok=True)

    print("Starting download...")
    snapshot_download(
        repo_id=info["repo_id"],
        local_dir=str(dest_path.resolve()),
        local_dir_use_symlinks=False,
    )
    print(f"Successfully downloaded to: {dest_path.resolve()}")


def main():
    parser = argparse.ArgumentParser(description="Download pinned models for Teams Translator")
    parser.add_argument(
        "model",
        choices=list(MODELS.keys()) + ["all"],
        help="Model to download (or 'all')",
    )
    args = parser.parse_args()

    if args.model == "all":
        for k, v in MODELS.items():
            download_model(k, v)
    else:
        download_model(args.model, MODELS[args.model])


if __name__ == "__main__":
    main()

