# Decision Matrix — Teams Real-Time Translator

Use this sheet after local benchmarks. Scores are intentionally left blank until measured on the RTX 5060 Ti.

## ASR / Speech Translation

| Candidate | First partial ms | First commit ms | TR→EN quality | EN ASR quality | VRAM | License | Decision |
|---|---:|---:|---:|---:|---:|---|---|
| WhisperLiveKit + large-v3-turbo | | | | | | Apache/MIT components + model license | |
| SimulStreaming + large-v3 | | | | | | MIT + model license | |
| WhisperLiveKit + smaller Whisper | | | | | | | |
| Turkish-tuned Whisper turbo | | | | n/a | | | |

## EN→TR Translation

| Candidate | 5-word ms | 10-word ms | Quality | Terminology | VRAM/RAM | License | Decision |
|---|---:|---:|---:|---:|---:|---|---|
| OPUS-MT TC-big EN→TR + CT2 | | | | | | CC-BY-4.0 | |
| Small OPUS EN→TR + CT2 | | | | | | | |
| NLLB-200 distilled 600M | | | | | | CC-BY-NC-4.0 | |

## TTS / Voice Clone

| Candidate | First PCM ms | RTF | Speaker similarity | English quality | Streaming | VRAM | License | Decision |
|---|---:|---:|---:|---:|---|---:|---|---|
| XTTS-v2 | | | | | Yes | | CPML / non-commercial | |
| CosyVoice2/current CosyVoice | | | | | Yes | | verify selected weights | |
| OpenVoice V2 | | | | | | | MIT code / verify weights | |
| Piper generic | | | n/a | | Yes/fast | | model-dependent | fallback |

## End-to-end

| Scenario | p50 | p95 | p99 | Drop/backlog events | Notes |
|---|---:|---:|---:|---:|---|
| TR mic → first EN PCM to VB-CABLE | | | | | |
| EN Teams → first partial TR text | | | | | |
| EN Teams → stable TR phrase | | | | | |
| Full duplex simultaneous speech | | | | | |

## Final selection rules

1. Latency is the primary ranking dimension.
2. Reject candidates that accumulate backlog under full-duplex load.
3. For outgoing TTS, speaker identity and intelligibility are hard gates after latency.
4. Prefer permissive/commercially usable licenses when quality/latency are close.
5. Prefer fewer model stages on the hot path.
6. Select the smallest model that meets the quality gate; unused accuracy is not worth latency.
