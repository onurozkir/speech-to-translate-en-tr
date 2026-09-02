# Speech to Translate Project State

Last updated: 2026-09-02

## Current Focus
Phase B+ Architecture & Codebase Implementation completed. All core modules, audio layer, adapters (ASR, MT, TTS), streaming orchestrator, SQLite persistence, telemetry, web UI, CLI, benchmark scripts, and test suite are implemented and verified.

## Subsystems
- **Audio Layer (`src/teams_translator/audio`)**: PyAudioWPatch / WASAPI device enumeration, non-blocking capture & render ring buffers, resampler.
- **ASR Adapter (`src/teams_translator/asr`)**: Whisper ASR adapter with multi-session weight sharing and mock test adapter.
- **MT Adapter (`src/teams_translator/translation`)**: CTranslate2 INT8 OPUS-MT (TR<->EN) adapter and mock adapter.
- **TTS Adapter (`src/teams_translator/tts`)**: Coqui XTTS-v2 cross-language voice cloning with conditioning disk cache, Chatterbox benchmark adapter, and mock adapter.
- **Streaming Orchestrator (`src/teams_translator/streaming`)**: Silero-VAD, CommitController (stable-prefix, punctuation, and clause boundaries for SOV/SVO alignment), OutgoingPipeline, IncomingPipeline, MeetingOrchestrator.
- **Persistence (`src/teams_translator/persistence`)**: SQLite WAL mode background async worker with bounded batching.
- **Telemetry (`src/teams_translator/telemetry`)**: Rolling P50/P95 latency percentiles, GPU VRAM and CPU monitor.
- **Web UI (`src/teams_translator/web`)**: FastAPI + WebSockets + responsive dual-pipeline live subtitle/cloned speech UI (localhost:8000 only).
- **CLI & Benchmarks (`src/teams_translator/main.py`, `scripts/`)**: CLI runner, device lister, environment checker, model downloader, and B1-B6 benchmark scripts.

## Next
1. Install remaining Python dependencies (`PyAudioWPatch`, `ctranslate2`, `soundfile`, `soxr`, `TTS`, `faster-whisper`).
2. Install VB-CABLE Virtual Audio Driver.
3. Download pinned models via `python scripts/download_models.py all`.
4. Place voice reference sample in `voices/onur-default/reference.wav`.
5. Run application: `python src/teams_translator/main.py run`.
