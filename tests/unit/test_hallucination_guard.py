from teams_translator.streaming.hallucination_guard import HallucinationGuard, SpeechEvidence, normalize_text


GOOD_EVIDENCE = SpeechEvidence(utterance_ms=900, voiced_ms=700, voiced_ratio=0.77, max_queue_age_ms=30)


def test_good_speech_is_accepted():
    decision = HallucinationGuard().evaluate("We need to review the deployment", GOOD_EVIDENCE, {"avg_logprob": -0.2})
    assert decision.accepted


def test_silence_hallucination_is_rejected_by_speech_evidence_before_pattern_list():
    no_speech = SpeechEvidence(utterance_ms=600, voiced_ms=0, voiced_ratio=0.0)
    decision = HallucinationGuard().evaluate("thank you for watching", no_speech)
    assert not decision.accepted
    assert decision.reason == "insufficient_voiced_audio"


def test_known_pattern_is_final_safety_net_for_otherwise_good_evidence():
    decision = HallucinationGuard().evaluate("Thank you for watching!", GOOD_EVIDENCE)
    assert not decision.accepted
    assert decision.reason == "known_hallucination_pattern"


def test_turkish_capital_dotted_i_matches_lowercase_hallucination_pattern():
    assert normalize_text("İzlediğiniz için teşekkür ederim.") == "izlediğiniz için teşekkür ederim"
    decision = HallucinationGuard().evaluate("İzlediğiniz için teşekkür ederim.", GOOD_EVIDENCE)
    assert not decision.accepted
    assert decision.reason == "known_hallucination_pattern"


def test_short_turkish_subscribe_hallucination_is_rejected():
    decision = HallucinationGuard().evaluate("Abone ol.", GOOD_EVIDENCE)
    assert not decision.accepted
    assert decision.reason == "known_hallucination_pattern"

def test_short_dot_turkish_subscribe_hallucination_is_rejected():
    decision = HallucinationGuard().evaluate("Altyazı M.K.", GOOD_EVIDENCE)
    assert not decision.accepted
    assert decision.reason == "known_hallucination_pattern"


def test_whisper_metadata_can_reject_no_speech_and_repetition():
    guard = HallucinationGuard()
    assert guard.evaluate("apparently valid", GOOD_EVIDENCE, {"no_speech_prob": 0.95}).reason == "whisper_no_speech"
    assert guard.evaluate("apparently valid", GOOD_EVIDENCE, {"compression_ratio": 3.0}).reason == "whisper_repetition"
