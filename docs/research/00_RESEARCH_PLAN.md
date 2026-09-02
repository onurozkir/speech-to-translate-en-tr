# MS Teams Real-Time TR↔EN Translation — Research & POC Plan

**Status:** Research / architecture selection  
**Date:** 2026-09-02  
**Primary constraint:** Minimum end-to-end latency  
**Target machine:** RTX 5060 Ti 16 GB, 32 GB RAM, Python 3.12, CUDA 12.8, Windows

> This document is a research baseline, not the final implementation decision. The final stack should be chosen only after local latency/quality benchmarks on the target PC.

---

## 1. Goal

Build a local-first real-time translator for Microsoft Teams with two independent pipelines:

1. **Outgoing — Turkish → English speech**
   - Capture the user's physical microphone.
   - Translate Turkish speech incrementally into English.
   - Synthesize English with a selectable voice profile, preferably the user's cloned voice.
   - Stream synthesized PCM into a virtual microphone used by Teams.

2. **Incoming — English → Turkish text**
   - Capture Teams' remote audio.
   - Transcribe English incrementally.
   - Translate stable English text incrementally into Turkish.
   - Display partial/committed Turkish text in an always-on-top local overlay/input.

The system must not wait for an entire 5–10 second utterance before producing output.

---

## 2. Architectural correction: what VB-CABLE does

VB-CABLE is an audio routing driver. It does **not** perform ASR, translation, TTS, or inference and it does not remove the CPU/GPU from the pipeline.

The intended route is:

```text
Physical Mic
    ↓
Native Windows audio capture
    ↓
GPU inference: streaming speech translation / ASR
    ↓
GPU/CPU inference: TTS
    ↓
CABLE Input   [playback endpoint]
    ↓  VB-CABLE driver
CABLE Output  [recording endpoint]
    ↓
Microsoft Teams Microphone
```

Official VB-CABLE: https://vb-audio.com/Cable/

Microsoft Teams supports explicitly selecting microphone and speaker devices:
https://support.microsoft.com/en-US/teams/meetings/manage-audio-settings-in-microsoft-teams-meetings

---

## 3. Proposed audio topology

### 3.1 Outgoing: Turkish microphone → English voice in Teams

```mermaid
flowchart LR
    MIC[Physical microphone] --> CAP[WASAPI capture\n20 ms frames]
    CAP --> VAD[VAD / VAC]
    VAD --> ST[SimulStreaming / Whisper\nTR speech -> EN text]
    ST --> COMMIT[Stable-prefix commit buffer]
    COMMIT --> TTS[Streaming TTS\ncloned/selectable voice]
    TTS --> RB[Audio ring buffer]
    RB --> CABLEIN[CABLE Input]
    CABLEIN --> CABLEOUT[CABLE Output]
    CABLEOUT --> TEAMS[Teams microphone]
```

**Key simplification:** for Turkish → English, Whisper/SimulStreaming can use the Whisper **translate** task and emit English directly. A separate Turkish→English MT model is therefore optional and should not be in the default latency path unless benchmarking proves it improves quality enough to justify the cost.

### 3.2 Incoming: English from Teams → Turkish text overlay

Preferred POC path:

```mermaid
flowchart LR
    TEAMS[Teams speaker output] --> LOOP[WASAPI device loopback]
    LOOP --> ASR[Streaming English ASR]
    ASR --> STABLE[Stable English tokens]
    STABLE --> MT[EN -> TR Marian/OPUS-MT\nCTranslate2]
    MT --> UI[Local Turkish live overlay/input]
```

This avoids requiring a second virtual cable during the first POC.

**Trade-off:** device loopback captures all sound played through that Windows output device, not only Teams. For production isolation, route Teams to a dedicated second virtual cable/device and mirror it to the headset.

---

## 4. Core streaming principle: do not speak unstable ASR text

A naive system would synthesize every partial Whisper hypothesis. This is incorrect because streaming ASR revisions are normal, while already-played audio cannot be retracted.

Use two text states:

- **Partial / unstable:** visible in UI only; may change.
- **Committed / stable:** append-only words emitted by AlignAtt / LocalAgreement policy; only these enter TTS.

Recommended TTS chunk trigger policy for the first benchmark:

- start after **4–8 committed words**, or
- punctuation / semantic boundary, or
- maximum wait of approximately **600–900 ms** after a usable stable prefix appears.

While TTS speaks chunk `N`, ASR and translation continue preparing chunk `N+1`.

```text
Audio capture ────────────────►
ASR           [chunk 1][chunk 2][chunk 3]...
Commit             [C1]   [C2]   [C3]
TTS                  [T1]   [T2]   [T3]
VB-CABLE               [audio stream continuously]
```

This overlap is the main way to prevent a 10-second speech segment from creating a 10-second wait.

---

## 5. Recommended baseline stack for the POC

### A. Streaming ASR / Turkish → English speech translation

**Primary candidate:** `QuentinFuxa/WhisperLiveKit`
- Repository: https://github.com/QuentinFuxa/WhisperLiveKit
- Provides simultaneous/streaming ASR.
- Uses SimulStreaming / AlignAtt policy.
- Supports direct English translation with `--direct-english-translation`.
- Provides WebSocket/server architecture if we decide to separate services.
- Good integration layer around current streaming research.

**Underlying reference:** `ufal/SimulStreaming`
- Repository: https://github.com/ufal/SimulStreaming
- Supports direct Whisper speech→English translation from multilingual input.
- Project reports roughly 5× speed improvement over its older WhisperStreaming approach.
- Supports terminology/context prompts.

**Model to benchmark first:**
- `openai/whisper-large-v3-turbo`
- Also benchmark `medium`/`small` or a Turkish-tuned turbo model if latency or Turkish recognition is better on this GPU.

### B. Incoming English → Turkish machine translation

**Primary candidate:** `Helsinki-NLP/opus-mt-tc-big-en-tr`
- Model: https://huggingface.co/Helsinki-NLP/opus-mt-tc-big-en-tr
- Dedicated EN→TR Marian/OPUS model.
- License: CC-BY-4.0.
- Convert/run with **CTranslate2** to minimize runtime overhead.

**Benchmark alternatives:**
- smaller OPUS-MT EN→TR model for raw latency.
- `facebook/nllb-200-distilled-600M` as a multilingual quality baseline, but it is larger and its CC-BY-NC license makes it a weaker default for a potentially commercial project.

### C. TTS / voice cloning

#### Candidate 1 — XTTS-v2

- Model: https://huggingface.co/coqui/XTTS-v2
- Maintained code ecosystem: https://github.com/idiap/coqui-ai-TTS
- Cross-language voice cloning.
- English and Turkish are supported languages.
- Multiple speaker reference files can be used.
- Streaming inference is documented below 200 ms under appropriate conditions.
- 24 kHz output.

**Major constraint:** XTTS-v2 weights use the **Coqui Public Model License**, which permits non-commercial use only. This is acceptable for personal POC/evaluation but must be treated as a licensing blocker if this becomes a commercial product.

#### Candidate 2 — CosyVoice2 / current CosyVoice family

- Repository: https://github.com/FunAudioLLM/CosyVoice
- Streaming text input + streaming audio output.
- Project reports latency as low as ~150 ms on its tested setup.
- Zero-shot / cross-lingual speaker cloning features.
- More attractive licensing path than XTTS for a future product.

**POC question to verify locally:** how well a Turkish reference voice preserves identity when the generated target language is English.

#### Candidate 3 — OpenVoice V2

- Repository: https://github.com/myshell-ai/OpenVoice
- Permissive architecture/license and cross-lingual voice cloning.
- Useful as a third benchmark for speaker similarity and timbre transfer.

#### Fallback — Piper

Piper is useful as a very fast, deterministic non-cloned fallback voice. It is not the primary solution for the user's own English cloned voice.

---

## 6. Existing GitHub projects worth studying

| Project | Why it matters | Use decision |
|---|---|---|
| https://github.com/QuentinFuxa/WhisperLiveKit | Modern low-latency streaming ASR/translation foundation | **Primary foundation candidate** |
| https://github.com/ufal/SimulStreaming | Core simultaneous policy / direct TR speech→EN | **Algorithm/reference** |
| https://github.com/vovaauer/mentalese | Very close functional idea: Whisper + NLLB + Coqui + VB-CABLE + bidirectional voice clone | **Architecture/reference; not preferred base** |
| https://github.com/roirude/LiveLingo | Windows virtual microphone + Teams/VB-CABLE routing; modular Python pipeline | **Audio-routing reference** |
| https://github.com/NBS282/LiveTranslate | Local subtitles, virtual cable, voice cloning, desktop UX | **UI/desktop/reference** |
| https://github.com/facebookresearch/seamless_communication | End-to-end simultaneous speech translation research | **Benchmark/alternative, not initial base** |
| https://github.com/ufal/whisper_streaming | Older LocalAgreement implementation | **Historical reference only** |
| https://github.com/s0d3s/PyAudioWPatch | Native Windows WASAPI loopback from Python | **Recommended audio capture library** |

### Why not simply fork Mentalese?

Mentalese validates almost exactly this use case, but its architecture uses the classic `Whisper → NLLB → Coqui` chain. For the minimum-latency target we can remove the outgoing NLLB stage and use newer simultaneous streaming policies. It is therefore more useful as a routing/configuration reference than as the final inference core.

### Why not simply fork LiveLingo?

Its README explicitly describes a chunked near-real-time design and a typical 1–4 second wait after an utterance/sentence. It is useful for device handling but not aggressive enough for the streaming requirement.

---

## 7. Voice profile design

Target UX:

```text
Voice: [ Onur - Neutral ▼ ]
       [ Onur - Formal  ]
       [ Onur - Energetic ]
       [ Generic Male EN ]
       [ Generic Female EN ]
```

Suggested local data:

```text
voices/
  onur/
    neutral_01.wav
    neutral_02.wav
    formal_01.wav
    energetic_01.wav
    profile.json
    cache/
      xtts_speaker_embedding.*
      cosyvoice_prompt_cache.*
```

At application startup:

1. Load voice profile metadata.
2. Compute/load cached speaker conditioning/embedding once.
3. Keep the selected/default profile resident.
4. Do **not** recompute speaker embeddings for every sentence.

Reference recording guidance for benchmarks:
- clean room / clean mic,
- no music or reverb,
- neutral Turkish clip(s),
- start with ~6–20 seconds total,
- test single-reference vs multi-reference identity.

The recording language can remain Turkish; the TTS engine should generate the target text in English while preserving speaker identity.

---

## 8. Python vs Node.js

### Recommended: Python for the real-time inference/audio core

Reasons:
- PyTorch/Whisper/CTranslate2/TTS ecosystems are Python-first.
- Native Windows audio is available through PyAudioWPatch / PortAudio / WASAPI.
- Avoid IPC and serialization between Node and Python on the critical path.

Node.js can still be used later for a desktop/frontend shell if desired, but it should not own the inference pipeline.

A good compromise is:

```text
Python realtime-engine
  ├─ WASAPI capture/output
  ├─ ASR / speech translation
  ├─ MT
  ├─ TTS
  └─ WebSocket telemetry/control

Optional Tauri/Web frontend
  └─ overlay, device selection, voice profiles, metrics
```

---

## 9. Docker decision

**Do not put Windows realtime audio routing in Docker for the initial implementation.**

WASAPI and VB-CABLE are host Windows devices. Containerizing the critical audio capture/playback path creates extra device plumbing and makes latency/debugging worse.

Recommended:
- native Windows Python virtual environments/processes for the POC,
- optionally containerize non-realtime helper services later,
- use a single launcher script to start all local services.

---

## 10. MCP decision

MCP is **not required at runtime** and should not be inserted into the audio path.

It can be useful later only as a development/operations convenience, for example:
- expose benchmark results,
- control local profiles/configuration,
- inspect logs or device state from an agent.

MCP would add no value to speech latency itself.

---

## 11. Initial Python package shortlist

Create isolated environments if the TTS dependency tree conflicts with ASR/translation.

### `realtime-core`

```text
torch
torchaudio
numpy
PyAudioWPatch
soundfile
soxr                 # benchmark against lower-overhead resampling path
whisperlivekit
faster-whisper
ctranslate2
sentencepiece
fastapi
uvicorn
websockets
pydantic
pydantic-settings
psutil
nvidia-ml-py         # optional GPU telemetry
```

### `tts-service`

```text
torch
torchaudio
coqui-tts            # XTTS benchmark
soundfile
numpy
fastapi
uvicorn
```

CosyVoice may be installed from its repository in a separate environment due to its own dependency/runtime stack.

### Optional desktop overlay

```text
PySide6
```

or use a lightweight Tauri/web frontend later.

---

## 12. CUDA / RTX 5060 Ti note

RTX 5060 Ti is a Blackwell-generation GPU, so the PyTorch build must include Blackwell (`sm_120`) support. Do not use an old CUDA/PyTorch wheel just because CUDA 12.x is installed globally.

For the POC, pin a validated CUDA 12.8 PyTorch build in the project environment rather than inheriting random system packages.

We should add a startup diagnostic that prints:

```text
Python version
PyTorch version
CUDA runtime used by PyTorch
torch.cuda.get_device_name()
compute capability
CTranslate2 CUDA availability
VRAM total/free
selected audio devices + sample rates
```

---

## 13. Process architecture

First implementation should remain small and observable:

```text
realtime-engine.exe/python
  ├─ AudioCaptureWorker
  ├─ OutgoingTranslator
  ├─ IncomingTranslator
  ├─ AudioPlaybackWorker
  ├─ PriorityScheduler
  └─ Metrics/EventBus

TTS service (separate process only if dependency/GPU isolation is useful)

UI
  └─ WebSocket to realtime-engine
```

### GPU scheduling

Both sides can receive speech simultaneously. Start with one shared Whisper model and a priority queue:

1. outgoing translation is highest priority because another participant is waiting for our audio,
2. incoming subtitles second,
3. TTS generation gets its own bounded queue,
4. reject/drop stale partial work rather than building a backlog.

If contention is measurable, benchmark a second ASR model instance if VRAM permits.

---

## 14. No-backlog rule

For a realtime system, correctness includes staying near the live edge.

Every internal queue should be **bounded**. If a temporary overload occurs:

- drop superseded partial hypotheses,
- preserve committed words,
- never let 3 seconds of work turn into 20 seconds of delayed playback,
- emit a metric when real-time factor falls behind 1.0.

This is more important than maximizing throughput.

---

## 15. Latency instrumentation

Each chunk/event should carry timestamps:

```text
t_capture
t_vad_active
t_asr_partial
t_asr_commit
t_mt_done
t_tts_request
t_tts_first_pcm
t_cable_write
t_ui_render
```

Calculate at least:

- mic → first committed EN token,
- mic → first synthesized PCM,
- mic → CABLE write,
- Teams loopback → EN ASR partial,
- Teams loopback → first Turkish text,
- TTS real-time factor,
- ASR real-time factor,
- p50 / p95 / p99 latency.

### Initial engineering targets — to be validated, not promises

| Path | Initial target |
|---|---:|
| Mic → first useful committed English text | < 700–1000 ms p50 |
| Mic → first translated audio into VB-CABLE | ~0.8–1.5 s p50 |
| Remote English → partial Turkish visible | < 1.0 s p50 |
| Remote English → stable Turkish phrase | ~1.0–1.5 s p50 |
| Sustained realtime factor | < 1.0 under simultaneous use |

Turkish→English word order means truly zero-delay interpretation is impossible; the system needs enough linguistic context to avoid speaking wrong English that cannot be retracted.

---

## 16. Benchmark matrix before final stack decision

Do not select models by model-card claims alone. Benchmark on the actual RTX 5060 Ti.

### Experiment A — ASR / direct speech translation

Input corpus:
- 20 short Turkish sentences,
- 10 long 10–20 second explanations,
- technical English names/acronyms,
- normal speech + fast speech.

Compare:
1. WhisperLiveKit + SimulStreaming + `large-v3-turbo`
2. SimulStreaming direct + `large-v3`
3. smaller/faster Whisper variants
4. optional Turkish-tuned turbo model

Measure:
- first partial latency,
- first commit latency,
- final accuracy,
- direct TR→EN translation quality,
- GPU VRAM and real-time factor.

### Experiment B — EN→TR MT

Compare:
1. OPUS-MT TC-big EN→TR via CTranslate2 FP16
2. same model quantized if supported/beneficial
3. smaller OPUS model
4. NLLB 600M reference

Measure:
- 5/10/20-word prefix latency,
- incremental translation stability,
- technical terminology quality.

### Experiment C — TTS / own voice

Compare:
1. XTTS-v2
2. CosyVoice2/current CosyVoice 0.5B variant
3. OpenVoice V2
4. Piper generic baseline

Measure:
- model warmup,
- first PCM latency,
- real-time factor,
- speaker similarity,
- English pronunciation,
- prosody,
- VRAM,
- effect of 1 vs multiple Turkish reference clips.

### Experiment D — full duplex contention

Simultaneously:
- speak Turkish outbound,
- play recorded English inbound,
- synthesize outbound English,
- update overlay.

This test decides whether one shared GPU/model instance is sufficient.

---

## 17. Suggested repository layout

```text
teams-live-translator/
├─ docs/
│  ├─ 00_RESEARCH_PLAN.md
│  ├─ 01_BENCHMARK_RESULTS.md          # create during POC
│  ├─ 02_FINAL_ARCHITECTURE.md         # create after decision
│  └─ 03_AUDIO_ROUTING.md              # exact Teams/VB-CABLE settings later
├─ apps/
│  ├─ realtime_engine/
│  └─ overlay_ui/
├─ services/
│  └─ tts/
├─ benchmarks/
│  ├─ asr/
│  ├─ mt/
│  └─ tts/
├─ voices/
├─ config/
├─ scripts/
├─ tests/
└─ pyproject.toml
```

---

## 18. POC phases

### Phase 0 — environment verification

- Verify PyTorch + CUDA + RTX 5060 Ti.
- Enumerate Windows audio endpoints.
- Install/configure VB-CABLE.
- Capture physical mic and loopback concurrently.
- Play generated test PCM into CABLE Input and verify Teams sees CABLE Output.

**Exit criterion:** reliable full-duplex audio routing with no AI models.

### Phase 1 — incoming subtitles only

`Teams loopback → streaming EN ASR → OPUS EN→TR → overlay`

**Exit criterion:** Turkish partial text appears while the remote sentence is still being spoken.

### Phase 2 — outgoing synthetic generic voice

`Mic → direct TR speech→EN → fast generic TTS → VB-CABLE → Teams`

Use generic TTS first to isolate speech-translation latency from cloning latency.

**Exit criterion:** English audio begins before the Turkish utterance finishes.

### Phase 3 — cloned voice

Add XTTS/CosyVoice profile cache and selectable voice presets.

**Exit criterion:** cloned-English speaker identity is acceptable without breaking the latency target.

### Phase 4 — full-duplex optimization

- bounded queues,
- GPU scheduling,
- chunk policy tuning,
- terminology prompt,
- sample-rate tuning,
- p50/p95 metrics.

### Phase 5 — desktop UX / packaging

Only after the pipeline is stable:
- device dropdowns,
- voice selector,
- default voice,
- overlay/input,
- start/stop button,
- saved profiles,
- optional SQLite,
- single launcher / installer.

---

## 19. Provisional recommendation before benchmarks

If implementation started today, the first baseline would be:

```text
OUTGOING
Physical Mic
  → PyAudioWPatch/WASAPI
  → WhisperLiveKit + SimulStreaming
  → Whisper large-v3-turbo, task=translate, language=tr
  → stable-prefix chunker
  → XTTS-v2 streaming [POC default; compare CosyVoice immediately]
  → 24k/48k stream conversion
  → CABLE Input
  → Teams mic = CABLE Output

INCOMING
Teams speaker endpoint
  → WASAPI loopback
  → WhisperLiveKit, language=en, task=transcribe
  → committed English text
  → Helsinki OPUS-MT tc-big-en-tr via CTranslate2
  → PySide6/web overlay with partial + stable Turkish text
```

**Why this baseline:**
- removes an entire MT model from the latency-critical outbound path,
- uses a modern simultaneous streaming policy instead of fixed multi-second chunks,
- uses a compact dedicated EN→TR model inbound,
- supports cross-language voice cloning,
- keeps Windows audio native,
- can later swap any model behind a narrow interface without rewriting the application.

---

## 20. Main risks / decision gates

1. **TTS licensing** — XTTS is excellent for the POC but its model license is non-commercial.
2. **TTS first-audio latency on RTX 5060 Ti** — published numbers are hardware/configuration dependent.
3. **Direct Whisper TR→EN quality** — must be tested against `TR ASR → OPUS TR→EN` for technical meetings.
4. **Simultaneous interpretation stability** — chunk size must balance latency vs bad irreversible speech.
5. **Full-duplex GPU contention** — 16 GB is sufficient for promising POC candidates, but actual concurrent residency must be measured.
6. **Teams/system audio isolation** — endpoint loopback is easy; Teams-only capture is cleaner with a dedicated device/cable.
7. **Dependency conflicts** — isolate ASR/MT and TTS environments/services if required.
8. **Teams audio processing** — test Teams noise suppression / automatic gain behavior with synthesized virtual-mic audio.

---

## 21. Current decision shortlist

### Keep for POC
- WhisperLiveKit
- SimulStreaming
- Whisper large-v3-turbo
- PyAudioWPatch / WASAPI
- CTranslate2
- Helsinki-NLP OPUS-MT TC-big EN→TR
- XTTS-v2
- CosyVoice2/current CosyVoice
- VB-CABLE
- FastAPI/WebSocket or in-process asyncio
- PySide6 or lightweight web/Tauri overlay

### Reference only
- Mentalese
- LiveLingo
- LiveTranslate
- Seamless Communication
- old WhisperStreaming

### Not needed initially
- Docker for the audio engine
- SQLite before persistent profiles/benchmarks are needed
- MCP in the runtime pipeline
- Ollama in the latency-critical pipeline
- a general-purpose LLM translator for EN↔TR

---

## 22. Source links

- WhisperLiveKit: https://github.com/QuentinFuxa/WhisperLiveKit
- SimulStreaming: https://github.com/ufal/SimulStreaming
- WhisperStreaming (older): https://github.com/ufal/whisper_streaming
- Mentalese: https://github.com/vovaauer/mentalese
- LiveLingo: https://github.com/roirude/LiveLingo
- LiveTranslate: https://github.com/NBS282/LiveTranslate
- PyAudioWPatch: https://github.com/s0d3s/PyAudioWPatch
- VB-CABLE: https://vb-audio.com/Cable/
- Microsoft Teams audio settings: https://support.microsoft.com/en-US/teams/meetings/manage-audio-settings-in-microsoft-teams-meetings
- OPUS-MT TC-big EN→TR: https://huggingface.co/Helsinki-NLP/opus-mt-tc-big-en-tr
- XTTS-v2: https://huggingface.co/coqui/XTTS-v2
- Coqui TTS maintained fork: https://github.com/idiap/coqui-ai-TTS
- CosyVoice: https://github.com/FunAudioLLM/CosyVoice
- OpenVoice: https://github.com/myshell-ai/OpenVoice
- Seamless Communication: https://github.com/facebookresearch/seamless_communication

