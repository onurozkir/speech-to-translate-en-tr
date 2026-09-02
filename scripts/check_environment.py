"""Phase B0: Environment and target hardware verification script."""

import sys
import platform

print("=" * 60)
print(" TEAMS TRANSLATOR - ENVIRONMENT & HARDWARE VERIFICATION")
print("=" * 60)

# 1. OS & Python
print(f"OS:            {platform.system()} {platform.release()} ({platform.version()})")
print(f"Python:        {sys.version.split()[0]} ({sys.executable})")

if platform.system() != "Windows":
    print(" [WARNING] Target runtime is Windows 11 native. Non-Windows detected.")

if sys.version_info < (3, 12):
    print(" [WARNING] Python 3.12+ recommended.")

# 2. PyTorch & CUDA
try:
    import torch
    print(f"PyTorch:       {torch.__version__}")
    cuda_avail = torch.cuda.is_available()
    print(f"CUDA Available:{cuda_avail}")
    if cuda_avail:
        dev_name = torch.cuda.get_device_name(0)
        cap = torch.cuda.get_device_capability(0)
        vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        print(f"GPU Device:    {dev_name}")
        print(f"Compute Cap:   {cap[0]}.{cap[1]}")
        print(f"Total VRAM:    {vram_gb:.2f} GB")
    else:
        print(" [WARNING] CUDA is NOT available to PyTorch!")
except ImportError:
    print("PyTorch:       [NOT INSTALLED]")

# 3. Audio & WASAPI
try:
    import pyaudiowpatch as pyaudio
    pa = pyaudio.PyAudio()
    dev_count = pa.get_device_count()
    print(f"WASAPI/Audio:  PyAudioWPatch OK ({dev_count} devices found)")
    pa.terminate()
except ImportError:
    try:
        import pyaudio
        print("WASAPI/Audio:  Standard PyAudio installed (WASAPI loopback may be limited)")
    except ImportError:
        print("WASAPI/Audio:  [NOT INSTALLED]")

# 4. Transformers & CTranslate2
for pkg in ["ctranslate2", "transformers", "sentencepiece", "soundfile", "soxr"]:
    try:
        mod = __import__(pkg)
        ver = getattr(mod, "__version__", "OK")
        print(f"{pkg:14s}: {ver}")
    except ImportError:
        print(f"{pkg:14s}: [NOT INSTALLED]")

print("=" * 60)

