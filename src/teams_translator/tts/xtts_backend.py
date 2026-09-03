"""Coqui XTTS-v2 Voice Cloning TTS Adapter."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple
import numpy as np

from teams_translator.core.errors import ModelNotFoundError, WarmupError
from teams_translator.tts.base import TTSAdapter, VoiceProfile
from teams_translator.tts.conditioning import VoiceProfileManager

logger = logging.getLogger(__name__)

_tts_import_error: Optional[Exception] = None
try:
    import torch
    import transformers.utils.import_utils
    import transformers.pytorch_utils

    # Compatibility shim for PyTorch 2.10+ and Transformers 5.x with Coqui TTS
    transformers.utils.import_utils.is_torchcodec_available = lambda: True
    if not hasattr(transformers.pytorch_utils, "isin_mps_friendly"):
        transformers.pytorch_utils.isin_mps_friendly = torch.isin

    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts
    import torchaudio
    import soundfile as sf

    def _soundfile_load(filepath, *args, **kwargs):
        data, sr = sf.read(filepath, dtype="float32")
        t = torch.from_numpy(data)
        if t.ndim == 1:
            t = t.unsqueeze(0)
        else:
            t = t.T
        return t, sr

    torchaudio.load = _soundfile_load
except Exception as _tts_err:
    _tts_import_error = _tts_err
    if "torch" not in globals():
        torch = None  # type: ignore
    XttsConfig = None  # type: ignore
    Xtts = None  # type: ignore


class XTTSv2Adapter(TTSAdapter):
    """XTTS-v2 Voice Cloning Adapter with cross-language synthesis and conditioning caching."""

    def __init__(self, temperature: float = 0.75, speed: float = 1.0):
        self.model: Optional[Any] = None
        self.config: Optional[Any] = None
        self.model_path: str = ""
        self.device: str = "cuda"
        self.sample_rate: int = 24000
        self.temperature = float(temperature)
        self.speed = float(speed)
        if self.temperature <= 0:
            raise ValueError("XTTS temperature must be greater than zero.")
        if self.speed <= 0:
            raise ValueError("XTTS speed must be greater than zero.")
        self._latents_cache: Dict[str, Tuple[Any, Any]] = {}
        self._is_warm = False

    def initialize(self, model_path: str, device: str = "cuda", sample_rate: int = 24000):
        self.model_path = model_path
        self.device = device
        self.sample_rate = sample_rate

        p = Path(model_path)
        if not p.exists():
            raise ModelNotFoundError(
                f"XTTS-v2 model not found at '{model_path}'. "
                "Download model weights manually into models/tts/xtts-v2."
            )

        if Xtts is None or torch is None:
            detail = (
                f"{type(_tts_import_error).__name__}: {_tts_import_error}"
                if _tts_import_error is not None else "unknown import failure"
            )
            raise RuntimeError(
                "XTTS runtime unavailable. Required package: coqui-tts==0.27.5. "
                f"Import failure: {detail}"
            ) from _tts_import_error

        logger.info(f"Loading XTTS-v2 model from '{model_path}' on {device}...")
        self.config = XttsConfig()
        self.config.load_json(str((p / "config.json").resolve()))
        self.model = Xtts.init_from_config(self.config)
        self.model.load_checkpoint(
            self.config,
            checkpoint_dir=str(p.resolve()),
            eval=True,
            use_deepspeed=False,
        )
        if device == "cuda" and torch.cuda.is_available():
            self.model.cuda()
        logger.info("XTTS-v2 model loaded successfully.")

    def warmup(self):
        if self.model is None:
            raise WarmupError("XTTS model not initialized before warmup.")
        logger.info("Warming up XTTS-v2 model...")
        try:
            # Create dummy latents with correct dimensions
            gpt_cond_latent = torch.zeros((1, 30, 1024), device=self.device)
            speaker_embedding = torch.zeros((1, 512, 1), device=self.device)
            
            # Dummy synthesis
            _ = self.model.inference(
                text="Test warmup.",
                language="en",
                gpt_cond_latent=gpt_cond_latent,
                speaker_embedding=speaker_embedding,
                temperature=self.temperature,
                speed=self.speed,
                enable_text_splitting=False,
            )
            self._is_warm = True
            logger.info("XTTS-v2 warmup completed.")
        except Exception as e:
            raise WarmupError(f"XTTS warmup failed: {e}") from e

    def prepare_voice_profile(self, profile: VoiceProfile):
        """Compute and cache speaker latents for voice profile."""
        if self.model is None:
            raise RuntimeError("Model must be initialized before preparing voice profiles.")

        ref_path = Path(profile.reference_audio_path)
        if not ref_path.exists():
            raise RuntimeError(
                f"Voice reference audio '{ref_path}' not found for profile '{profile.display_name}'."
            )

        audio_hash = VoiceProfileManager.compute_audio_hash(str(ref_path))
        cache_key = f"{profile.id}_{audio_hash}"

        if cache_key in self._latents_cache:
            return

        # Check disk cache
        cache_dir = Path(profile.conditioning_cache_path or "voices/cache")
        cache_file = cache_dir / f"latents_{cache_key}.pt"

        if cache_file.exists():
            try:
                latents = torch.load(str(cache_file), map_location=self.device)
                self._latents_cache[cache_key] = latents
                logger.info(f"Loaded voice conditioning cache for profile '{profile.display_name}' from disk.")
                return
            except Exception as e:
                logger.warning(f"Could not load cache file: {e}")

        logger.info(f"Computing speaker conditioning latents for profile '{profile.display_name}' from {ref_path}...")
        gpt_cond_latent, speaker_embedding = self.model.get_conditioning_latents(
            audio_path=[str(ref_path.resolve())],
            gpt_cond_len=30,
            max_ref_length=60,
            sound_norm_refs=False,
        )

        latents = (gpt_cond_latent, speaker_embedding)
        self._latents_cache[cache_key] = latents

        # Save to disk
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            torch.save(latents, str(cache_file))
            logger.info(f"Saved voice conditioning cache to '{cache_file}'.")
        except Exception as e:
            logger.warning(f"Could not save latents cache to disk: {e}")

    def synthesize_committed(
        self,
        text: str,
        profile: VoiceProfile,
        target_language: str = "en",
    ) -> Iterator[np.ndarray]:
        if self.model is None or not text.strip():
            return

        ref_path = Path(profile.reference_audio_path)
        audio_hash = VoiceProfileManager.compute_audio_hash(str(ref_path))
        cache_key = f"{profile.id}_{audio_hash}"

        if cache_key not in self._latents_cache:
            self.prepare_voice_profile(profile)

        if cache_key in self._latents_cache:
            gpt_cond_latent, speaker_embedding = self._latents_cache[cache_key]
        else:
            raise RuntimeError(
                f"Voice conditioning is unavailable for profile '{profile.display_name}'."
            )

        try:
            out = self.model.inference(
                text=text,
                language=target_language,
                gpt_cond_latent=gpt_cond_latent,
                speaker_embedding=speaker_embedding,
                temperature=self.temperature,
                speed=self.speed,
                enable_text_splitting=False,
            )
            pcm_data = np.asarray(out["wav"], dtype=np.float32)
            yield pcm_data
        except Exception as e:
            logger.error(f"XTTS synthesis error: {e}")

    def shutdown(self):
        self.model = None
        self._latents_cache.clear()
        self._is_warm = False
