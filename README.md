# Realtime Full-Duplex Turkish ↔ English & French MS Teams Translator with Voice Cloning

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![CUDA 12.x](https://img.shields.io/badge/CUDA-12.x-green.svg)](https://developer.nvidia.com/cuda-toolkit)
[![OS: Windows 11](https://img.shields.io/badge/OS-Windows%2011%20Native-orange.svg)](https://www.microsoft.com/windows)
[![License: MIT](https://img.shields.io/badge/License-MIT-purple.svg)](LICENSE)

A local, private, full-duplex speech-to-speech translator designed specifically for **Microsoft Teams, Zoom, and Google Meet** on Windows. 

Translate your speech live between **Turkish** and **English / French** while preserving your original identity through **cross-lingual voice cloning**.

---

## Key Features

- **Turkish Mic ➔ Cloned English / French Speech (Outgoing)**: Speak in Turkish into your physical microphone. The system transcribes, translates, and synthesizes your speech in real-time using **your cloned voice** (or custom voice avatars), sending the cloned audio directly into Teams as your virtual microphone.
- **English / French Teams ➔ Live Turkish Subtitles (Incoming)**: Automatically captures remote meeting audio directly from Windows WASAPI loopback and displays streaming, punctuated Turkish subtitles on your screen.
- **Zero-Shot Voice Cloning (XTTS-v2)**: Clone any voice from a clean 6–10 second reference `.wav` file. The cloned voice seamlessly speaks English and French with accurate prosody and natural intonation.
- **Live Mid-Meeting Switching**:
  - Switch voice avatars (e.g. *Personal Cloned Voice* ➔ *Anime Character Voice*) with **0 ms latency** during an active meeting.
  - Switch target language (e.g. **Turkish ➔ English** to **Turkish ➔ French**) on-the-fly without restarting or interrupting audio streams.
- **100% Local & Private**: All inference (VAD, ASR, MT, TTS) runs locally on your GPU. No cloud APIs, no audio leaks, and zero recurring subscription costs.
- **Hardware-Aware Diagnostics**: Real-time dBFS audio meters for physical mic, WASAPI loopback, and VB-CABLE virtual render, along with P50/P95 end-to-end latency telemetry and VRAM monitoring.

---

## System Requirements

### Hardware
- **Operating System**: Windows 11 (64-bit) native execution (required for native WASAPI loopback capture).
- **GPU**: NVIDIA GPU with CUDA support and at least **12 GB VRAM** (16 GB VRAM recommended).
  - *Verified & benchmarked on*: NVIDIA GeForce RTX 5060 Ti (16 GB), RTX 4070 / 4080 / 4090, RTX 3060 (12 GB).
- **RAM**: 16 GB minimum (32 GB recommended).
- **Storage**: ~15 GB free NVMe / SSD disk space for offline model checkpoints.

### Software
- **Python**: Version 3.12 (64-bit).
- **NVIDIA Driver & CUDA**: CUDA 12.x compatible driver.
- **Virtual Audio Device**: [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) (Free virtual audio driver).

---

## Architecture & Pipeline

```
[ Physical Mic ] ──> [ Silero VAD ] ──> [ Whisper ASR ] ──> [ MarianMT / CTranslate2 ] ──> [ XTTS-v2 Voice Cloning ] ──> [ VB-CABLE Input ] ──> [ Teams Mic ]
                                              │                         │                               │
                                      (Turkish Speech)          (English/French Text)           (Cloned Speech PCM)

[ Teams Speaker ] ──> [ WASAPI Loopback ] ──> [ Whisper ASR ] ──> [ MarianMT / CTranslate2 ] ──> [ Live Subtitles Web UI ]
                                                    │                         │
                                            (Incoming Audio)          (Turkish Subtitles)
```

- **VAD**: Silero VAD with speech envelope hysteresis and adaptive hangover to preserve natural Turkish SOV sentence structures.
- **ASR**: OpenAI `whisper-large-v3-turbo` with prompt biasing and automated prefix stripping.
- **MT**: Helsinki-NLP `opus-mt-tc-big-tr-en`, `opus-mt-tc-big-en-tr`, and `opus-mt-tr-fr` with CTranslate2 INT8 / HuggingFace MarianMT execution.
- **TTS**: Coqui XTTS-v2 with persistent speaker latent caching.

---

## Step-by-Step Installation

### 1. Install VB-Audio Virtual Cable
1. Download **VB-CABLE Driver** from [VB-Audio](https://vb-audio.com/Cable/).
2. Extract the archive and run `VBCABLE_Setup_x64.exe` as Administrator.
3. Reboot your computer if prompted.

### 2. Clone Repository & Setup Virtual Environment
```powershell
# Clone the repository
git clone https://github.com/onurozkir/speech-to-translate-en-tr.git
cd speech-to-translate-en-tr

# Create Python 3.12 virtual environment
python -m venv .venv

# Activate the virtual environment
.\.venv\Scripts\Activate.ps1

# Upgrade pip and install package in editable mode
python -m pip install --upgrade pip
pip install -e .
```

### 3. Download Model Weights
All models are downloaded once and cached offline in `models/`:
```powershell
# Download all required models (Whisper, MT English & French, XTTS-v2)
python scripts/download_models.py all
```
*Or download individual models as needed:*
```powershell
python scripts/download_models.py whisper    # Whisper Large v3 Turbo
python scripts/download_models.py mt-tr-en   # Turkish -> English translation
python scripts/download_models.py mt-en-tr   # English -> Turkish translation
python scripts/download_models.py mt-tr-fr   # Turkish -> French translation
python scripts/download_models.py xtts       # Coqui XTTS-v2 voice cloning
```

---

## Microsoft Teams Configuration

Configure Microsoft Teams audio settings so that it uses the cloned audio output as your microphone:

1. In Teams, go to **Settings ➔ Devices**.
2. **Microphone**: Select **CABLE Output (VB-Audio Virtual Cable)**.
3. **Speaker**: Select your regular physical headphones or speakers (e.g. *Speakers / Headphones*).
4. **Noise suppression in Teams**: Set to **Low** or **Off** (since XTTS-v2 generates clean PCM).

---

## Running the Application

1. Start the server:
   ```powershell
   python src/teams_translator/main.py run
   ```
2. Open your web browser and navigate to:
   ```
   http://127.0.0.1:8000
   ```
3. Configure devices in the Web Dashboard:
   - **Physical Mic**: Your physical microphone.
   - **Teams Audio (Loopback)**: Your physical headphones/speakers with `[Loopback]`.
   - **VB-CABLE Render**: `CABLE Input (VB-Audio Virtual Cable)`.
   - **Voice Profile**: Choose your personal voice or an avatar voice.
   - **Outgoing Target Language**: Select `English (en)` or `Français (fr)`.
4. Click **Start Meeting**.

### CPU / Mock Mode (For testing without GPU)
```powershell
python src/teams_translator/main.py run --mock
```

---

## Adding Custom Voice Profiles

You can add as many custom voice avatars as you like (e.g., personal cheerful voice, anime character, professional tone):

1. Create a new folder under `voices/<profile_name>/`.
2. Place a clean 6–10 second `.wav` audio recording inside the folder named `reference.wav` (16-bit PCM, 24kHz or 16kHz recommended).
3. Add a `profile.json` manifest:
   ```json
   {
     "id": "anime-girl",
     "display_name": "Anime Character",
     "backend": "xtts_v2",
     "reference_audio_path": "reference.wav",
     "reference_language": "ja",
     "target_languages": ["en", "fr"],
     "is_default": false,
     "metadata": {
       "description": "Japanese anime voice cloned for real-time English and French synthesis"
     }
   }
   ```
4. Restart the server. The profile will appear in the web dashboard and can be switched live mid-meeting!

---

## Running Tests

Run the complete test suite:
```powershell
python -m pytest tests/ -v
```

---

## License

- Code: [MIT License](LICENSE)
- XTTS-v2 Weights: Coqui Public Model License (CPML - Non-commercial / Personal use)
- Whisper & MarianMT: MIT / Apache 2.0 / CC-BY-4.0
