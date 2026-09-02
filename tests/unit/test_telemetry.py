from teams_translator.core.types import Direction, LatencyEvent
from teams_translator.telemetry.metrics import TelemetryTracker


def test_telemetry_percentiles():
    tracker = TelemetryTracker(window_size=100)
    for dur in [100.0, 200.0, 300.0, 400.0, 500.0]:
        tracker.record_event(LatencyEvent(
            meeting_id="m1",
            utterance_id="u1",
            direction=Direction.INCOMING,
            event_type="incoming_partial",
            duration_ms=dur,
        ))

    p = tracker.get_percentiles("incoming_partial")
    assert p["count"] == 5
    assert p["p50"] == 300.0
    assert p["p95"] == 480.0

