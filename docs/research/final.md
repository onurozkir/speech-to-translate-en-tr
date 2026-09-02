# MS Teams Gerçek Zamanlı Çeviri — Nihai Araştırma Analizi

**Tarih:** 2026-09-02  
**Durum:** Mimari öneri tamamlandı; nihai ASR ve TTS modeli Phase 0 yerel benchmark sonucunda seçilecek  
**Hedef sistem:** Windows 11, NVIDIA GeForce RTX 5060 Ti 16 GB, 32 GB RAM, Python 3.12

## 1. Yönetici özeti

Altı araştırmanın ortak sonucu, hedef sistemin yerel ve büyük ölçüde açık modellerle yapılabilir olduğudur. En güçlü yaklaşım, Windows ses katmanını model inference katmanından ayıran modüler bir mimaridir:

- Native Windows audio bridge ve masaüstü UI.
- Mikrofon, WASAPI loopback ve VB-CABLE erişimi için `PyAudioWPatch`.
- Değiştirilebilir ASR, MT ve TTS adapter'ları.
- Her iki çeviri yönünde CPU üzerinde `OPUS-MT + CTranslate2`.
- Tek VB-CABLE + WASAPI loopback ile hızlı MVP.
- Teams-only ses izolasyonu gerekirse ikinci sanal kablo veya process loopback.
- Qwen3-TTS gibi Linux gerektiren model servisleri için gerektiği kadar WSL2/Docker.
- SQLite, MCP ve Ollama'nın canlı audio yolundan çıkarılması.

Uzun vadeli mimari için [02-teams-realtime-translation-plan.md](./02-teams-realtime-translation-plan.md) en güçlü temel belgedir. [03-teams-realtime-translation-research.md](./03-teams-realtime-translation-research.md) güncel model ve runtime eki, [00_RESEARCH_PLAN.md](./00_RESEARCH_PLAN.md) benchmark metodolojisi, [01_DECISION_MATRIX.md](./01_DECISION_MATRIX.md) ise ölçüm sonuç formu olarak kullanılmalıdır.

En kolay demo ile en iyi uzun vadeli mimari aynı değildir:

- En hızlı demo: WhisperLiveKit + hazır TTS servisi.
- En yüksek latency potansiyeli: gerçek streaming ASR + OPUS-MT + gerçek PCM streaming TTS.
- En güvenli ses klonlama POC'u: XTTS-v2; ancak ticari olmayan model lisansı vardır.
- En güçlü açık lisanslı TTS hedefi: Qwen3-TTS; fakat Türkçe referanstan İngilizce klon kalitesi ölçülmelidir.

## 2. Değişmez proje hedefleri

Sistem iki bağımsız ve eşzamanlı akış çalıştırmalıdır.

### 2.1 Outgoing: Türkçe mikrofon → İngilizce ses

1. Fiziksel mikrofondan Türkçe ses alınır.
2. Streaming ASR geçici ve kararlı Türkçe metin üretir.
3. Yalnız kararlı metin İngilizceye çevrilir.
4. İngilizce metin seçili veya klonlanmış ses profiliyle sentezlenir.
5. PCM parçaları VB-CABLE'a sürekli yazılır.
6. Teams, `CABLE Output` aygıtını mikrofon olarak kullanır.

On saniyelik konuşmanın tamamı beklenmemelidir. Kararlı kısa anlam parçaları hazır oldukça çevrilip seslendirilmelidir.

### 2.2 Incoming: İngilizce Teams sesi → Türkçe yazı

1. Teams hoparlör akışı WASAPI loopback veya ikinci sanal kablo ile yakalanır.
2. Streaming ASR İngilizce partial/committed sonuçlar üretir.
3. Metin Türkçeye çevrilir.
4. Partial çeviri arayüzde değiştirilebilir, committed çeviri kalıcı gösterilir.

### 2.3 Genel hedefler

- Minimum uçtan uca latency.
- Uzun konuşmada büyümeyen kuyruk.
- Full-duplex çalışma.
- Tamamen yerel işleme ve varsayılan olarak kayıt tutmama.
- Çoklu ses profili ve klonlanmış sesin default seçilebilmesi.
- Tek komutla çalıştırılabilen tekrarlanabilir kurulum.
- Model ve runtime'ın dar adapter arayüzleriyle değiştirilebilmesi.

## 3. Araştırma belgelerinin değerlendirmesi

Puanlama; teknik doğruluk, latency gerçekçiliği, entegrasyon uygulanabilirliği, lisans/risk farkındalığı ve karar faydasına göre yapılmıştır.

| Belge | Puan | Güçlü yön | Zayıf yön |
|---|---:|---|---|
| [02 — Teknik plan](./02-teams-realtime-translation-plan.md) | **9,3/10** | True streaming ayrımı, commit/backpressure, ortam kontrolü, lisanslar ve ölçüm kapısı | Nihai model kararı doğal olarak benchmark'a bırakılmış |
| [03 — Güncel araştırma](./03-teams-realtime-translation-research.md) | **8,9/10** | Güncel Nemotron, Qwen, WhisperLiveKit ve TTS yolları | Birkaç eski not ve scheduler önceliği belirsizliği |
| [00 — POC planı](./00_RESEARCH_PLAN.md) | **8,8/10** | Stable/partial ayrımı, no-backlog, aşamalı POC ve ölçüm yöntemi | Model kısa listesi 02/03'e göre daha eski |
| [05 — WLK/Chatterbox araştırması](./05-ms-teams-realtime-ceviri-arastirma-ve-mimari.md) | **7,4/10** | Hazır servisler, Docker/native sınırı ve kolay demo planı | Chatterbox streaming ve iki WLK servisinin maliyeti fazla iyimser |
| [01 — Decision matrix](./01_DECISION_MATRIX.md) | **6,5/10** | Doğru ölçüm başlıkları ve seçim kuralları | Henüz boş; entegrasyon, audio topology ve weighted score eksik |
| [04 — Google araştırması](./04-teams-research-with-google.md) | **5,6/10** | Veri akışı ve semantic chunking fikri | Ölçülmemiş kesin rakamlar, kurulum tutarsızlıkları ve eksik lisans analizi |

Önerilen belge sahipliği:

- `02`: canonical mimari ve kabul kriterleri.
- `03`: güncel model/runtime kataloğu.
- `01`: gerçek benchmark sonuçları.
- `00`, `04`, `05`: araştırma girdileri ve alternatif yaklaşımlar.
- `final.md`: nihai sentez ve uygulama yönü.

## 4. Mimari alternatiflerin puanı

Ağırlıklar:

- Latency potansiyeli: %25.
- Türkçe/İngilizce ve ses klonlama kalite uyumu: %20.
- Entegrasyon kolaylığı: %15.
- Operasyonel kararlılık: %15.
- Lisans ve local-first uygunluğu: %10.
- RTX 5060 Ti 16 GB uyumu: %10.
- Değiştirilebilirlik: %5.

Entegrasyon zorluğu ölçeğinde `1=kolay`, `5=zor`.

| Mimari | Zorluk | Latency | Kalite | Kolaylık | Toplam |
|---|---:|---:|---:|---:|---:|
| **Önerilen birleşik modüler mimari** | 4/5 | 9/10 | 8,5/10 | 6/10 | **82/100** |
| `00`: WLK + direct Whisper + OPUS + XTTS | 3/5 | 7,5/10 | 8/10 | 8/10 | **75/100** |
| `05`: WLK + NLLW + Chatterbox Docker | 3/5 | 6,5/10 | 8/10 | 8,5/10 | **72/100** |
| `04`: fixed chunk faster-whisper + NLLB + XTTS | 4/5 gerçek efor | 5,5/10 | 8/10 | 6/10 | **61/100** |

`05` hızlı demonstrasyon için güçlüdür. Önerilen birleşik mimari daha zor olmasına rağmen minimum latency, bakım, lisans ve model değiştirme açısından daha güçlüdür.

## 5. Nihai önerilen mimari

```text
Native Windows Python 3.12
├─ PyAudioWPatch / WASAPI
├─ Physical microphone capture
├─ Teams speaker loopback
├─ VB-CABLE playback
├─ 10–20 ms bounded PCM ring buffers
├─ resampling
├─ commit/backpressure state machine
└─ PySide6 overlay + device/voice controls

Model katmanı
├─ ASR server
│  ├─ Nemotron 3.5 / NeMo-Speech.cpp
│  ├─ WhisperLiveKit + Qwen3-ASR
│  └─ WhisperLiveKit + Whisper turbo fallback
├─ OPUS-MT tr-en + en-tr / CTranslate2 CPU
└─ TTS server
   ├─ Qwen3-TTS / vLLM-Omni
   ├─ XTTS-v2 personal fallback
   └─ CosyVoice/Chatterbox benchmark alternatives
```

### 5.1 Outgoing akış

```text
Physical microphone
  → WASAPI capture
  → VAD
  → Streaming ASR tr-TR
  → Partial/committed state
  → Semantic stable commit
  → OPUS-MT tr-en / CTranslate2 CPU
  → Cloned TTS PCM stream
  → Bounded playback queue
  → CABLE Input
  → CABLE Output
  → Teams microphone
```

### 5.2 Incoming akış

```text
Teams speaker
  → WASAPI device loopback
  → VAD
  → Streaming ASR en-US
  → Partial/committed state
  → OPUS-MT en-tr / CTranslate2 CPU
  → Partial/stable Turkish overlay
```

### 5.3 Neden iki yönde de ayrı OPUS-MT?

Whisper'ın direct English translation özelliği outgoing MT aşamasını kaldırabilir ve benchmark adayı olarak tutulmalıdır. Canonical zincirde ayrı OPUS-MT önerilmesinin nedenleri:

- Aynı ASR model ağırlıkları iki bağımsız session arasında paylaşılabilir.
- Türkçe transcript ayrıca elde edilir.
- Terminoloji ve glossary daha kontrollüdür.
- ASR ve MT bağımsız değiştirilebilir.
- Translation stability ayrıca ölçülebilir.
- Mimari Whisper'a bağlanmaz.
- Ek MT gecikmesi CPU üzerinde küçük ve ölçülebilirdir.

Direct Whisper, gerçek donanımda belirgin latency avantajı ve yeterli teknik çeviri kalitesi gösterirse outgoing fast path olabilir.

## 6. Streaming ve commit kuralları

### 6.1 Partial ve committed durumları

- `partial`: Değiştirilebilir ASR/MT hipotezi. Incoming UI'da gösterilebilir, eski hipotez geldiğinde düşürülebilir.
- `committed`: İki ardışık hipotezde aynı kalan veya endpoint ile kapanan append-only metin.
- TTS yalnız `committed` metin alır.

Çalınmış ses geri alınamayacağı için partial metnin seslendirilmesi yasaktır.

### 6.2 Başlangıç commit politikası

Commit kararı şu sinyalleri birlikte kullanmalıdır:

- Stable-prefix sonucu.
- Noktalama veya anlamsal kısa cümlecik sınırı.
- 250–450 ms sessizlik.
- Maksimum bekleme süresi.
- Minimum 3–8 kelime/uygun karakter sayısı.
- Kuyruk doluluğu.
- TTS real-time factor.

Türkçe SOV ve İngilizce SVO sözcük dizimi nedeniyle sıfır dilsel bekleme mümkün değildir. Ana gecikme yalnız model inference değil, kararlı anlam parçasının oluşma süresidir.

### 6.3 Backpressure

- Bütün kuyruklar bounded olmalıdır.
- Superseded partial işler düşürülebilir.
- Committed parçalar sessizce düşürülemez veya yeniden sıralanamaz.
- TTS gerçek zamandan geri kalırsa commit boyutu dinamik artırılmalıdır.
- Kuyruk canlı akıştan uzaklaşıyorsa metrik ve UI uyarısı üretilmelidir.
- Toplantı başlamadan bütün modeller ısıtılmalıdır.

## 7. Audio routing kararı

### 7.1 MVP: tek VB-CABLE + WASAPI loopback

- Uygulama TTS PCM'ini `CABLE Input`a yazar.
- Teams mikrofon olarak `CABLE Output` kullanır.
- Teams hoparlörü fiziksel kulaklık olarak kalır.
- Uygulama kulaklığın WASAPI loopback akışını yakalar.

Avantajları:

- En kolay kurulum.
- Tek sanal kablo.
- Kullanıcı incoming sesi normal kulaklıktan duyar.

Dezavantajı:

- Aynı Windows çıkışındaki bildirim, müzik ve diğer uygulama sesleri de ASR'ye girebilir.

### 7.2 İkinci aşama: çift sanal kablo

- Cable A outgoing Teams mikrofonu için.
- Cable B incoming Teams hoparlörü için.
- Uygulama Cable B sesini fiziksel kulaklığa mirror eder.

Teams sesi daha iyi izole edilir; ek routing, buffer ve device lifecycle maliyeti oluşur.

### 7.3 Production izolasyonu: process loopback

Windows ApplicationLoopback ile yalnız Teams süreç ağacı yakalanabilir. En temiz yol olmakla birlikte native C++ helper veya güvenilir bir addon gerektirir. MVP için ertelenmelidir.

## 8. Bileşen değerlendirmesi

### 8.1 Audio ve UI

| Bileşen | Uygunluk | Zorluk | Karar |
|---|---:|---:|---|
| `PyAudioWPatch + VB-CABLE` | **9/10** | 2/5 | MVP temeli |
| Çift VB-CABLE | 8/10 | 3/5 | İzolasyon gerekirse |
| Process Loopback | 8,5/10 | 5/5 | Production optimizasyonu |
| PySide6 overlay | 9/10 | 2/5 | Önerilen UI |
| WLK web UI | 7/10 | 1/5 | İlk smoke test |
| Odaklanan input'a otomatik yazma | 4/10 | 3/5 | Kırılgan; varsayılan yapılmamalı |

### 8.2 ASR

| Aday | Uygunluk | Zorluk | Avantaj | Risk |
|---|---:|---:|---|---|
| Nemotron 3.5 + NeMo-Speech.cpp | **8,8/10** | 3/5 | Gerçek streaming, küçük model, native Windows CUDA | Runtime/model yeni; OpenMDW lisansı |
| WLK `qwen3-streaming` | 8,5/10 | 3/5 | Native HF/Windows test yolu, stable-prefix hazır | Bounded recompute; resmi vLLM streaming yolu değil |
| WLK + Whisper turbo | 8/10 | 2/5 | En olgun ve en kolay bring-up | Whisper native streaming değil |
| Qwen3-ASR + vLLM | 8/10 | 4/5 | Resmi streaming, Apache-2.0 | WSL2/Linux operasyonu |

Phase 0'da aynı corpus ve aynı iki-stream yükü altında karşılaştırılmadan nihai ASR seçilmemelidir.

### 8.3 Makine çevirisi

| Aday | Uygunluk | Zorluk | Karar |
|---|---:|---:|---|
| OPUS-MT tc-big + CTranslate2 CPU INT8 | **9,2/10** | 2/5 | Varsayılan iki yönlü MT |
| Whisper direct translation | 7,8/10 | 2/5 | Outgoing latency benchmark adayı |
| NLLW/NLLB | 7,2/10 kişisel | 3/5 | Kalite referansı; varsayılan değil |
| Genel amaçlı LLM/Ollama | 4/10 hot path | 2/5 | Canlı yolda kullanılmamalı |

NLLB/NLLW, CC-BY-NC-4.0 nedeniyle ticari üründe varsayılan olamaz. OPUS-MT daha küçük, daha kontrollü ve ticari açıdan daha güvenli bir başlangıçtır.

### 8.4 TTS ve ses klonlama

| Aday | Uygunluk | Zorluk | Avantaj | Risk |
|---|---:|---:|---|---|
| Qwen3-TTS 0.6B + vLLM-Omni | **8,5/10** | 5/5 | Apache-2.0, gerçek PCM streaming | WSL/Linux; Türkçe referans deneysel |
| XTTS-v2 | 8,3/10 kişisel | 3/5 | TR ve EN resmi dil; klon başarı olasılığı yüksek | CPML; ticari kullanım yok |
| CosyVoice3 | 7,5/10 | 5/5 | Apache-2.0, bi-streaming | Python 3.10/conda/WSL; Türkçe referans belirsiz |
| Chatterbox | 6,8/10 latency | 2–3/5 | MIT, Türkçe, hazır server/UI | Gerçek token/PCM streaming değil |
| Piper/generic TTS | 7/10 POC | 1/5 | Çok hızlı pipeline doğrulaması | Voice clone yok |

Chatterbox-TTS-Server'ın `stream:true` özelliği, bir text chunk'ını tam forward pass ile sentezledikten sonra gönderir. Kısa input tek chunk ise streaming faydası yoktur. Kaynak: [Chatterbox-TTS-Server documentation](https://github.com/devnen/Chatterbox-TTS-Server/blob/main/documentation.md).

Qwen3-TTS, vLLM-Omni ile Code2Wav pencereleri hazır oldukça gerçek PCM chunk döndürebilir. Kaynak: [vLLM-Omni Text-to-Speech](https://docs.vllm.ai/projects/vllm-omni/en/latest/user_guide/examples/online_serving/text_to_speech/).

## 9. Ses profili tasarımı

MVP'de SQLite gerekli değildir. Ses profilleri klasör + manifest ile taşınmalıdır:

```text
voices/
  onur-default/
    reference.wav
    profile.json
    cache/
```

Örnek manifest:

```json
{
  "id": "onur-default",
  "display_name": "Onur - Default",
  "backend": "qwen3-tts-0.6b-base",
  "reference_audio": "reference.wav",
  "reference_text": "Reference recording transcript",
  "reference_language": "Turkish",
  "target_language": "English",
  "x_vector_only": false,
  "is_default": true,
  "consent_recorded_at": "2026-09-02T00:00:00+03:00"
}
```

Kurallar:

- Referans ses temiz, tek konuşmacı ve yankısız olmalıdır.
- 3, 10 ve 30 saniyelik referanslar benchmark edilmelidir.
- Speaker conditioning/prompt uygulama başlangıcında hesaplanıp cache'lenmelidir.
- Birden fazla profil UI'dan seçilebilir olmalıdır.
- Yalnız bir profil `is_default=true` taşımalıdır.
- Yalnız kullanıcının kendi veya açık izinli sesi klonlanmalıdır.

Qwen3-TTS için üç yol A/B test edilmelidir:

1. Türkçe referansla `x_vector_only_mode=true`.
2. Türkçe referans + doğru transcript ile ICL.
3. Aynı kullanıcının kısa İngilizce referansı + transcript ile ICL.

XTTS-v2, Türkçe referanstan İngilizce klonlama için kalite kontrol modeli olarak tutulmalıdır.

## 10. Runtime ve deployment kararı

### 10.1 Native Windows'ta kalacaklar

- Audio capture ve playback.
- WASAPI loopback.
- VB-CABLE output.
- Ring buffer ve resampling.
- Commit/backpressure orchestration.
- Desktop UI ve overlay.

### 10.2 Ayrı model servisi olabilecekler

- ASR server.
- TTS server.
- Dependency çatışması varsa MT worker.

### 10.3 Docker/WSL kullanımı

- Windows audio yolu Docker'a alınmamalıdır.
- Qwen3-TTS/vLLM-Omni gibi Linux gerektiren servisler WSL2 veya Docker içinde çalışabilir.
- Native çalışan model için sırf standartlaştırma amacıyla Docker zorunlu tutulmamalıdır.
- Her model/repo revision ile pinlenmelidir.
- `start.ps1`, sağlık kontrolleri ve warm-up tamamlanmadan UI'yı hazır göstermemelidir.

### 10.4 MCP, SQLite ve Ollama

- MCP canlı audio yoluna girmemelidir.
- SQLite yalnız kalıcı ayarlar veya kullanıcı isterse transcript geçmişi için sonradan eklenmelidir.
- Ollama canlı MT yoluna girmemelidir.
- Ollama yalnız committed metinde, ana akışı bloklamayan opsiyonel post-processing için düşünülebilir.

## 11. Scheduler ve öncelikler

Statik `outgoing > incoming > TTS` sırası doğru değildir; TTS outgoing teslimatın parçasıdır. Öncelik, stage adı yerine bir sonraki audio deadline'a göre verilmelidir:

1. Audio callback ve render deadline.
2. Sıradaki outgoing committed chunk'ın ASR/MT/TTS işi.
3. Incoming stable subtitle.
4. Incoming partial subtitle.
5. Profil cache, log ve arka plan işleri.

Tek ASR modelinin iki bağımsız session taşıması tercih edilmelidir:

- Session A: `tr-TR`, fiziksel mikrofon.
- Session B: `en-US`, Teams incoming.

İki ayrı WhisperLiveKit container aynı model ağırlığını ve CUDA context'ini çoğaltabilir. Runtime izin veriyorsa ağırlıklar tek model server içinde paylaşılmalıdır. İzin vermiyorsa ikinci incoming modelin daha küçük bir varyant olması benchmark edilmelidir.

## 12. Latency hedefleri ve telemetri

### 12.1 Kabul hedefleri

| Ölçüm | P50 | P95 |
|---|---:|---:|
| İngilizce ses → ilk Türkçe partial | ≤0,8 sn | ≤1,5 sn |
| İngilizce ses → stable Türkçe | ≤1,5 sn | ≤2,5 sn |
| Türkçe ses → ilk İngilizce PCM | ≤1,5 sn | ≤2,5 sn |
| 30 dakika full-duplex | Backlog yok | Underrun yok |

`150–200 ms` tam sistem hedefi gerçekçi değildir. Bu sayılar genellikle yalnız modelin sentez veya bir inference aşamasını ölçer. ASR stability, dilsel commit, MT, TTS ve Windows audio toplamı değildir.

### 12.2 Kaydedilecek zaman damgaları

- `audio_captured_at`
- `vad_started_at`
- `asr_first_partial_at`
- `asr_committed_at`
- `mt_completed_at`
- `tts_request_at`
- `tts_first_pcm_at`
- `cable_write_at`
- `ui_partial_at`
- `ui_committed_at`

Ek metrikler:

- ASR/TTS real-time factor.
- Queue depth.
- Dropped/superseded partial sayısı.
- Buffer underrun/overrun.
- GPU VRAM ve utilization.
- CPU utilization.
- Device reconnect sayısı.

Varsayılan olarak ham ses ve transcript diske yazılmamalıdır.

## 13. Entegrasyon zorluğu sıralaması

En zor problemler model indirmek değildir:

| Problem | Zorluk | Etki |
|---|---:|---|
| Semantic commit ve irreversible TTS | 5/5 | Doğrudan kalite/latency |
| Full-duplex GPU scheduling/backpressure | 5/5 | Backlog ve kesinti |
| Türkçe referans → İngilizce ses kimliği | 4/5 | Ana ürün hedefi |
| Blackwell/CUDA/Python uyumu | 4/5 | Kurulum ve stabilite |
| Teams-only process capture | 5/5 production | Ses izolasyonu |
| Tek VB-CABLE audio MVP | 2/5 | Hızlı doğrulama |
| OPUS-MT entegrasyonu | 2/5 | Düşük risk |
| Overlay/UI | 2/5 | Görece kolay |

## 14. Phase 0 benchmark kapısı

Nihai model kartı iddialarıyla değil, hedef bilgisayardaki ölçümlerle seçilmelidir.

### 14.1 Ortam hazırlığı

1. Python 3.12 ve `uv` doğrulama.
2. Kırık `hf` CLI/Python PATH onarımı.
3. CUDA Toolkit ve PyTorch Blackwell `sm_120` uyumluluğu.
4. WSL2 ve Docker durumunun doğrulanması.
5. Benchmark sırasında ComfyUI/Ollama ve diğer GPU işlerinin kapatılması.
6. Model revision ve lisans manifesti.

### 14.2 ASR benchmark

Aynı Türkçe ve İngilizce corpus ile:

- Nemotron 3.5 / NeMo-Speech.cpp.
- WLK `qwen3-streaming`.
- Qwen3-ASR/vLLM resmi yol.
- WLK + Whisper large-v3-turbo.

Ölçüler:

- First partial latency.
- First committed latency.
- WER/CER.
- Teknik terim doğruluğu.
- İki eşzamanlı stream.
- RTF ve VRAM.

### 14.3 MT benchmark

- OPUS tc-big CPU INT8, beam 1 ve beam 2.
- Daha küçük OPUS modeli.
- NLLB kişisel kalite referansı.
- Outgoing direct Whisper translation.

Ölçüler:

- 5/10/20 kelimelik prefix latency.
- Commit stability.
- Teknik terminoloji.
- İnsan değerlendirmesi.

### 14.4 TTS benchmark

- Qwen3-TTS 0.6B Base / vLLM-Omni.
- XTTS-v2.
- CosyVoice3.
- Chatterbox Multilingual/Turbo.
- Piper generic latency baseline.

Ölçüler:

- Time-to-first-PCM.
- Uzun üretimde RTF.
- Türkçe referans → İngilizce speaker similarity.
- İngilizce telaffuz ve anlaşılabilirlik.
- Prosody ve parça birleşim kalitesi.
- VRAM.
- 3/10/30 saniyelik referans etkisi.

### 14.5 Full-duplex soak testi

- Aynı anda Türkçe outgoing konuşma.
- Kayıtlı İngilizce incoming konuşma.
- TTS playback.
- UI partial/stable güncelleme.
- 30 dakika kesintisiz çalışma.

Hard gate:

- Kuyruk sürekli büyümemeli.
- Audio underrun olmamalı.
- P95 hedefleri aşılmamalı.
- Committed metin sırası bozulmamalı.

## 15. Uygulama sırası

### Phase 0 — ortam ve benchmark

Runtime ve model kısa listesini gerçek ölçümlerle daralt.

### Phase 1 — modelden bağımsız audio bridge

1. Device enumeration ve stable device ID.
2. Fiziksel mic capture.
3. WASAPI loopback capture.
4. Test PCM → `CABLE Input` playback.
5. Ring buffer/resampler.
6. Teams test call.

### Phase 2 — incoming altyazı

```text
Teams loopback → ASR → OPUS en-tr → PySide6 overlay
```

### Phase 3 — outgoing generic voice

```text
Mic → ASR → OPUS tr-en → Piper/generic TTS → VB-CABLE
```

Bu aşama, voice cloning riskini pipeline latency riskinden ayırır.

### Phase 4 — voice cloning

Qwen3-TTS, XTTS, CosyVoice ve Chatterbox adapter'ları; çoklu profil ve default seçim.

### Phase 5 — full-duplex optimizasyon

Bounded queues, deadline-aware scheduling, dynamic commit policy ve telemetry tuning.

### Phase 6 — ürünleştirme

Process loopback/çift cable, installer, `start.ps1`, crash recovery, device reconnect ve opsiyonel persistence.

## 16. Bugün kodlamaya başlanırsa

En güvenli bring-up stack:

```text
PyAudioWPatch + VB-CABLE
WhisperLiveKit + Whisper large-v3-turbo
OPUS-MT + CTranslate2 CPU
Piper generic TTS
PySide6 overlay
```

Bu seçim nihai performans yığını değildir. Ama audio routing, commit state ve full-duplex orchestration'ı en az model riskiyle doğrular.

Benchmark sonunda hedef stack büyük olasılıkla şu aileden seçilecektir:

```text
ASR: Nemotron 3.5 veya Qwen3-ASR
MT: OPUS-MT iki yön / CTranslate2 CPU
TTS: Qwen3-TTS gerçek PCM streaming
Voice-quality fallback: XTTS-v2, kişisel kullanım
Audio/UI: Native Windows Python + PyAudioWPatch + PySide6
Runtime: Native Windows + gerektiği kadar WSL2 model servisi
```

## 17. Ana riskler ve azaltma yolları

| Risk | Etki | Azaltma |
|---|---|---|
| Türkçe cümle sonu bekleme | Outgoing latency | Stable-prefix, semantic clause commit, maksimum bekleme |
| Partial metnin seslendirilmesi | Geri alınamaz yanlış ses | TTS yalnız committed metin alır |
| TTS RTF ≥1 | Kuyruk büyümesi | Küçük model, warm-up, bounded queue, adaptive chunk |
| Türkçe ref ile Qwen klon zayıf | Kimlik kaybı | x-vector/ICL/EN ref A/B; XTTS fallback |
| İki ASR servisi aynı ağırlığı yükler | VRAM israfı | Shared model/session veya küçük incoming model |
| Loopback başka sesleri yakalar | Yanlış transcript | Dedicated endpoint, çift cable veya process loopback |
| Teams noise suppression/AGC | Kesik/robotik TTS | Fixed level ve suppression A/B testi |
| RTX 50 dependency uyumsuzluğu | Kurulum bozulur | Compatibility matrix ve revision pin |
| Non-commercial model lisansı | Ürünleşme engeli | NLLB/XTTS'yi varsayılandan çıkar; OPUS/Qwen seç |
| Transcript gizliliği | KVKK/şirket riski | Persistence off, localhost-only, redacted telemetry |

## 18. Nihai karar

Mimari kararı verilmiştir:

1. Windows audio ve UI native kalacak.
2. Model katmanı dar adapter'larla değiştirilebilir olacak.
3. Her iki yön için canonical MT, OPUS-MT/CTranslate2 CPU olacak.
4. Tek VB-CABLE + WASAPI loopback MVP'de kullanılacak.
5. Partial/committed ayrımı, bounded queue ve deadline-aware scheduling zorunlu olacak.
6. Docker/WSL yalnız gerekli model servislerinde kullanılacak.
7. SQLite, MCP ve Ollama canlı audio yoluna girmeyecek.
8. Nihai ASR ve TTS modeli Phase 0 benchmark sonucunda seçilecek.

Model seçimindeki öncelik sırası:

1. P95 latency ve backlog davranışı.
2. Türkçe/İngilizce kalite eşiği.
3. Voice similarity ve anlaşılabilirlik.
4. Operasyonel stabilite.
5. Lisans.
6. VRAM/RAM kullanımı.

Kalite eşiğini geçen en küçük ve en hızlı model seçilmelidir. Model kartı rakamları nihai seçim için yeterli değildir.

## 19. Başlıca dış kaynaklar

- [WhisperLiveKit](https://github.com/QuentinFuxa/WhisperLiveKit)
- [NeMo-Speech.cpp](https://github.com/NVIDIA/NeMo-Speech.cpp)
- [Nemotron 3.5 ASR Streaming](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b)
- [Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR)
- [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS)
- [vLLM-Omni Text-to-Speech](https://docs.vllm.ai/projects/vllm-omni/en/latest/user_guide/examples/online_serving/text_to_speech/)
- [CTranslate2 Transformers guide](https://opennmt.net/CTranslate2/guides/transformers.html)
- [OPUS-MT tr-en](https://huggingface.co/Helsinki-NLP/opus-mt-tc-big-tr-en)
- [OPUS-MT en-tr](https://huggingface.co/Helsinki-NLP/opus-mt-tc-big-en-tr)
- [CosyVoice](https://github.com/FunAudioLLM/CosyVoice)
- [XTTS-v2](https://huggingface.co/coqui/XTTS-v2)
- [Chatterbox](https://github.com/resemble-ai/chatterbox)
- [Chatterbox-TTS-Server](https://github.com/devnen/Chatterbox-TTS-Server)
- [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch)
- [VB-CABLE](https://vb-audio.com/Cable/)
- [Microsoft WASAPI loopback recording](https://learn.microsoft.com/en-us/windows/win32/coreaudio/loopback-recording)
- [Microsoft ApplicationLoopback sample](https://github.com/microsoft/Windows-classic-samples/tree/main/Samples/ApplicationLoopback)

