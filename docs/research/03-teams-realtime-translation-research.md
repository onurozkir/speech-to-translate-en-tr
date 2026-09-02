# Teams Gerçek Zamanlı Çeviri — Araştırma Akışı ve Karar Kapısı

**Durum:** Araştırma tamamlandı; benchmark ve kullanıcı kararı bekleniyor.
**Tarih:** 2026-09-02
**İlgili mevcut belgeler:** `docs/research/00_RESEARCH_PLAN.md`, `docs/research/01_DECISION_MATRIX.md`, `docs/research/02-teams-realtime-translation-plan.md` (ayrıntılar orada; bu plan yalnızca doğrulanmış bulguları, nihai akışı, paket/repo listesini ve karar kapısını özetler).
**Not:** Bu plan `docs/` klasörüne yazılamadı (izin kuralları yalnız plan klasörlerine yazmaya izin veriyor). İstenirse uygulama aşamasında `docs/research/03_RESEARCH_FLOW_DECISION_GATES.md` olarak kopyalanabilir.

## 1. Bugün doğrulanan bulgular (HF + GitHub canlı kontrol)

| Bileşen | Doğrulama sonucu |
|---|---|
| `nvidia/nemotron-3.5-asr-streaming-0.6b` | Mevcut. 600M, OpenMDW-1.1 (ticari kullanıma açık). `tr-TR` transcription-ready. FLEURS WER tr-TR: 12.34 (80 ms) → 11.17 (1120 ms); en-US: 9.43 → 7.91. Cache-aware streaming, 80/160/320/560/1120 ms chunk. |
| `Qwen/Qwen3-ASR-0.6B` | Mevcut. Apache-2.0. 30 dil + Türkçe. HF open-asr-leaderboard ortalama WER 6.42; streaming modda kalite hafif düşer (ör. Librispeech 2.11 → 2.54). Resmi streaming yolu vLLM'dir (Windows native yok → WSL2). |
| **YENİ:** WhisperLiveKit `qwen3-streaming` backend | WhisperLiveKit, Qwen3-ASR'yi **HF Transformers üzerinden vLLM'siz** native CUDA/CPU/MPS streaming olarak destekliyor (`uv sync --extra qwen3-streaming`). Windowed mod çok dilli; causal mod İngilizce-only. Bu, Qwen3-ASR için **WSL2 zorunluluğunu ortadan kaldırabilecek** native Windows test yolu demektir. Türkçe stream kalitesi yerelde ölçülmeli. |
| `openai/whisper-large-v3-turbo` | Mevcut (MIT). Native streaming değil; SimulStreaming/LocalAgreement sarmalayıcısı gerekir. Olgun geri dönüş adayı. |
| `NVIDIA/NeMo-Speech.cpp` | Mevcut ve resmi. Apache-2.0 kod. **Windows PowerShell kurulum scripti ve CUDA build var.** HTTP + realtime WebSocket server, OpenAI-uyumlu uçlar. Nemotron ASR + Silero VAD + noktalama/büyük-küçük harf + endpointing içerir. Ayrıca TTS (MagpieTTS Multilingual 357M) ve NMT (Riva Translate 4B — 16 GB için ağır) destekler. Not: Nemotron model kartında OS "Linux" yazar; Windows yolu NeMo-Speech.cpp runtime'ıdır. |
| `Helsinki-NLP/opus-mt-tc-big-tr-en` + `en-tr` | Mevcut. CC-BY-4.0. CTranslate2 ile CPU INT8 → düşük gecikme, GPU belleği ASR/TTS'ye kalır. |
| `facebook/nllb-200-distilled-600M` | CC-BY-NC-4.0 → **ticari kullanılamaz**. WhisperLiveKit'in NLLW çeviri backend'i bunu kullanır; ticari senaryoda OPUS-MT ile değiştirilmelidir. |
| `Qwen/Qwen3-TTS-12Hz-0.6B-Base` | Mevcut. Apache-2.0. 10 çıktı dili (İngilizce var, Türkçe yok — çıktı zaten İngilizce olacağı için sorun değil). `generate_voice_clone(ref_audio, ref_text)` ile 3 sn klon. 97 ms sentez iddiası (model içi). Gerçek PCM streaming: vLLM-Omni. **Türkçe referanstan İngilizce klon deneyseldir** — x_vector_only / ICL / kısa İngilizce ref üçlüsü A/B test edilmeli. |
| `FunAudioLLM/Fun-CosyVoice3-0.5B-2512` | Mevcut. Apache-2.0. 9 dil + cross-lingual zero-shot klon. Bi-streaming ~150 ms iddiası. test-en: WER 2.24, speaker similarity 71.8. **Resmi kurulum conda + Python 3.10** → ana ortamdan izole edilmeli; Windows resmi destek yok (WSL2 veya deneysel). |
| `coqui/XTTS-v2` | Mevcut. **CPML — ticari değil.** TR+EN resmi dil; Türkçe referanstan İngilizce klon en güçlü bilinen yol. POC/karşılaştırma için tutulur; ticari üründe varsayılan olamaz. |
| `nvidia/magpie_tts_multilingual_357m` | NeMo-Speech.cpp içinde çalışır; çok hafif düşük gecikmeli fallback adayı. Ses klonlama yeteneği **araştırılacak** (henüz doğrulanmadı). |

**Donanım notu (02'den):** Benchmark öncesi GPU boşaltılmalı — kontrol anında 11.3 GB VRAM dolu, GPU %100 (ComfyUI/Ollama vb. kapatılmalı). `python`/`py` PATH'te yok, `hf` kırık, Docker daemon kapalı, WSL durumu belirsiz → Phase 0 bu zinciri düzeltir.

## 2. Nihai akış

### 2.1 Outgoing: Türkçe mikrofondan → İngilizce sese (Teams mikrofonu)

```text
Fiziksel mic → WASAPI capture (20 ms frame, PyAudioWPatch)
  → Silero VAD → Streaming ASR (tr-TR) → partial/committed state
  → Commit politikası (kararlı 3–8 kelime / noktalama / 250–450 ms sessizlik / max bekleme)
  → OPUS-MT tr-en (CTranslate2 CPU INT8)
  → TTS (seçili profil; varsayılan = klonlanmış ses) → PCM ring buffer
  → CABLE Input (playback) → VB-CABLE → CABLE Output (recording) → Teams mikrofonu
```

### 2.2 Incoming: İngilizce Teams sesinden → Türkçe yazıya (ekranda)

```text
Teams hoparlör → WASAPI device loopback (Seçenek A: tek kablo, MVP)
  → Silero VAD → Streaming ASR (en-US) → partial/committed state
  → OPUS-MT en-tr (CTranslate2 CPU INT8)
  → Overlay/input: partial = gri/değişebilir, committed = kalıcı satır
```

### 2.3 Değişmez kurallar

- **TTS yalnızca committed metin alır.** Çalınan ses geri alınamaz; partial hipotez asla seslendirilmez.
- **Tüm kuyruklar bounded.** Geride kalınırsa: superseded partial düşür, committed koru, commit boyutunu büyüt, metrik yayınla. 10 sn konuşma 10 sn bekletilmez.
- **GPU önceliği:** outgoing (karşı taraf bekliyor) > incoming altyazı > TTS. Tek ASR modeli iki session (tr + en) taşır.
- **Ses/transcript varsayılan olarak diske yazılmaz**; telemetri yalnız süre/sayaç tutar.
- Turkish→English sözcük dizimi farkı nedeniyle birkaç yüz ms + kısa cümlecik "çeviri bakışı" kaçınılmazdır; teknik ayar bunu sıfırlayamaz.

### 2.4 Süreç mimarisi

```text
Python audio bridge (native Windows; WASAPI + VB-CABLE + UI)
  ├─ AudioCapture/Playback worker'ları (lock-free ring buffer)
  ├─ Commit/backpressure state machine
  └─ WebSocket (binary PCM) → model servisleri

Model servisleri (bir veya iki süreç; native CUDA veya WSL2 — benchmark sonrası belli olur)
  ├─ ASR server (Nemotron/NeMo-Speech.cpp | Qwen3/WLK | Whisper fallback)
  ├─ MT worker (CTranslate2 CPU)
  └─ TTS server (Qwen3-TTS/vLLM-Omni | CosyVoice3 | XTTS fallback)

UI: PySide6 (cihaz seçimi, ses profilleri, Türkçe overlay, metrikler)
```

## 3. Paket listesi (ortamlar izole: bridge / ASR+MT / TTS)

| Ortam | Paketler |
|---|---|
| bridge | `PyAudioWPatch`, `numpy`, `soxr`, `pydantic`, `pydantic-settings`, `websockets`, `PySide6`, `psutil`, `nvidia-ml-py`, `soundfile` |
| ASR + MT | `whisperlivekit` (faster-whisper + SimulStreaming + `qwen3-streaming` extra), `qwen-asr[vllm]` (yalnız WSL2 yolu), `NeMo-Speech.cpp` (native CLI/server), `silero-vad`, `ctranslate2`, `sentencepiece`, `transformers` |
| TTS | `qwen-tts` + `vllm-omni` (Linux/WSL2), CosyVoice repo (Python 3.10 conda), `coqui-tts` (XTTS, POC), MagpieTTS (NeMo-Speech.cpp) |
| Geliştirme | `uv`, `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `huggingface_hub`/`hf`, `ffmpeg` (yalnız fixture, canlı yolda değil) |

**Docker:** ses köprüsü native Windows'ta kalır; yalnız model servisleri gerekirse Linux/WSL2 konteynerinde çalışır. Tek komut başlangıç: `start.ps1`.
**SQLite:** MVP'de gerekmez; ses profilleri klasör + `profile.json` manifestiyle taşınır. Gerekirse sonra ayarlar/geçmiş için eklenir.
**MCP:** canlı ses yoluna girmemelidir; yalnız geliştirme/telemetri aracı olarak düşünülebilir.

## 4. GitHub repo listesi

| Repo | Rol | Karar |
|---|---|---|
| https://github.com/QuentinFuxa/WhisperLiveKit | Streaming ASR + simultaneous çeviri çekirdeği; WS server; çoklu backend (Whisper, Qwen3-ASR HF, Canary); `--direct-english-translation` ve NLLW çeviri | **Birincil temel aday** |
| https://github.com/NVIDIA/NeMo-Speech.cpp | Nemotron 3.5 native Windows CUDA runtime; HTTP+WS server; VAD/noktalama/endpointing; MagpieTTS | **POC-1 adayı (native yol)** |
| https://github.com/ufal/SimulStreaming | AlignAtt/stable-prefix simultaneous politika | Algoritma referansı (WLK içinde kullanılır) |
| https://github.com/QwenLM/Qwen3-ASR | Qwen3-ASR paket/servis | POC-2 adayı |
| https://github.com/QwenLM/Qwen3-TTS + vLLM-Omni | TTS + gerçek PCM streaming | TTS POC-1 adayı |
| https://github.com/FunAudioLLM/CosyVoice | CosyVoice3 bi-streaming TTS | TTS POC-2 adayı |
| https://github.com/idiap/coqui-ai-TTS | XTTS-v2 (ticari olmayan lisans) | Kalite referansı |
| https://github.com/s0d3s/PyAudioWPatch | Python WASAPI capture/playback/loopback | Ses köprüsü temeli |
| https://github.com/NBS282/LiveTranslate | Teams + VB-CABLE yönlendirme/UX referansı | Referans; temel değil |
| https://github.com/vovaauer/mentalese | Benzer tam sistem (Whisper+NLLB+Coqui) | Referans; zinciri daha yavaş |
| https://vb-audio.com/Cable/ | Sanal ses aygıtı (driver) | Gerekli kurulum |

## 5. Karar kapısı (kullanıcıya sunulacak)

| Kapı | Adaylar | Ne belirler |
|---|---|---|
| **K1 — Lisans kapsamı** | ✅ **KARAR (2026-09-02): Kişisel kullanım.** | Tüm adaylar masada: XTTS-v2 (CPML) ve NLLB-600M (CC-BY-NC) benchmark'ta kalır. Proje ileride ticari ürüne dönerse lisans manifesti çıkarılıp bu ikisi varsayılandan çıkarılır. |
| K2 — ASR | Nemotron (native) / Qwen3-ASR (WLK-HF native veya vLLM-WSL2) / Whisper turbo | Phase 0: P95 stable latency + tr/en WER + 2 stream + VRAM |
| K3 — MT | OPUS tc-big CPU / küçük OPUS / NLLB referans | CPU latency + insan değerlendirmesi + lisans |
| K4 — TTS | Qwen3-TTS / CosyVoice3 / XTTS | İlk PCM + RTF + Türkçe ref→İngilizce klon benzerliği + lisans |
| K5 — Ses izolasyonu | Tek kablo loopback / çift kablo / per-process capture | Gürültü kirliliği + kurulum kolaylığı |
| K6 — Runtime | Native Windows / WSL2 / karma | Kurulum tekrarlanabilirliği + VRAM + stabilite |

## 6. Phase 0 — benchmark özeti (ayrıntı 02'de)

1. Ortam: Python 3.12 + `uv`, `hf` onarımı, CUDA wheel doğrulama, WSL2 durumu, GPU boşaltma.
2. ASR: Nemotron / Qwen3-ASR / Whisper turbo — aynı tr+en corpus'ta first partial, commit latency, WER/CER, RTF, 2 eşzamanlı stream, VRAM.
3. MT: iki OPUS modeli CPU INT8/beam karşılaştırması.
4. TTS: Qwen3-TTS / CosyVoice3 / XTTS — time-to-first-PCM, RTF, klon benzerliği, Türkçe ref→EN, VRAM.
5. 30 dk iki yönlü sentetik soak testi.
6. Çıktı: K2–K6 tablosu gerçek ölçümlerle kullanıcıya sunulur.

## 7. Açık sorular

- **K1 kapandı:** Kişisel kullanım. K2–K6, Phase 0 benchmark çıktıları kullanıcıya sunulduktan sonra karara bağlanır.

## 8. Sonraki adım (uygulama kapsamı: Phase 0)

Uygulama ajanı için sıralı görev listesi:

1. Ortam onarımı: Python 3.12 + `uv` kurulumu/doğrulama, `python`/`py` PATH düzeltmesi, `hf` CLI onarımı (huggingface_hub), WSL2 durumu tespiti, Docker daemon (yalnız model servisleri için gerekirse).
2. GPU boşaltma: benchmark öncesi ComfyUI/Ollama vb. kapatılır; `nvidia-smi` + `nvcc --version` kaydı.
3. CUDA/PyTorch wheel doğrulaması (Blackwell sm_120; CUDA 12.8/12.9).
4. VB-CABLE kurulumu ve cihaz listeleme (PyAudioWPatch ile mic + loopback + CABLE uçları).
5. Model indirme + lisans manifesti: Nemotron 3.5 q8 GGUF, Qwen3-ASR-0.6B, Whisper large-v3-turbo, OPUS-MT tc-big tr-en/en-tr, Qwen3-TTS-0.6B-Base, Fun-CosyVoice3-0.5B, XTTS-v2.
6. ASR benchmark (tr + en corpus): first partial, commit latency, WER/CER, RTF, 2 eşzamanlı stream, VRAM → K2 tablosu.
7. MT benchmark: OPUS CPU INT8/beam varyantları → K3 tablosu.
8. TTS benchmark: first PCM, RTF, Türkçe ref→EN klon benzerliği, VRAM → K4 tablosu.
9. 30 dk iki yönlü sentetik soak testi (kuyruk büyümesi/underrun).
10. Sonuç raporu: K2–K6 tablosu gerçek ölçümlerle kullanıcıya sunulur; kullanıcı nihai kararı verir → Phase 1 (audio bridge) başlar.

## 9. Kaynaklar

- WhisperLiveKit: https://github.com/QuentinFuxa/WhisperLiveKit
- NeMo-Speech.cpp: https://github.com/NVIDIA/NeMo-Speech.cpp
- Nemotron 3.5 ASR: https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b
- Qwen3-ASR: https://huggingface.co/Qwen/Qwen3-ASR-0.6B
- Qwen3-TTS: https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base
- Fun-CosyVoice3: https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512
- XTTS-v2: https://huggingface.co/coqui/XTTS-v2
- OPUS-MT tr-en: https://huggingface.co/Helsinki-NLP/opus-mt-tc-big-tr-en
- OPUS-MT en-tr: https://huggingface.co/Helsinki-NLP/opus-mt-tc-big-en-tr
- vLLM-Omni Speech API: https://docs.vllm.ai/projects/vllm-omni/en/latest/serving/speech_api/
- PyAudioWPatch: https://github.com/s0d3s/PyAudioWPatch
- VB-CABLE: https://vb-audio.com/Cable/
