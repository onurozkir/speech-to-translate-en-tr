"""Whisper ASR Backend supporting Faster-Whisper and HuggingFace Transformers."""

from __future__ import annotations

import copy
import logging
import os
import re
import threading
import time
import zlib
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional
import numpy as np

from teams_translator.asr.base import ASRAdapter, ASRSession
from teams_translator.core.errors import ModelNotFoundError, WarmupError
from teams_translator.core.types import Direction, UtteranceEvent, UtteranceState

logger = logging.getLogger(__name__)


class _WhisperInternalDeprecationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not record.getMessage().startswith(
            "Passing `generation_config` together with generation-related arguments="
        )


@contextmanager
def _quiet_transformers_whisper_internal_warning():
    """Hide one Transformers 5.x nested-call warning we cannot act on per request."""
    generation_logger = logging.getLogger("transformers.generation.utils")
    message_filter = _WhisperInternalDeprecationFilter()
    generation_logger.addFilter(message_filter)
    try:
        yield
    finally:
        generation_logger.removeFilter(message_filter)


def strip_prompt_prefix(text: str, prompt: str) -> str:
    """Strip prompt text if Whisper repeats the prompt at the beginning of the transcript."""
    if not prompt or not text:
        return text.strip()
    
    p_clean = prompt.strip()
    # 1. Exact full prompt match
    if text.lower().startswith(p_clean.lower()):
        text = text[len(p_clean):].lstrip(" .:,;!?")
    else:
        p_no_punct = p_clean.rstrip(".?!;:")
        if text.lower().startswith(p_no_punct.lower()):
            text = text[len(p_no_punct):].lstrip(" .:,;!?")

    # 2. Check individual sentences / comma phrases in the prompt
    for part in re.split(r'[.,;]\s*', p_clean):
        part = part.strip()
        if len(part) >= 4 and text.lower().startswith(part.lower()):
            text = text[len(part):].lstrip(" .:,;!?")

    return text.strip()


try:
    import torch
except ImportError:
    torch = None  # type: ignore

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None  # type: ignore

try:
    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor
except ImportError:
    AutoModelForSpeechSeq2Seq = None  # type: ignore
    AutoProcessor = None  # type: ignore


class WhisperASRAdapter(ASRAdapter):
    """Whisper ASR Adapter supporting local offline weights (faster-whisper or HuggingFace)."""

    def __init__(
        self,
        partial_interval_ms: int = 500,
        min_audio_rms: float = 0.003,
        beam_size: int = 1,
    ):
        self.model: Optional[Any] = None
        self.processor: Optional[Any] = None
        self.backend_type: str = "transformers"
        self.model_path: str = ""
        self.device: str = "cuda"
        self.compute_type: str = "float16"
        self._is_warm = False
        self.partial_interval_samples = max(1600, int(16000 * partial_interval_ms / 1000.0))
        self.min_audio_rms = max(0.0, float(min_audio_rms))
        self.beam_size = max(1, int(beam_size))
        # One weight instance is shared by two isolated sessions. Backend calls are serialized.
        self._inference_lock = threading.Lock()

    def initialize(self, model_path: str, device: str = "cuda", compute_type: str = "float16"):
        self.model_path = model_path
        self.device = self._resolve_device(device)
        self.compute_type = compute_type
        if self.device == "cpu" and compute_type == "float16":
            self.compute_type = "float32"

        path = Path(model_path)
        if not path.exists() and not (path.is_dir() or path.is_file()):
            if not Path(os.path.abspath(model_path)).exists():
                raise ModelNotFoundError(
                    f"ASR model not found at '{model_path}'. "
                    "Models must be downloaded manually to the exact local path."
                )

        has_ct2_model = (path / "model.bin").exists()

        if has_ct2_model and WhisperModel is not None:
            self.backend_type = "faster_whisper"
            logger.info(
                "Loading faster-whisper model from '%s' on %s (%s)...",
                model_path,
                self.device,
                self.compute_type,
            )
            self.model = WhisperModel(
                model_size_or_path=str(path.resolve()),
                device=self.device,
                compute_type=self.compute_type,
                local_files_only=True,
            )
        else:
            self.backend_type = "transformers"
            if AutoModelForSpeechSeq2Seq is None or torch is None:
                raise RuntimeError("transformers and torch are required for HuggingFace Whisper model.")

            logger.info(
                "Loading HuggingFace Whisper model from '%s' on %s (%s)...",
                model_path,
                self.device,
                self.compute_type,
            )
            torch_dtype = torch.float16 if (self.compute_type == "float16" and self.device == "cuda") else torch.float32

            self.processor = AutoProcessor.from_pretrained(
                str(path.resolve()),
                local_files_only=True,
            )
            self.model = AutoModelForSpeechSeq2Seq.from_pretrained(
                str(path.resolve()),
                dtype=torch_dtype,
                low_cpu_mem_usage=True,
                local_files_only=True,
            )
            # Transformers 5.x performs a nested generate() call for Whisper.
            # Clear legacy length/prompt fields on the in-memory config as well as
            # on per-call copies so the nested call cannot restore max_length=448.
            self.model.generation_config.max_length = None
            self.model.generation_config.forced_decoder_ids = None
            self.model.to(self.device)

        logger.info(f"Whisper model loaded successfully (backend: {self.backend_type}).")

    @staticmethod
    def _resolve_device(requested_device: str) -> str:
        requested = requested_device.strip().lower()
        if requested.startswith("cuda") and (torch is None or not torch.cuda.is_available()):
            logger.warning(
                "CUDA is unavailable; falling back to CPU for Whisper instead of using requested device '%s'.",
                requested_device,
            )
            return "cpu"
        return requested

    def warmup(self):
        if self.model is None:
            raise WarmupError("Model not initialized before warmup.")
        logger.info(f"Warming up Whisper model ({self.backend_type})...")
        dummy_audio = 0.05 * np.sin(2 * np.pi * 440 * np.linspace(0, 1, 16000, dtype=np.float32))
        try:
            with self._inference_lock:
                if self.backend_type == "faster_whisper":
                    segments, _ = self.model.transcribe(
                        dummy_audio,
                        language="tr",
                        beam_size=self.beam_size,
                        temperature=0.0,
                        condition_on_previous_text=False,
                    )
                    list(segments)
                else:
                    _ = self._transcribe_transformers(dummy_audio, "tr")

            self._is_warm = True
            logger.info("Whisper model warmup completed.")
        except Exception as e:
            raise WarmupError(f"Whisper warmup failed: {e}") from e

    def _transcribe_transformers(self, audio_16k: np.ndarray, language: str, prompt: str = "") -> tuple[str, dict[str, float]]:
        if self.model is None or self.processor is None:
            return "", {}

        # Energy gate: do not transcribe silence/noise
        rms = np.sqrt(np.mean(audio_16k ** 2)) if len(audio_16k) > 0 else 0.0
        if rms < self.min_audio_rms:
            return "", {"audio_rms": float(rms)}

        inputs = self.processor(audio_16k, sampling_rate=16000, return_tensors="pt")
        input_features = inputs.input_features.to(self.device)
        if self.compute_type == "float16" and self.device == "cuda" and torch is not None:
            input_features = input_features.half()

        # Generate prompt_ids if prompt is provided
        prompt_ids = None
        effective_prompt = prompt or getattr(self, "initial_prompt", "")
        if effective_prompt and hasattr(self.processor, "get_prompt_ids"):
            try:
                prompt_ids = self.processor.get_prompt_ids(effective_prompt, return_tensors="pt").to(self.device)
            except Exception:
                prompt_ids = None

        with torch.inference_mode():
            # Whisper's nested Transformers 5.x generate() restores a legacy
            # max_length even when a copied config uses max_new_tokens. Use one
            # bounded total length owner (4 prompt tokens + up to 64 text tokens).
            generation_config = copy.deepcopy(self.model.generation_config)
            generation_config.max_length = 68
            generation_config.max_new_tokens = None
            generation_config.forced_decoder_ids = None
            generation_config.language = language
            generation_config.task = "transcribe"
            generation_config.repetition_penalty = 1.2
            generation_config.no_repeat_ngram_size = 3
            generation_config.num_beams = self.beam_size
            generation_config.return_dict_in_generate = True
            generation_config.output_scores = True
            
            gen_kwargs = {"generation_config": generation_config}
            if prompt_ids is not None:
                gen_kwargs["prompt_ids"] = prompt_ids

            with _quiet_transformers_whisper_internal_warning():
                output = self.model.generate(input_features, **gen_kwargs)

        predicted_ids = output.sequences
        transcription = self.processor.batch_decode(
            predicted_ids,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )
        text = transcription[0].strip() if transcription else ""
        model_info = self._transformers_model_info(output, text)
        model_info["audio_rms"] = float(rms)
        
        # Strip common hallucinated subtitle prefixes
        if text.lower().startswith("altyazı") or text.lower().startswith("subtitle"):
            return "", model_info

        # Strip prompt text if Whisper repeated it at the start of transcription
        text = strip_prompt_prefix(text, effective_prompt)

        return text, model_info

    @staticmethod
    def _transformers_model_info(output: Any, text: str) -> dict[str, float]:
        """Extract confidence evidence already produced by generate()."""
        info: dict[str, float] = {}
        scores = getattr(output, "scores", None)
        sequences = getattr(output, "sequences", None)
        if torch is not None and scores and sequences is not None:
            count = min(len(scores), int(sequences.shape[-1]))
            generated = sequences[0, -count:]
            token_logprobs = []
            for score, token_id in zip(scores[-count:], generated):
                log_probs = torch.log_softmax(score[0].float(), dim=-1)
                token_logprobs.append(float(log_probs[int(token_id)].item()))
            if token_logprobs:
                info["avg_logprob"] = sum(token_logprobs) / len(token_logprobs)
        encoded = text.encode("utf-8")
        if encoded:
            info["compression_ratio"] = len(encoded) / max(1, len(zlib.compress(encoded)))
        return info

    def create_session(self, stream_id: str, direction: Direction, language: str, initial_prompt: str = "") -> ASRSession:
        return ASRSession(
            stream_id=stream_id,
            direction=direction,
            language=language,
            initial_prompt=initial_prompt or getattr(self, "initial_prompt", ""),
        )

    def process_audio(
        self,
        session: ASRSession,
        audio_chunk_16k: np.ndarray,
        captured_at_ns: int,
    ) -> Optional[UtteranceEvent]:
        if not session.is_active or len(audio_chunk_16k) == 0:
            return None

        captured_samples = session.total_audio_samples + len(audio_chunk_16k)
        capture_start_ns = captured_at_ns - int((captured_samples / 16000.0) * 1e9)
        session.metadata["capture_start_ns"] = min(
            capture_start_ns,
            int(session.metadata.get("capture_start_ns", capture_start_ns)),
        )
        session.metadata["capture_end_ns"] = max(
            captured_at_ns,
            int(session.metadata.get("capture_end_ns", captured_at_ns)),
        )
        session.audio_buffer.append(audio_chunk_16k)
        session.total_audio_samples += len(audio_chunk_16k)
        samples_since_decode = int(session.metadata.get("samples_since_decode", 0)) + len(audio_chunk_16k)
        session.metadata["samples_since_decode"] = samples_since_decode

        # Minimum 0.3s (4800 samples) before running ASR
        if session.total_audio_samples < 4800:
            return None

        # HuggingFace Whisper is not incremental. Decoding every 20 ms blocks the
        # audio drain worker and creates stale queued speech. Emit one early partial,
        # then coalesce subsequent revisions to a bounded cadence.
        if session.metadata.get("decode_attempted") and samples_since_decode < self.partial_interval_samples:
            return None

        # Bound audio buffer to maximum 4.0 seconds to prevent backlog accumulation
        if session.total_audio_samples > 64000:
            combined = np.concatenate(session.audio_buffer)
            session.audio_buffer = [combined[-64000:]]
            session.total_audio_samples = 64000

        combined_audio = np.concatenate(session.audio_buffer)

        try:
            session.metadata["samples_since_decode"] = 0
            session.metadata["decode_attempted"] = True
            prompt = session.initial_prompt or getattr(self, "initial_prompt", "")
            try:
                full_text, model_info = self._decode_audio(combined_audio, session.language, prompt=prompt)
            except TypeError:
                full_text, model_info = self._decode_audio(combined_audio, session.language)

            if not full_text:
                return None

            session.current_revision += 1
            session.last_partial_text = full_text
            session.metadata["last_model_info"] = model_info

            return UtteranceEvent(
                meeting_id=session.metadata.get("meeting_id", "local_session"),
                stream_id=session.stream_id,
                direction=session.direction,
                utterance_id=f"{session.stream_id}_{session.sequence_id}",
                sequence_id=session.sequence_id,
                revision=session.current_revision,
                state=UtteranceState.PARTIAL,
                source_language=session.language,
                text=full_text,
                audio_start_ns=captured_at_ns - int((len(combined_audio) / 16000.0) * 1e9),
                audio_end_ns=captured_at_ns,
                is_final=False,
                model_info=model_info,
            )
        except Exception as e:
            logger.error(f"Whisper inference error: {e}")
            return None

    def _decode_audio(self, audio_16k: np.ndarray, language: str, prompt: str = "") -> tuple[str, dict[str, Any]]:
        rms = float(np.sqrt(np.mean(audio_16k ** 2))) if len(audio_16k) else 0.0
        model_info: dict[str, Any] = {
            "backend": self.backend_type,
            "model": self.model_path,
            "audio_rms": rms,
            "condition_on_previous_text": False,
        }
        if rms < self.min_audio_rms:
            return "", model_info

        with self._inference_lock:
            if self.backend_type == "faster_whisper":
                segments, info = self.model.transcribe(
                    audio_16k,
                    language=language,
                    beam_size=self.beam_size,
                    temperature=0.0,
                    condition_on_previous_text=False,
                    vad_filter=False,
                    initial_prompt=prompt or None,
                )
                materialized = [segment for segment in segments if segment.text.strip()]
                text = " ".join(segment.text.strip() for segment in materialized).strip()
                text = strip_prompt_prefix(text, prompt)
                no_speech = [float(s.no_speech_prob) for s in materialized if getattr(s, "no_speech_prob", None) is not None]
                avg_logprobs = [float(s.avg_logprob) for s in materialized if getattr(s, "avg_logprob", None) is not None]
                compression = [float(s.compression_ratio) for s in materialized if getattr(s, "compression_ratio", None) is not None]
                if no_speech:
                    model_info["no_speech_prob"] = max(no_speech)
                if avg_logprobs:
                    model_info["avg_logprob"] = sum(avg_logprobs) / len(avg_logprobs)
                if compression:
                    model_info["compression_ratio"] = max(compression)
                if getattr(info, "language_probability", None) is not None:
                    model_info["language_probability"] = float(info.language_probability)
                return text, model_info

            text, transformer_info = self._transcribe_transformers(audio_16k, language, prompt=prompt)
            model_info.update(transformer_info)
            return text, model_info

    def flush_session(self, session: ASRSession) -> Optional[UtteranceEvent]:
        if not session.audio_buffer:
            session.audio_buffer.clear()
            session.total_audio_samples = 0
            session.metadata.pop("capture_start_ns", None)
            session.metadata.pop("capture_end_ns", None)
            return None

        combined_audio = np.concatenate(session.audio_buffer)
        try:
            prompt = session.initial_prompt or getattr(self, "initial_prompt", "")
            try:
                final_text, model_info = self._decode_audio(combined_audio, session.language, prompt=prompt)
            except TypeError:
                final_text, model_info = self._decode_audio(combined_audio, session.language)
        except Exception as exc:
            logger.error("Whisper final inference error: %s", exc)
            final_text = ""
            model_info = {}
        if not final_text:
            final_text = session.last_partial_text
            model_info = dict(session.metadata.get("last_model_info", model_info))

        now_ns = time.monotonic_ns()
        audio_start_ns = int(session.metadata.get("capture_start_ns", now_ns))
        audio_end_ns = int(session.metadata.get("capture_end_ns", now_ns))
        seq_id = session.sequence_id
        session.sequence_id += 1
        session.current_revision = 0
        session.audio_buffer.clear()
        session.total_audio_samples = 0
        session.last_partial_text = ""
        session.metadata.pop("samples_since_decode", None)
        session.metadata.pop("decode_attempted", None)
        session.metadata.pop("last_model_info", None)
        session.metadata.pop("capture_start_ns", None)
        session.metadata.pop("capture_end_ns", None)

        if not final_text:
            return None

        return UtteranceEvent(
            meeting_id=session.metadata.get("meeting_id", "local_session"),
            stream_id=session.stream_id,
            direction=session.direction,
            utterance_id=f"{session.stream_id}_{seq_id}",
            sequence_id=seq_id,
            revision=1,
            state=UtteranceState.COMMITTED,
            source_language=session.language,
            text=final_text,
            audio_start_ns=audio_start_ns,
            audio_end_ns=audio_end_ns,
            is_final=True,
            model_info=model_info or {"backend": self.backend_type, "model": self.model_path},
        )

    def close_session(self, session: ASRSession):
        session.is_active = False
        session.audio_buffer.clear()
        session.metadata.pop("capture_start_ns", None)
        session.metadata.pop("capture_end_ns", None)

    def shutdown(self):
        self.model = None
        self.processor = None
        self._is_warm = False
