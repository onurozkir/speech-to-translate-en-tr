import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np
from teams_translator.asr.whisper_backend import WhisperASRAdapter
from teams_translator.core.types import Direction

print("=" * 60)
print(" BENCHMARK B2: ASR INFERENCE & SESSION SHARING")
print("=" * 60)

model_path = "models/asr/whisper-large-v3-turbo"
if not Path(model_path).exists():
    print(f"Model path '{model_path}' does not exist. Run 'python scripts/download_models.py whisper' first.")
    exit(1)

adapter = WhisperASRAdapter()
adapter.initialize(model_path=model_path, device="cuda", compute_type="float16")
adapter.warmup()

session_tr = adapter.create_session("stream_tr", Direction.OUTGOING, "tr")
session_en = adapter.create_session("stream_en", Direction.INCOMING, "en")

# Benchmark dummy 2-second audio chunks
dummy_audio = (0.1 * np.random.randn(32000)).astype(np.float32)

t0 = time.monotonic_ns()
_ = adapter.process_audio(session_tr, dummy_audio, t0)
t1 = time.monotonic_ns()

print(f"Turkish Session Inference Latency: {(t1 - t0)/1e6:.2f} ms")

t2 = time.monotonic_ns()
_ = adapter.process_audio(session_en, dummy_audio, t2)
t3 = time.monotonic_ns()

print(f"English Session Inference Latency: {(t3 - t2)/1e6:.2f} ms")

adapter.shutdown()
print("=" * 60)

