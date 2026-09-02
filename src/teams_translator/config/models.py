"""Pydantic configuration models."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    open_browser: bool = True


class AudioConfig(BaseModel):
    sample_rate: int = 48000
    channels: int = 1
    frame_duration_ms: int = 20
    ring_buffer_duration_sec: float = 5.0
    mic_device_id: str = ""
    loopback_device_id: str = ""
    render_device_id: str = ""


class StreamingConfig(BaseModel):
    vad_threshold: float = 0.5
    vad_end_threshold: float = 0.35
    vad_min_speech_duration_ms: int = 200
    vad_min_silence_duration_ms: int = 400
    vad_start_confirm_frames: int = 3
    vad_end_confirm_frames: int = 6
    vad_hangover_ms: int = 80
    vad_energy_start_dbfs: float = -40.0
    vad_energy_end_dbfs: float = -46.0
    guard_min_utterance_ms: float = 280.0
    guard_min_voiced_ms: float = 220.0
    guard_min_voiced_ratio: float = 0.25
    max_audio_queue_age_ms: float = 600.0
    whisper_max_no_speech_prob: float = 0.80
    whisper_min_avg_logprob: float = -1.20
    whisper_max_compression_ratio: float = 2.40
    commit_min_words: int = 3
    commit_max_wait_ms: int = 1800
    stable_prefix_min_count: int = 2
    max_partial_queue_size: int = 2
    max_committed_queue_size: int = 8
    max_tts_queue_size: int = 8


class ASRConfig(BaseModel):
    backend: str = "whisper_turbo"
    model_path: str = "models/asr/whisper-large-v3-turbo"
    device: str = "cuda"
    compute_type: str = "float16"
    beam_size: int = 1
    partial_interval_ms: int = 500
    min_audio_rms: float = 0.003
    language_mic: str = "tr"
    language_loopback: str = "en"
    initial_prompt: str = "Toplantı, Türkçe, teknik, iş, günlük konuşma."
    share_weights: bool = True


class TranslationConfig(BaseModel):
    backend: str = "ctranslate2"
    tr_en_model_path: str = "models/mt/opus-mt-tc-big-tr-en"
    en_tr_model_path: str = "models/mt/opus-mt-tc-big-en-tr"
    tr_fr_model_path: str = "models/mt/opus-mt-tr-fr"
    device: str = "cpu"
    compute_type: str = "int8"
    beam_size: int = 2


class TTSConfig(BaseModel):
    backend: str = "xtts_v2"
    model_path: str = "models/tts/xtts-v2"
    device: str = "cuda"
    voice_profile_id: str = "onur-default"
    sample_rate: int = 24000
    temperature: float = 0.75
    speed: float = 1.0


class VoiceConfig(BaseModel):
    profiles_root: str = "voices"
    default_profile: str = "onur-default"


class PersistenceConfig(BaseModel):
    enabled: bool = False
    database_path: str = "data/meetings.sqlite3"
    recordings_root: str = "recordings"
    batch_size: int = 20
    flush_interval_sec: float = 2.0


class TelemetryConfig(BaseModel):
    window_size: int = 100
    sample_interval_sec: float = 1.0
    high_latency_threshold_ms: float = 2500.0


class AppConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    streaming: StreamingConfig = Field(default_factory=StreamingConfig)
    asr: ASRConfig = Field(default_factory=ASRConfig)
    translation: TranslationConfig = Field(default_factory=TranslationConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    persistence: PersistenceConfig = Field(default_factory=PersistenceConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
