from teams_translator.streaming.commit_policy import CommitController


def test_commit_punctuation():
    ctrl = CommitController(min_words=2)
    dec = ctrl.evaluate("Merhaba nasılsınız? Bugün hava çok güzel.")
    assert dec.should_commit
    assert dec.committed_text == "Merhaba nasılsınız?"
    assert dec.remaining_partial_text == "Bugün hava çok güzel."
    assert dec.reason == "punctuation"


def test_commit_silence_endpoint():
    ctrl = CommitController()
    dec = ctrl.evaluate("Toplantı başladı ve devam ediyor", is_silence_endpoint=True)
    assert dec.should_commit
    assert dec.committed_text == "Toplantı başladı ve devam ediyor"
    assert dec.reason == "silence_endpoint"


def test_commit_deadline_timeout():
    ctrl = CommitController(min_words=3, max_wait_ms=1000)
    # First partial
    _ = ctrl.evaluate("Bir iki üç dört beş", now_ms=1000.0)
    # After timeout
    dec = ctrl.evaluate("Bir iki üç dört beş", now_ms=2100.0)
    assert dec.should_commit
    assert dec.reason == "deadline_timeout"

