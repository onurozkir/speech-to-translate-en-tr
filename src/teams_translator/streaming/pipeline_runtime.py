"""Shared runtime construction and utterance reset helpers for both directions."""

from __future__ import annotations

from teams_translator.asr.base import ASRSession
from teams_translator.config.models import StreamingConfig
from teams_translator.streaming.hallucination_guard import (
    HallucinationGuard,
    HallucinationPolicy,
    SpeechEvidence,
)
from teams_translator.streaming.vad import SileroVAD, VADResult


def build_vad(config: StreamingConfig) -> SileroVAD:
    return SileroVAD(
        threshold=config.vad_threshold,
        end_threshold=config.vad_end_threshold,
        min_speech_duration_ms=config.vad_min_speech_duration_ms,
        min_silence_duration_ms=config.vad_min_silence_duration_ms,
        start_confirm_frames=config.vad_start_confirm_frames,
        end_confirm_frames=config.vad_end_confirm_frames,
        hangover_ms=config.vad_hangover_ms,
        energy_start_dbfs=config.vad_energy_start_dbfs,
        energy_end_dbfs=config.vad_energy_end_dbfs,
    )


def build_guard(config: StreamingConfig) -> HallucinationGuard:
    return HallucinationGuard(
        HallucinationPolicy(
            min_utterance_ms=config.guard_min_utterance_ms,
            min_voiced_ms=config.guard_min_voiced_ms,
            min_voiced_ratio=config.guard_min_voiced_ratio,
            max_audio_queue_age_ms=config.max_audio_queue_age_ms,
            max_no_speech_prob=config.whisper_max_no_speech_prob,
            min_avg_logprob=config.whisper_min_avg_logprob,
            max_compression_ratio=config.whisper_max_compression_ratio,
        )
    )


def speech_evidence(result: VADResult, max_queue_age_ms: float) -> SpeechEvidence:
    return SpeechEvidence(
        utterance_ms=result.utterance_ms,
        voiced_ms=result.voiced_ms,
        voiced_ratio=result.voiced_ratio,
        max_queue_age_ms=max_queue_age_ms,
    )


def reset_asr_utterance(session: ASRSession | None) -> None:
    if session is None:
        return
    session.audio_buffer.clear()
    session.total_audio_samples = 0
    session.last_partial_text = ""
    session.current_revision = 0
    session.metadata.pop("last_model_info", None)
    session.metadata.pop("samples_since_decode", None)
    session.metadata.pop("decode_attempted", None)


def next_pcm_chunk(iterator):
    try:
        return True, next(iterator)
    except StopIteration:
        return False, None
