import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from teams_translator.translation.ctranslate_backend import CTranslate2MTAdapter

print("=" * 60)
print(" BENCHMARK B3: CTRANSLATE2 OPUS-MT TR <-> EN")
print("=" * 60)

tr_en_path = "models/mt/opus-mt-tc-big-tr-en"
en_tr_path = "models/mt/opus-mt-tc-big-en-tr"

if not Path(tr_en_path).exists() or not Path(en_tr_path).exists():
    print("MT models not found. Run 'python scripts/download_models.py mt-tr-en' and 'mt-en-tr'.")
    exit(1)

mt = CTranslate2MTAdapter()
mt.initialize(tr_en_model_path=tr_en_path, en_tr_model_path=en_tr_path, device="cpu", compute_type="int8")
mt.warmup()

sentences_tr = [
    "Merhaba, bugünkü toplantımıza katıldığınız için teşekkür ederim.",
    "Proje mimarisi hakkında ne düşünüyorsunuz?",
    "Ses gecikmesi bir saniyenin altında kalmalı.",
]

print("\n--- Testing TR -> EN Translation ---")
for s in sentences_tr:
    t0 = time.monotonic_ns()
    res = mt.translate(s, "tr", "en")
    t1 = time.monotonic_ns()
    print(f"TR:  {s}")
    print(f"EN:  {res} [{(t1-t0)/1e6:.2f} ms]\n")

mt.shutdown()
print("=" * 60)

