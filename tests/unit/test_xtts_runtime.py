from teams_translator.tts import xtts_backend


def test_coqui_xtts_runtime_imports_are_available():
    assert xtts_backend.torch is not None
    assert xtts_backend.XttsConfig is not None, xtts_backend._tts_import_error
    assert xtts_backend.Xtts is not None, xtts_backend._tts_import_error
