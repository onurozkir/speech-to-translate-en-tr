from types import SimpleNamespace
import logging

import numpy as np
import torch

from teams_translator.asr.whisper_backend import WhisperASRAdapter
from teams_translator.asr import whisper_backend
from teams_translator.core.types import Direction


def test_huggingface_decode_uses_one_length_owner_and_current_language():
    adapter = WhisperASRAdapter(min_audio_rms=0.0, beam_size=3)

    class FakeProcessor:
        def __call__(self, audio, sampling_rate, return_tensors):
            return SimpleNamespace(input_features=torch.ones((1, 80, 20)))

        def batch_decode(self, ids, **kwargs):
            assert kwargs["clean_up_tokenization_spaces"] is False
            return ["Merhaba nasılsınız?"]

    class FakeModel:
        def __init__(self):
            self.generation_config = SimpleNamespace(
                max_length=448,
                max_new_tokens=None,
                forced_decoder_ids=[[1, None], [2, 50360]],
            )
            self.received = None

        def generate(self, input_features, generation_config):
            self.received = generation_config
            scores = (torch.zeros((1, 8)), torch.zeros((1, 8)))
            return SimpleNamespace(sequences=torch.tensor([[1, 2]]), scores=scores)

    adapter.processor = FakeProcessor()
    adapter.model = FakeModel()
    text, info = adapter._transcribe_transformers(np.ones(4800, dtype=np.float32) * 0.1, "tr")

    assert text == "Merhaba nasılsınız?"
    assert "avg_logprob" in info
    assert adapter.model.generation_config.max_length == 448
    assert adapter.model.received.max_length == 68
    assert adapter.model.received.max_new_tokens is None
    assert adapter.model.received.forced_decoder_ids is None
    assert adapter.model.received.language == "tr"
    assert adapter.model.received.task == "transcribe"
    assert adapter.model.received.num_beams == 3


def test_initialize_resolves_unavailable_cuda_to_cpu(monkeypatch, tmp_path, caplog):
    loaded = {}

    class FakeProcessorLoader:
        @staticmethod
        def from_pretrained(path, **kwargs):
            return object()

    class FakeModel:
        def __init__(self):
            self.generation_config = SimpleNamespace(max_length=448, forced_decoder_ids=[])
            self.moved_to = None

        def to(self, device):
            self.moved_to = device
            return self

    class FakeModelLoader:
        @staticmethod
        def from_pretrained(path, **kwargs):
            loaded["dtype"] = kwargs["dtype"]
            loaded["model"] = FakeModel()
            return loaded["model"]

    monkeypatch.setattr(whisper_backend, "AutoProcessor", FakeProcessorLoader)
    monkeypatch.setattr(whisper_backend, "AutoModelForSpeechSeq2Seq", FakeModelLoader)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

    adapter = WhisperASRAdapter()
    with caplog.at_level(logging.WARNING):
        adapter.initialize(str(tmp_path), device="cuda", compute_type="float16")

    assert adapter.device == "cpu"
    assert adapter.compute_type == "float32"
    assert loaded["dtype"] == torch.float32
    assert loaded["model"].moved_to == "cpu"
    assert "CUDA is unavailable" in caplog.text


def test_partial_decode_is_coalesced_even_when_first_attempt_returns_empty():
    adapter = WhisperASRAdapter(partial_interval_ms=500, min_audio_rms=0.0)
    adapter.model = object()
    calls = []

    def fake_decode(audio, language):
        calls.append(len(audio))
        return "", {"avg_logprob": -0.2}

    adapter._decode_audio = fake_decode
    session = adapter.create_session("tx", Direction.OUTGOING, "tr")
    frame = np.ones(320, dtype=np.float32) * 0.1

    for _ in range(15):
        adapter.process_audio(session, frame, 1)
    assert len(calls) == 1

    for _ in range(24):
        adapter.process_audio(session, frame, 2)
    assert len(calls) == 1
    adapter.process_audio(session, frame, 3)
    assert len(calls) == 2


def test_flush_redecodes_complete_buffer_instead_of_committing_stale_partial():
    adapter = WhisperASRAdapter(min_audio_rms=0.0)
    adapter.model = object()
    adapter._decode_audio = lambda audio, language: (
        "Merhaba nasılsınız?",
        {"avg_logprob": -0.2, "audio_samples": len(audio)},
    )
    session = adapter.create_session("tx", Direction.OUTGOING, "tr")
    session.audio_buffer = [np.ones(4800, dtype=np.float32), np.ones(3200, dtype=np.float32)]
    session.total_audio_samples = 8000
    session.last_partial_text = "Merhaba"

    event = adapter.flush_session(session)

    assert event is not None
    assert event.text == "Merhaba nasılsınız?"
    assert event.model_info["audio_samples"] == 8000
    assert session.audio_buffer == []
    assert session.total_audio_samples == 0


def test_flush_preserves_real_capture_span_and_resets_it_for_next_utterance():
    adapter = WhisperASRAdapter(min_audio_rms=0.0)
    adapter.model = object()
    adapter._decode_audio = lambda audio, language: (
        "Merhaba",
        {"avg_logprob": -0.2},
    )
    session = adapter.create_session("tx", Direction.OUTGOING, "tr")

    adapter.process_audio(session, np.ones(3200, dtype=np.float32), 1_000_000_000)
    adapter.process_audio(session, np.ones(4800, dtype=np.float32), 1_300_000_000)
    event = adapter.flush_session(session)

    assert event is not None
    assert event.audio_start_ns == 800_000_000
    assert event.audio_end_ns == 1_300_000_000

    adapter.process_audio(session, np.ones(4800, dtype=np.float32), 2_000_000_000)
    next_event = adapter.flush_session(session)

    assert next_event is not None
    assert next_event.audio_start_ns == 1_700_000_000
    assert next_event.audio_end_ns == 2_000_000_000


def test_strip_prompt_prefix():
    from teams_translator.asr.whisper_backend import strip_prompt_prefix

    prompt = "Toplantı, Türkçe, teknik, iş, günlük konuşma."
    # Case 1: Exact prompt repeated by Whisper
    raw1 = "Toplantı, Türkçe, teknik, iş, günlük konuşma. Bugün güne sakin bir başlangıç yaptım."
    assert strip_prompt_prefix(raw1, prompt) == "Bugün güne sakin bir başlangıç yaptım."

    # Case 2: Multi-sentence prompt repeated
    prompt2 = "Merhaba. Türkçe iş, teknik ve günlük konuşma toplantısı."
    raw2 = "Merhaba. Türkçe iş, teknik ve günlük konuşma toplantısı. Kahvemi içerken gün içinde yapacağım işleri düşündüm."
    assert strip_prompt_prefix(raw2, prompt2) == "Kahvemi içerken gün içinde yapacağım işleri düşündüm."

    # Case 3: Prompt not repeated
    raw3 = "Hava oldukça güzeldi."
    assert strip_prompt_prefix(raw3, prompt) == "Hava oldukça güzeldi."
