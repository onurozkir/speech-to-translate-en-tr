"""Translation Backend supporting CTranslate2 and HuggingFace MarianMT."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from teams_translator.core.errors import ModelNotFoundError, WarmupError
from teams_translator.translation.base import MTAdapter

logger = logging.getLogger(__name__)

try:
    import torch
except ImportError:
    torch = None  # type: ignore

try:
    import ctranslate2
except ImportError:
    ctranslate2 = None  # type: ignore

try:
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
except ImportError:
    AutoModelForSeq2SeqLM = None  # type: ignore
    AutoTokenizer = None  # type: ignore


class CTranslate2MTAdapter(MTAdapter):
    """MT Adapter supporting CTranslate2 INT8 or Hugging Face MarianMT."""

    def __init__(self):
        self.tr_en_translator: Optional[Any] = None
        self.en_tr_translator: Optional[Any] = None
        self.tr_fr_translator: Optional[Any] = None
        self.tr_en_tokenizer: Optional[Any] = None
        self.en_tr_tokenizer: Optional[Any] = None
        self.tr_fr_tokenizer: Optional[Any] = None
        self.backend_type: str = "transformers"  # "ctranslate2" or "transformers"
        self.device = "cpu"
        self.compute_type = "int8"
        self._is_warm = False

    def initialize(
        self,
        tr_en_model_path: str,
        en_tr_model_path: str,
        tr_fr_model_path: Optional[str] = "models/mt/opus-mt-tr-fr",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        self.device = device
        self.compute_type = compute_type

        # Offline path checks
        p_tr_en = Path(tr_en_model_path)
        p_en_tr = Path(en_tr_model_path)

        if not p_tr_en.exists():
            raise ModelNotFoundError(
                f"TR->EN MT model path '{tr_en_model_path}' not found. "
                "Models must be downloaded manually."
            )
        if not p_en_tr.exists():
            raise ModelNotFoundError(
                f"EN->TR MT model path '{en_tr_model_path}' not found. "
                "Models must be downloaded manually."
            )

        # Check if CTranslate2 format (requires shared/source_vocabulary.json + model.bin)
        has_ct2 = (
            (p_tr_en / "model.bin").exists()
            and ((p_tr_en / "shared_vocabulary.json").exists() or (p_tr_en / "source_vocabulary.json").exists())
        )

        if has_ct2 and ctranslate2 is not None and AutoTokenizer is not None:
            self.backend_type = "ctranslate2"
            logger.info(f"Loading CTranslate2 TR->EN model from '{tr_en_model_path}' ({device}, {compute_type})...")
            self.tr_en_translator = ctranslate2.Translator(
                str(p_tr_en.resolve()),
                device=device,
                compute_type=compute_type,
            )
            self.tr_en_tokenizer = AutoTokenizer.from_pretrained(str(p_tr_en.resolve()), local_files_only=True)

            logger.info(f"Loading CTranslate2 EN->TR model from '{en_tr_model_path}' ({device}, {compute_type})...")
            self.en_tr_translator = ctranslate2.Translator(
                str(p_en_tr.resolve()),
                device=device,
                compute_type=compute_type,
            )
            self.en_tr_tokenizer = AutoTokenizer.from_pretrained(str(p_en_tr.resolve()), local_files_only=True)
        else:
            self.backend_type = "transformers"
            if AutoModelForSeq2SeqLM is None or AutoTokenizer is None:
                raise RuntimeError("transformers is required for HuggingFace MT models.")

            logger.info(f"Loading HuggingFace MarianMT TR->EN from '{tr_en_model_path}'...")
            self.tr_en_tokenizer = AutoTokenizer.from_pretrained(str(p_tr_en.resolve()), local_files_only=True)
            self.tr_en_translator = AutoModelForSeq2SeqLM.from_pretrained(str(p_tr_en.resolve()), local_files_only=True)

            logger.info(f"Loading HuggingFace MarianMT EN->TR from '{en_tr_model_path}'...")
            self.en_tr_tokenizer = AutoTokenizer.from_pretrained(str(p_en_tr.resolve()), local_files_only=True)
            self.en_tr_translator = AutoModelForSeq2SeqLM.from_pretrained(str(p_en_tr.resolve()), local_files_only=True)

            if device == "cuda" and torch is not None and torch.cuda.is_available():
                self.tr_en_translator.to("cuda")
                self.en_tr_translator.to("cuda")

        # Optional TR->FR model loading
        if tr_fr_model_path:
            p_tr_fr = Path(tr_fr_model_path)
            if p_tr_fr.exists():
                logger.info(f"Loading TR->FR translation model from '{tr_fr_model_path}'...")
                has_ct2_fr = (p_tr_fr / "model.bin").exists() and (
                    (p_tr_fr / "shared_vocabulary.json").exists() or (p_tr_fr / "source_vocabulary.json").exists()
                )
                if has_ct2_fr and ctranslate2 is not None and AutoTokenizer is not None:
                    self.tr_fr_translator = ctranslate2.Translator(
                        str(p_tr_fr.resolve()),
                        device=device,
                        compute_type=compute_type,
                    )
                    self.tr_fr_tokenizer = AutoTokenizer.from_pretrained(str(p_tr_fr.resolve()), local_files_only=True)
                elif AutoModelForSeq2SeqLM is not None and AutoTokenizer is not None:
                    self.tr_fr_tokenizer = AutoTokenizer.from_pretrained(str(p_tr_fr.resolve()), local_files_only=True)
                    self.tr_fr_translator = AutoModelForSeq2SeqLM.from_pretrained(str(p_tr_fr.resolve()), local_files_only=True)
                    if device == "cuda" and torch is not None and torch.cuda.is_available():
                        self.tr_fr_translator.to("cuda")
                logger.info("TR->FR translation model loaded successfully.")
            else:
                logger.info(f"TR->FR model '{tr_fr_model_path}' not found. Run 'python scripts/download_models.py mt-tr-fr' to enable French translation.")

        logger.info(f"MT models loaded successfully (backend: {self.backend_type}).")

    def warmup(self):
        if self.tr_en_translator is None or self.en_tr_translator is None:
            raise WarmupError("MT models not initialized before warmup.")
        try:
            logger.info("Warming up MT models...")
            _ = self.translate("Merhaba dünya", "tr", "en")
            _ = self.translate("Hello world", "en", "tr")
            self._is_warm = True
            logger.info("MT models warmup completed.")
        except Exception as e:
            raise WarmupError(f"MT warmup failed: {e}") from e

    def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        is_partial: bool = False,
    ) -> str:
        text = text.strip()
        if not text:
            return ""

        source_lang = source_lang.lower()
        target_lang = target_lang.lower()

        try:
            if source_lang.startswith("tr") and target_lang.startswith("en"):
                translator = self.tr_en_translator
                tokenizer = self.tr_en_tokenizer
            elif source_lang.startswith("tr") and target_lang.startswith("fr"):
                translator = self.tr_fr_translator
                tokenizer = self.tr_fr_tokenizer
                if translator is None:
                    logger.warning("TR->FR model not loaded yet. Falling back to original text.")
                    return text
            elif source_lang.startswith("en") and target_lang.startswith("tr"):
                translator = self.en_tr_translator
                tokenizer = self.en_tr_tokenizer
            else:
                logger.warning(f"Unsupported language pair: {source_lang}->{target_lang}")
                return text

            if translator is None or tokenizer is None:
                return text

            if self.backend_type == "ctranslate2":
                tokens = tokenizer.convert_ids_to_tokens(tokenizer.encode(text))
                results = translator.translate_batch([tokens], beam_size=1 if is_partial else 2)
                out_tokens = results[0].hypotheses[0]
                out_text = tokenizer.decode(tokenizer.convert_tokens_to_ids(out_tokens))
                return out_text.strip()
            else:
                # HuggingFace MarianMT inference
                inputs = tokenizer(text, return_tensors="pt", padding=True)
                if self.device == "cuda" and torch is not None and torch.cuda.is_available():
                    inputs = {k: v.to("cuda") for k, v in inputs.items()}
                
                if torch is not None:
                    with torch.inference_mode():
                        translated_tokens = translator.generate(**inputs, max_length=128, num_beams=1 if is_partial else 2)
                else:
                    translated_tokens = translator.generate(**inputs, max_length=128, num_beams=1 if is_partial else 2)

                out_text = tokenizer.batch_decode(translated_tokens, skip_special_tokens=True)
                return out_text[0].strip() if out_text else text
        except Exception as e:
            logger.error(f"MT translation error ({source_lang}->{target_lang}): {e}")
            return text

    def shutdown(self):
        self.tr_en_translator = None
        self.en_tr_translator = None
        self.tr_fr_translator = None
        self.tr_en_tokenizer = None
        self.en_tr_tokenizer = None
        self.tr_fr_tokenizer = None
        self._is_warm = False
