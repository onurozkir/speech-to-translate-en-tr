# FILE_MAP.md — Subsystem Routing & File Responsibility Index

> **AGENT NAVIGATION INVARIANT:**
> - **DO NOT** perform broad recursive directory scans or grep the entire repository.
> - **CONSULT** the Subsystem Routing Matrix below first to identify the exact 1–2 files responsible for your task.
> - **INSPECT** and modify ONLY those target files and their paired unit test files.

---

## 1. Subsystem Routing Matrix (Task → Target Files)

| Task Domain | Primary Source Files | Paired Unit Test Files | Key Responsibilities |
|---|---|---|---|
| **VAD, Endpointing & SOV Logic** | `src/teams_translator/streaming/commit_policy.py`<br>`src/teams_translator/streaming/vad.py` | `tests/unit/test_commit_sov.py`<br>`tests/unit/test_commit_policy.py`<br>`tests/unit/test_vad.py` | Turkish SOV verb detection, 200 ms silence commit, conjunction holding, deverbal noun protection, Silero VAD state. |
| **Hallucination Filtering** | `src/teams_translator/streaming/hallucination_guard.py` | `tests/unit/test_hallucination_guard.py`<br>`tests/unit/test_pipeline_silence.py` | Speech evidence checks (`voiced_ms`, speech-rate ratio), normalized hallucination pattern guards, dot-I normalization. |
| **ASR & Whisper Inference** | `src/teams_translator/asr/whisper_backend.py`<br>`src/teams_translator/asr/base.py` | `tests/unit/test_whisper_streaming.py`<br>`tests/unit/test_adapters.py` | WhisperModel (CTranslate2) & HuggingFace pipelines, partial coalescing (500 ms), shared-weight inference scheduler. |
| **Machine Translation (MT)** | `src/teams_translator/translation/ctranslate_backend.py`<br>`src/teams_translator/translation/base.py` | `tests/unit/test_mt_ctranslate.py` | CTranslate2 INT8 MT (OPUS-MT TR↔EN, NLLB-200), EOS token handling, domain glossary injection, rolling discourse context. |
| **TTS & Voice Cloning** | `src/teams_translator/tts/xtts_backend.py`<br>`src/teams_translator/tts/conditioning.py`<br>`src/teams_translator/tts/base.py` | `tests/unit/test_tts_quality.py`<br>`tests/unit/test_xtts_runtime.py`<br>`tests/unit/test_pipeline_tts.py` | Coqui XTTS-v2 adapter, multi-sample conditioning discovery/hashing, hyperparameter tuning (`top_p`, `repetition_penalty`), -1 dBFS peak normalization. |
| **Audio Hardware & VB-CABLE** | `src/teams_translator/audio/devices.py`<br>`src/teams_translator/audio/capture.py`<br>`src/teams_translator/audio/render.py`<br>`src/teams_translator/audio/resampler.py` | `tests/unit/test_audio_devices.py`<br>`tests/unit/test_audio_signal.py`<br>`tests/unit/test_resampler.py` | DirectSound/WASAPI device discovery, non-blocking capture callbacks, stateful soxr resampling, VB-CABLE output rendering. |
| **Pipelines & Concurrency** | `src/teams_translator/streaming/pipeline_outgoing.py`<br>`src/teams_translator/streaming/pipeline_incoming.py`<br>`src/teams_translator/streaming/pipeline_runtime.py` | `tests/unit/test_pipeline_split_commit.py`<br>`tests/unit/test_bounded_queue.py` | Outgoing (Mic→ASR→MT→TTS→VB-CABLE) & Incoming (Loopback→ASR→MT→Web UI) state machines, bounded queues, ring buffers. |
| **Meeting Orchestrator** | `src/teams_translator/streaming/orchestrator.py` | `tests/unit/test_adapter_config.py`<br>`tests/integration/test_full_pipeline_mock.py` | Lifecycle coordinator (STOPPED, WARMING, READY, RUNNING), hardware resolution, dynamic voice profile and target language switching. |
| **Web UI & API** | `src/teams_translator/web/routes.py`<br>`src/teams_translator/web/websocket.py`<br>`src/teams_translator/web/server.py`<br>`src/teams_translator/web/static/` | `tests/unit/test_web_static.py`<br>`tests/integration/test_web_api.py` | FastAPI REST endpoints (`/api/start`, `/api/stop`, `/api/devices`), WebSocket live telemetry broadcast, WhisperLiveKit static frontend. |
| **Configuration & Models** | `config/default.toml`<br>`src/teams_translator/config/models.py`<br>`src/teams_translator/config/loader.py` | `tests/unit/test_adapter_config.py` | AppConfig dataclasses (Audio, ASR, Translation, TTS, Streaming, Persistence), TOML deserialization. |
| **Persistence (SQLite)** | `src/teams_translator/persistence/database.py`<br>`src/teams_translator/persistence/schema.py` | `tests/unit/test_persistence.py` | Asynchronous non-blocking SQLite worker (`data/meetings.sqlite3`), schema migrations, utterance logging, latency event persistence. |
| **Telemetry & Latency** | `src/teams_translator/telemetry/metrics.py`<br>`src/teams_translator/telemetry/system.py` | `tests/unit/test_telemetry.py` | P50/P95 latency percentiles, queue age tracking, GPU VRAM & RTF telemetry snapshots. |

---

## 2. Directory Structure & File Index

### `src/teams_translator/`
```text
src/teams_translator/
├── main.py                     # CLI entrypoint (run, mock, download commands)
│
├── asr/                        # Speech-to-Text (ASR) subsystem
│   ├── base.py                 # ASRAdapter abstract contract and ASRSession state
│   ├── whisper_backend.py      # WhisperModel (faster-whisper) & HuggingFace implementation with scheduler
│   └── mock_backend.py         # MockASRAdapter for offline testing
│
├── audio/                      # Audio I/O, device discovery, and signal processing
│   ├── devices.py              # AudioDeviceManager: WASAPI/DirectSound device discovery & stable fingerprinting
│   ├── capture.py              # Non-blocking PortAudio / WASAPI stream capture
│   ├── render.py               # AudioRenderEngine: float32-to-int16 render to VB-CABLE Input
│   ├── resampler.py            # Stateful soxr resampling (e.g. 48kHz -> 16kHz / 24kHz)
│   ├── signal.py               # Audio signal analysis (RMS, peak, dominant frequency)
│   └── diagnostic.py           # Audio pipeline diagnostics and calibration
│
├── config/                     # Configuration schema & loading
│   ├── models.py               # Pydantic/Dataclass config schemas (Audio, ASR, Translation, TTS, etc.)
│   └── loader.py               # TOML loader with environment and local override support
│
├── core/                       # Core primitives, data structures, and errors
│   ├── types.py                # Core enums & dataclasses (MeetingStatus, Direction, UtteranceEvent, LatencyEvent)
│   ├── bounded_queue.py        # BoundedQueue with drop-oldest / replace policies
│   ├── ring_buffer.py          # Lockless / low-overhead circular PCM buffer
│   └── errors.py               # Custom exceptions (ModelNotFoundError, WarmupError, DeviceError)
│
├── persistence/                # SQLite local storage
│   ├── schema.py               # DDL schema for meetings, utterances, latency_events
│   └── database.py             # PersistenceWorker: background queue worker for SQLite writes
│
├── streaming/                  # Realtime pipelines and decision controllers
│   ├── orchestrator.py         # MeetingOrchestrator: high-level coordinator of all adapters & pipelines
│   ├── pipeline_outgoing.py    # OutgoingPipeline: Mic -> VAD -> ASR -> MT -> TTS -> VB-CABLE
│   ├── pipeline_incoming.py    # IncomingPipeline: Speaker Loopback -> VAD -> ASR -> MT -> Web UI
│   ├── pipeline_runtime.py     # Pipeline helper factories and common event builders
│   ├── vad.py                  # SileroVAD and energy-based Voice Activity Detection
│   ├── commit_policy.py        # CommitController: Turkish SOV verb detection, punctuation, timeouts
│   └── hallucination_guard.py  # HallucinationGuard: VAD evidence gating and subtitle hallucination rejection
│
├── telemetry/                  # Metrics, profiling, and latency tracking
│   ├── metrics.py              # TelemetryTracker: rolling window P50/P95 latency percentiles
│   ├── system.py               # SystemMetrics: CPU, GPU VRAM, RAM sampling
│   └── timer.py                # Monotonic latency timer helpers
│
├── translation/                # Machine Translation (MT) subsystem
│   ├── base.py                 # MTAdapter abstract base class
│   ├── ctranslate_backend.py   # CTranslate2MTAdapter (INT8 OPUS-MT, NLLB-200, glossary, context)
│   └── mock_backend.py         # MockMTAdapter for fast offline tests
│
├── tts/                        # Text-to-Speech (TTS) & Voice Cloning subsystem
│   ├── base.py                 # TTSAdapter ABC and VoiceProfile dataclass
│   ├── xtts_backend.py         # XTTSv2Adapter: Coqui XTTS-v2 with conditioning cache and peak normalization
│   ├── conditioning.py         # VoiceProfileManager: multi-reference audio discovery and deterministic SHA256 hashing
│   ├── chatterbox_backend.py   # Experimental alternative TTS backend
│   └── mock_backend.py         # MockTTSAdapter (generates sine waves for offline tests)
│
└── web/                        # HTTP & WebSocket Web UI
    ├── server.py               # FastAPI application setup
    ├── routes.py               # REST API routes (/api/status, /api/start, /api/stop, /api/devices, /api/profiles)
    ├── websocket.py            # WebSocket live telemetry and subtitle streaming handler
    └── static/                 # WhisperLiveKit frontend assets (index.html, app.js, style.css)
```

---

## 3. Configuration & Scripts

* `config/default.toml`: Primary application configuration (audio endpoint selectors, model paths, ASR/MT/TTS hyperparameters, queue sizes).
* `scripts/download_models.py`: CLI model downloader ensuring offline local weights policy.
* `scripts/convert_models_ct2.py`: Utility to convert HuggingFace models to CTranslate2 INT8 format.

---

## 4. Test Suite Map

* `tests/unit/test_commit_sov.py`: Turkish SOV verb suffix matching, conjunction pause holding, deverbal noun blacklist.
* `tests/unit/test_tts_quality.py`: XTTS hyperparameter validation (`top_p`, `repetition_penalty`), multi-sample hashing, -1 dBFS peak normalization.
* `tests/unit/test_mt_ctranslate.py`: CTranslate2 INT8 translation, glossary injection, EOS token enforcement.
* `tests/unit/test_whisper_streaming.py`: Whisper partial coalescing, shared scheduler priority, timestamp preservation.
* `tests/unit/test_hallucination_guard.py`: Normalized denylist filtering, Turkish dotted-I handling, speech evidence gating.
* `tests/unit/test_audio_devices.py` & `test_audio_signal.py`: Device enumeration, format checks, RMS/peak calculations.
* `tests/unit/test_adapter_config.py`: Adapter runtime wiring from config.
* `tests/integration/test_full_pipeline_mock.py`: End-to-end full-duplex pipeline lifecycle test using mock adapters.
* `tests/integration/test_web_api.py`: FastAPI endpoints and WebSocket lifecycle test.

---

## 5. Agent Instructions for Adding/Editing Code

1. **Locate Subsystem**: Find your task topic in Section 1 (Subsystem Routing Matrix).
2. **Open Only Relevant Files**: Do not read unrelated subsystems. For example, if updating translation glossary logic, open *only* `src/teams_translator/translation/ctranslate_backend.py` and `tests/unit/test_mt_ctranslate.py`.
3. **Run Targeted Tests**: After making changes, run only the paired unit test file first:
   ```bash
   pytest tests/unit/test_mt_ctranslate.py -v
   ```
4. **Run Full Test Suite**: Before concluding, run the full test suite to ensure 0 regressions:
   ```bash
   pytest -v tests/
   ```

