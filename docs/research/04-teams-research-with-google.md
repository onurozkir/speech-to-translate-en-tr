# MS Teams İki Yönlü Gerçek Zamanlı Simültane Çeviri ve Ses Klonlama Sistemi
## Kapsamlı Araştırma, Sistem Mimarisi ve Teknik Analiz Dokümanı

---

## 1. Yönetici Özeti ve Proje Hedefleri

Bu doküman, Microsoft Teams toplantılarında **minimum gecikme (ultra-low latency)** ile çalışacak çift yönlü bir simültane çeviri ve ses klonlama sisteminin teknik mimarisini, model seçimlerini, donanım kaynak yönetimini ve uygulama planını detaylandırmaktadır.

### Temel Hedefler:
1. **İletim (TX - Kullanıcı $\to$ Teams):** Kullanıcı fiziksel mikrofondan **Türkçe** konuştuğunda, ses CPU/GPU darboğazına uğramadan mikro-öbekler (streaming chunks) halinde yakalanacak, İngilizceye çevrilecek ve kullanıcının kendi ses karakteristiğini taşıyan bir **İngilizce yapay ses** ile sentezlenerek **VB-Cable** üzerinden MS Teams'e mikrofon girdisi olarak gönderilecektir. Karşı taraf 10 saniyelik bir konuşma için 10 saniye beklemeyecek; konuşma başladıktan ~1.5 - 1.8 saniye sonra ilk cümleleri duymaya başlayacaktır.
2. **Alım (RX - Teams $\to$ Ekrana Canlı Altyazı):** Toplantıdaki yabancı katılımcı **İngilizce** konuştuğunda, kulaklığa gelen ses Windows WASAPI Loopback ile arka planda yakalanacak, İngilizce STT ile deşifre edilip Türkçeye çevrilecek ve ekranda her zaman üstte duran (Always-on-Top) şeffaf bir metin kutusuna/arayüze anlık (streaming) olarak basılacaktır.
3. **Kişiselleştirilmiş Ses Klonlama:** Kullanıcının 6-10 saniyelik temiz Türkçe ses kaydından çıkarılan biyometrik ses özellikleri (speaker embeddings) kullanılarak, İngilizce çıktının kullanıcının kendi sesiyle konuşması sağlanacaktır. İhtiyaç anında farklı ses profilleri (kurumsal, samimi, alternatif konuşmacılar) arasında geçiş yapılabilecektir.
4. **Maksimum Açık Kaynak ve Yerellik:** Veri gizliliği, sıfır API maliyeti ve minimum ağ gecikmesi için tüm pipeline yerel donanımda (RTX 5060 Ti 16 GB VRAM) çalışacaktır.

---

## 2. Donanım Özellikleri ve Kaynak (VRAM/RAM) Bütçesi

### Sistem Profili
* **GPU:** NVIDIA GeForce RTX 5060 Ti (16 GB GDDR7 VRAM, Blackwell Mimarisi)
* **RAM:** 32 GB DDR5
* **Yazılım Ortamı:** Python 3.12, CUDA 12.8, PyTorch 2.4+ (cu128), Ollama (Opsiyonel/Harici)

### VRAM & Bellek Dağılım Bütçesi
Aynı anda çalışacak modellerin GPU bellek ayak izi:

| Bileşen / Model | Seçilen Model & Format | VRAM Kullanımı | Çıkarım Gecikmesi (Inference) |
| :--- | :--- | :--- | :--- |
| **VAD (Voice Activity Detection)** | Silero VAD v5 (ONNX / Torch) | ~120 MB | 5 - 10 ms |
| **STT (Türkçe TX & İngilizce RX)** | Faster-Whisper `large-v3-turbo` (int8_float16) | ~2.1 GB | 80 - 130 ms (öbek başı) |
| **NMT (TR $\leftrightarrow$ EN Çeviri)** | CTranslate2 `nllb-200-distilled-600M` (int8) | ~750 MB | 15 - 30 ms |
| **TTS & Voice Clone (İngilizce)** | Coqui XTTS-v2 Streaming (fp16) | ~3.4 GB | 150 - 200 ms (ilk chunk) |
| **CUDA Context & PyTorch Overhead** | Bellek havuzu & ara tensörler | ~1.2 GB | - |
| **TOPLAM VRAM TÜKETİMİ** | **Tüm Pipeline Aktif Halde** | **~7.6 GB** | **Boş Kalan: ~8.4 GB** |

> **Analiz Sonucu:** RTX 5060 Ti üzerindeki 16 GB VRAM, modellerin aynı anda GPU'da sıcak (hot-loaded) tutulması için fazlasıyla yeterlidir. Kalan ~8.4 GB VRAM payı, CUDA bellek parçalanması (fragmentation) veya gelecekte eklenebilecek daha büyük TTS modelleri (örn. CosyVoice 2 / F5-TTS) için güvenli bir tampon bölge oluşturur.

---

## 3. Uçtan Uca Sistem Mimarisi

Sistem, Python'un `asyncio` ve çoklu iş parçacığı (`threading` / `multiprocessing`) mekanizmaları üzerinde çalışan iki ana hatta (TX ve RX) ayrılır:

```
===================================================================================================
                                      TX PİPELİNE (GİDEN HAT)
===================================================================================================
[Fiziksel Mikrofon]
        │ (16kHz PCM Ses Akışı)
        ▼
[Silero VAD v5] ── (Sessizlik / Konuşma Algılama: 250ms threshold)
        │
        ▼ (Anlamsal Ses Blokları: 1.5 - 2.0 sn)
[Faster-Whisper large-v3-turbo] ── (Language: 'tr', Beam: 1, Temperature: 0)
        │
        ▼ (Türkçe Ham Metin)
[Metin Normalizasyonu & Bağlaç Segmentasyonu]
        │
        ▼
[CTranslate2 NLLB-200-600M] ── (src: 'tur_Latn' -> tgt: 'eng_Latn')
        │
        ▼ (İngilizce Çeviri Metni)
[Coqui XTTS-v2 Streaming API] <── [Referans Ses Profili: reside_default.wav]
        │
        ▼ (24kHz PCM Ses Paketleri - 200ms chunks)
[SoundDevice / PyAudio API]
        │
        ▼
[VB-Audio Virtual Cable (CABLE Input)]
        │
        ▼ (Sanal Aygıt)
[MS TEAMS MİKROFON GİRDİSİ (CABLE Output)] ──> [Toplantı Katılımcıları (İngilizce Klon Ses)]


===================================================================================================
                                      RX PİPELİNE (GELEN HAT)
===================================================================================================
[MS TEAMS HOPARLÖR ÇIKIŞI (Kulaklık)]
        │
        ▼ (WASAPI Loopback Capture)
[SoundCard / WASAPI Dinleyici]
        │ (16kHz Downsampled Audio)
        ▼
[Silero VAD v5] ── (Konuşmacı Ses Blokları)
        │
        ▼
[Faster-Whisper large-v3-turbo] ── (Language: 'en', Task: 'transcribe')
        │
        ▼ (İngilizce Metin)
[CTranslate2 NLLB-200-600M] ── (src: 'eng_Latn' -> tgt: 'tur_Latn')
        │
        ▼ (Türkçe Çeviri Metni)
[Masaüstü Canlı Altyazı HUD (PyQt6 / Tkinter - Always on Top)] ──> [Kullanıcı Ekranı]
```

---

## 4. Model ve Motor Kıyaslama Raporu

### 4.1. Konuşma Tanıma (STT / ASR)
* **Değerlendirilenler:** OpenAI Whisper (Vanilla), Whisper.cpp, Faster-Whisper, Distil-Whisper.
* **Seçim:** **Faster-Whisper (`large-v3-turbo`)**
  * *Neden:* CTranslate2 C++ kütüphanesi üzerinde çalıştığı için standart PyTorch Whisper'a göre 4 kat daha hızlıdır ve %50 daha az VRAM harcar. `large-v3-turbo` modeli, standart `large-v3` kalitesini neredeyse korurken çıkarım katmanlarını 32'den 4'e düşürerek ~100 ms içinde Türkçe transkripsiyon üretir.
  * *Parametre Optimizasyonu:* `beam_size=1`, `best_of=1`, `condition_on_previous_text=False`, `vad_filter=False` (VAD'ı harici yürüttüğümüz için).

### 4.2. Makine Çevirisi (NMT)
* **Değerlendirilenler:** Ollama (Llama-3.1-8B-Instruct, Qwen-2.5-7B), Helsinki-NLP (Opus-MT), CTranslate2 NLLB-200 (Meta).
* **Seçim:** **CTranslate2 `facebook/nllb-200-distilled-600M` (int8)**
  * *Neden:* 
    * LLM'ler (Ollama vb.) prompt yükü (system prompt formatting), token-by-token üretim gecikmesi ve halüsinasyon riski taşır. Bir cümlenin çevirisi yerel LLM ile 300-600 ms sürer.
    * NLLB-200 600M ise özel bir çeviri ağıdır. CTranslate2 ile optimize edildiğinde Türkçe-İngilizce bir cümleyi **15-25 ms** içinde deterministik ve gramer doğruluğu yüksek olarak çevirir. VRAM yükü 800 MB'ın altındadır.

### 4.3. Ses Sentezi ve Ses Klonlama (TTS)
* **Değerlendirilenler:** F5-TTS, CosyVoice 2, OpenVoice v2, Coqui XTTS-v2.
* **Seçim:** **Coqui XTTS-v2 (Streaming API)**
  * *Neden:*
    1. **Streaming Desteği:** XTTS-v2, cümlenin tamamının sentezlenmesini beklemeden ilk 200 ms'lik ses paketini (token-by-token audio decoding) üreterek `inference_stream` metoduyla dışarı aktarabilir. Time-to-First-Audio (TTFA) gecikmesi RTX 5060 Ti üzerinde ~180 ms'dir.
    2. **Cross-Lingual Zero-Shot Klonlama:** Türkçe konuşan bir referans ses dosyasından (10 saniye) çıkarılan speaker embedding vektörünü doğrudan İngilizce fonemlerle eşleştirir. Sonuçta kullanıcının kendi ses tonu, rezonansı ve tınısıyla konuşan akıcı bir İngilizce ses üretilir.
    3. **Yerel & Python Uyumlu:** Harici bir bulut servisine ihtiyaç duymaz.

---

## 5. Düşük Gecikme (Latency) Stratejisi: Semantic Chunking

10 saniyelik bir konuşmada karşı tarafın 10 saniye beklememesi en kritik mühendislik problemidir.

### Dilbilgisi Kısıtı ve Çözümü:
* **Sorun:** Türkçe SOV (*Özne + Nesne + Yüklem*), İngilizce ise SVO (*Özne + Yüklem + Nesne*) yapısındadır. Kelime kelime (word-by-word) anlık çeviri yapılırsa Türkçede yüklem cümlenin sonunda yer aldığı için İngilizce cümle anlamsızlaşır.
* **Çözüm (Semantic Clause Chunking):** 
  Sistem tam cümlenin bitmesini beklemez; **anlamsal yan cümlecikleri** (clause) ve doğal konuşma nefes aralıklarını yakalar.
  1. Kullanıcı konuşurken Silero VAD kesintisiz dinler.
  2. Kullanıcı 250–350 ms sustuğunda veya konuşma süresi 1.8 saniyeye ulaştığında (veya "ve, ama, çünkü, bu yüzden" gibi bağlaçlar tespit edildiğinde) o anki öbek bir "chunk" olarak kesilir.
  3. Kesilen chunk hemen ASR $\to$ NMT $\to$ TTS kuyruğuna aktarılır.
  4. Siz bir sonraki cümleyi söylerken, önceki cümlenin sesi sanal kabloya akmaya başlar.

### Zaman Bütçesi (End-to-End Time Budget):

| Aşama | İşlem | Süre | Kümülatif Zaman |
| :--- | :--- | :--- | :--- |
| **T0** | Konuşmanın Başlaması & İlk Anlamsal Öbek | 1500 ms | 1500 ms |
| **T1** | Silero VAD (Duraklama / Kesim Onayı) | 10 ms | 1510 ms |
| **T2** | Faster-Whisper Turbo ile Deşifre | 110 ms | 1620 ms |
| **T3** | CTranslate2 NLLB ile TR $\to$ EN Çeviri | 20 ms | 1640 ms |
| **T4** | XTTS-v2 İlk Ses Paketi Üretimi (TTFA) | 180 ms | 1820 ms |
| **T5** | SoundDevice $\to$ VB-Cable Buffer | 15 ms | **~1835 ms** |

> **Net Sonuç:** Siz konuşmaya başladıktan **~1.8 saniye sonra** karşı taraf İngilizce ilk cümleyi duymaya başlar. Ardışık streaming blokları sayesinde ses kesintisiz olarak akar.

---

## 6. Ses Yönlendirme (Audio Routing) ve Donanım Konfigürasyonu

Fiziksel ek bir mikser veya donanımsal ses kartına gerek yoktur. Yazılımsal yönlendirme şu şekilde yapılandırılır:

### Aygıt Ayarları:
1. **VB-Audio Cable:** Ücretsiz sanal ses sürücüsü kurulur.
2. **Windows Ses Ayarları:**
   * Varsayılan Çıkış: Kulaklığınız (Örn: Realtek Audio / USB Headset)
   * Varsayılan Giriş: Fiziksel Mikrofonunuz
3. **Python Pipeline Yapılandırması:**
   * **Giriş Cihazı:** Fiziksel Mikrofon ID'si (SoundDevice ile okunur).
   * **Çıkış Cihazı:** `CABLE Input (VB-Audio Virtual Cable)` (XTTS sesi buraya basılır).
   * **Dinleme Cihazı (RX):** Windows WASAPI Loopback (Kulaklığınıza giden tüm sesleri, yani Teams'teki İngilizce konuşmacıyı arka planda klonlayıp yakalar).
4. **MS Teams Uygulama Ayarları:**
   * **Mikrofon:** `CABLE Output (VB-Audio Virtual Cable)` seçilir. (Böylece Teams sizin gerçek sesinizi değil, sadece çevrilmiş İngilizce klon sesinizi duyar).
   * **Hoparlör:** Normal kulaklığınız seçilir.

---

## 7. Ses Klonlama ve Çoklu Profil Yönetimi

### Referans Ses Kaydı Özellikleri:
* **Format:** 24 kHz veya 48 kHz, Mono, 16-bit PCM WAV.
* **Süre:** 8 - 12 saniye (Tek parça, sessiz oda ortamında kaydedilmiş, nefes patlaması veya yankı içermeyen doğal ton).
* **Konuşma Tarzı:** Kullanıcının toplantılarda kullandığı doğal ses tonu, diksiyonu ve hızı.

### Çoklu Profil Sistemi (Profile Manager):
Sistem `profiles/` dizini altında birden fazla referans ses dosyasını yönetebilir:
* `profiles/reside_formal.wav` $	o$ Ciddi iş toplantıları için sakin, resmi ton.
* `profiles/reside_casual.wav` $	o$ Samimi beyin fırtınası görüşmeleri için dinamik ton.
* `profiles/en_native_speaker.wav` $	o$ Klonlama yerine kusursuz aksanlı hazır bir profil.

Profil dosyalarından çıkarılan speaker embedding tensörleri (`speaker_embeddings.pth`) ilk açılışta önbelleğe (cache) alınır; böylece toplantı sırasında profil değişimi **<50 ms** içinde anında gerçekleşir.

---

## 8. Canlı Altyazı Arayüzü (HUD / Overlay)

Karşı tarafın konuştuğu İngilizce sesin Türkçeye çevrilerek ekranda gösterilmesi için:
* **Teknoloji:** PyQt6 / PySide6 veya hafif Tkinter GUI.
* **Özellikler:**
  * **Always-on-Top:** Toplantı penceresinin veya sunum slaytlarının her zaman üzerinde kalır.
  * **Frameless & Transparent:** Çerçevesiz, arka planı yarı saydam (opacity %80), dikkat dağıtmayan koyu tema.
  * **Streaming Text Buffer:** Karşı taraf konuştukça metin kelime kelime akar, konuşma bittiğinde yeni satıra geçer ve son 3-5 konuşma geçmişini tutar.
  * **Input / Arama Alanı:** Kullanıcının acil bir metin yazıp doğrudan panoya (clipboard) kopyalayabileceği veya sesli okutabileceği opsiyonel bir hızlı giriş barı.

---

## 9. Proje Dizin Yapısı ve `/docs` Klasör Planı

```text
teams-translator-ai/
├── docs/
│   ├── 01_system_architecture.md       # Ayrıntılı veri akışı, kuyruk yapıları ve mimari şemalar
│   ├── 02_audio_routing_vb_cable.md    # Windows WASAPI ve VB-Cable kurulum rehberi
│   ├── 03_benchmarks_and_latency.md    # Model çıkarım süreleri, chunk büyüklüğü optimizasyonu
│   ├── 04_voice_cloning_guide.md       # Referans ses kaydı alma ve embedding optimizasyonu
│   └── 05_installation_guide.md        # CUDA 12.8, PyTorch, CTranslate2 ve paket kurulumları
├── profiles/                           # Referans klon ses wav dosyaları ve embedding cache
│   ├── reside_default.wav
│   └── profiles.json
├── src/
│   ├── audio/
│   │   ├── capture.py                  # Mikrofon ve WASAPI loopback yakalama sınıfları
│   │   ├── player.py                   # VB-Cable sanal çıkış ses yazıcı
│   │   └── vad.py                      # Silero VAD akış ve sessizlik bölücü
│   ├── engine/
│   │   ├── asr.py                      # Faster-Whisper wrapper (TR & EN)
│   │   ├── translator.py               # CTranslate2 NLLB-200 çevirici
│   │   └── tts.py                      # Coqui XTTS-v2 streaming wrapper
│   ├── pipeline/
│   │   ├── tx_pipeline.py              # Mikrofon -> VAD -> STT -> Trans -> TTS -> Sanal Kablo
│   │   └── rx_pipeline.py              # Teams Loopback -> STT -> Trans -> GUI Altyazı
│   ├── ui/
│   │   └── overlay.py                  # Şeffaf, her zaman üstte canlı altyazı penceresi
│   └── main.py                         # Ana orkestrasyon ve CLI başlatıcı
├── config.yaml                         # Ses kartı ID'leri, seçili profil, model yolları
├── requirements.txt                    # Gerekli Python paketleri
└── README.md                           # Proje tanıtımı ve hızlı başlangıç
```

---

## 10. Kurulum ve Geliştirme Yol Haritası

### Adım 1: Temel Ortamın Hazırlanması
```bash
# Python sanal ortamı oluşturma
python -m venv venv
venv\Scripts\activate

# PyTorch (CUDA 12.8 uyumlu) kurulumu
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# Çekirdek bağımlılıklar
pip install faster-whisper ctranslate2 sounddevice soundcard numpy PyQt6
pip install TTS --no-deps
pip install deepspeed pydub transformers sentencepiece
```

### Adım 2: Ses Cihazlarının Tespiti
`sounddevice` ile mikrofon ve VB-Cable index numaraları belirlenir:
```python
import sounddevice as sd
print(sd.query_devices())
```

### Adım 3: İnkremental Modül Doğrulama
1. **Mikrofon $\to$ VAD $\to$ Faster-Whisper:** Türkçe konuşmanın 150 ms içinde metne döküldüğünün doğrulanması.
2. **NLLB-200 Entegrasyonu:** Metnin 20 ms içinde İngilizceye çevrildiğinin doğrulanması.
3. **XTTS-v2 Streaming Testi:** İngilizce metnin klon ses ile VB-Cable'a parça parça aktarılması.
4. **RX & Overlay Testi:** Teams sesinin WASAPI ile yakalanıp ekranda canlı Türkçe altyazıya dönüştürülmesi.
5. **Entegre Uçtan Uca Test:** MS Teams test aramasında (Echo test / Test Call) gecikme ve ses kalitesinin ölçülmesi.