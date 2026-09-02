"""Outgoing Pipeline: Turkish Mic -> guarded ASR -> MT -> cloned TTS -> VB-CABLE."""

from __future__ import annotations

import asyncio
import collections
import logging
import time
from dataclasses import asdict
from typing import Callable, Optional

import numpy as np

from teams_translator.asr.base import ASRAdapter, ASRSession
from teams_translator.audio.capture import AudioCaptureEngine
from teams_translator.audio.devices import DeviceInfo
from teams_translator.audio.render import AudioRenderEngine
from teams_translator.audio.resampler import AudioResampler
from teams_translator.config.models import AppConfig
from teams_translator.core.bounded_queue import BoundedQueue
from teams_translator.core.types import Direction, LatencyEvent, TranslationEvent, UtteranceEvent, UtteranceState
from teams_translator.streaming.commit_policy import CommitController
from teams_translator.streaming.pipeline_runtime import (
    build_guard,
    build_vad,
    next_pcm_chunk,
    reset_asr_utterance,
    speech_evidence,
)
from teams_translator.streaming.vad import VADResult
from teams_translator.translation.base import MTAdapter
from teams_translator.tts.base import TTSAdapter, VoiceProfile

logger = logging.getLogger("teams_translator.outgoing")


class OutgoingPipeline:
    """Realtime outgoing pipeline with a non-inference PortAudio callback boundary."""

    def __init__(
        self,
        meeting_id: str,
        mic_device: DeviceInfo,
        render_device: DeviceInfo,
        asr_adapter: ASRAdapter,
        mt_adapter: MTAdapter,
        tts_adapter: TTSAdapter,
        voice_profile: VoiceProfile,
        config: AppConfig,
        on_event_callback: Optional[Callable[[dict], None]] = None,
        on_latency_callback: Optional[Callable[[LatencyEvent], None]] = None,
    ):
        self.meeting_id = meeting_id
        self.mic_device = mic_device
        self.render_device = render_device
        self.asr_adapter = asr_adapter
        self.mt_adapter = mt_adapter
        self.tts_adapter = tts_adapter
        self.voice_profile = voice_profile
        self.config = config
        self.target_language: str = "en"
        self.on_event_callback = on_event_callback
        self.on_latency_callback = on_latency_callback

        self.vad = build_vad(config.streaming)
        self.guard = build_guard(config.streaming)
        self.commit_controller = CommitController(
            min_words=config.streaming.commit_min_words,
            max_wait_ms=config.streaming.commit_max_wait_ms,
            stable_prefix_min_count=config.streaming.stable_prefix_min_count,
        )
        self.resampler_in = AudioResampler(in_rate=config.audio.sample_rate, out_rate=16000, streaming=True)
        self.asr_session: Optional[ASRSession] = None
        self.capture_engine: Optional[AudioCaptureEngine] = None
        self.render_engine: Optional[AudioRenderEngine] = None
        self.committed_queue: BoundedQueue[UtteranceEvent] = BoundedQueue(
            maxsize=config.streaming.max_committed_queue_size,
            drop_oldest_on_full=False,
        )
        self.tts_queue: BoundedQueue[TranslationEvent] = BoundedQueue(
            maxsize=config.streaming.max_tts_queue_size,
            drop_oldest_on_full=False,
        )

        self.is_running = False
        self._tasks: list[asyncio.Task] = []
        self._sequence_counter = 0
        self._in_speech = False
        self._preroll = collections.deque(maxlen=max(1, 300 // config.audio.frame_duration_ms))
        self._last_vad_result = VADResult(False, 0.0, "idle", None, 0.0, 0.0, -120.0, 0.0, 0.0, 0.0, "unknown")
        self._current_max_queue_age_ms = 0.0
        self._max_queue_age_seen_ms = 0.0
        self._dropped_audio_samples = 0
        self._last_rejection: Optional[dict] = None
        self._overloaded = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def start(self) -> None:
        if self.is_running:
            return
        self._loop = asyncio.get_running_loop()
        self.is_running = True
        self.capture_engine = AudioCaptureEngine(
            device_info=self.mic_device,
            sample_rate=self.config.audio.sample_rate,
            frame_duration_ms=self.config.audio.frame_duration_ms,
            ring_buffer_sec=self.config.audio.ring_buffer_duration_sec,
        )
        self.render_engine = AudioRenderEngine(
            device_info=self.render_device,
            sample_rate=self.config.audio.sample_rate,
            frame_duration_ms=self.config.audio.frame_duration_ms,
        )
        self.asr_session = self.asr_adapter.create_session(
            stream_id=f"tx_{self.meeting_id}",
            direction=Direction.OUTGOING,
            language="tr",
            initial_prompt=getattr(self.config.asr, "initial_prompt", ""),
        )
        self.asr_session.metadata["meeting_id"] = self.meeting_id
        try:
            self.capture_engine.start()
            self.render_engine.start()
        except Exception:
            self.is_running = False
            if self.capture_engine:
                self.capture_engine.stop()
            if self.render_engine:
                self.render_engine.stop()
            raise
        self._tasks = [
            asyncio.create_task(self._audio_worker(), name="outgoing-audio"),
            asyncio.create_task(self._mt_worker(), name="outgoing-mt"),
            asyncio.create_task(self._tts_worker(), name="outgoing-tts"),
        ]
        logger.info("Outgoing pipeline: %s -> %s", self.mic_device.name, self.render_device.name)

    async def _audio_worker(self) -> None:
        """Drain bounded PCM outside PortAudio, then run VAD/Whisper in a worker thread."""
        assert self.capture_engine is not None
        frame_size = self.capture_engine.frame_size
        while self.is_running:
            available = self.capture_engine.ring_buffer.available_read
            if available < frame_size:
                await asyncio.sleep(0.005)
                continue
            queue_age_ms = available / self.capture_engine.sample_rate * 1000.0
            self._max_queue_age_seen_ms = max(self._max_queue_age_seen_ms, queue_age_ms)
            if queue_age_ms > self.config.streaming.max_audio_queue_age_ms:
                discard = max(0, available - frame_size)
                if discard:
                    self.capture_engine.read_samples(discard)
                    self._dropped_audio_samples += discard
                    self._reject_current("stale_audio", self.asr_session.last_partial_text if self.asr_session else "")
                    self.vad.reset()
                    self._in_speech = False
                    self._preroll.clear()
                queue_age_ms = frame_size / self.capture_engine.sample_rate * 1000.0
            frame = self.capture_engine.read_samples(frame_size)
            if len(frame) < frame_size:
                continue
            captured_at_ns = time.monotonic_ns() - int(queue_age_ms * 1e6)
            await asyncio.to_thread(self._process_audio_frame, frame, captured_at_ns, queue_age_ms)

    def _process_audio_frame(self, frame_48k: np.ndarray, captured_at_ns: int, queue_age_ms: float) -> None:
        if not self.is_running or self.asr_session is None:
            return
        frame_16k = self.resampler_in.process(frame_48k)
        vad_result = self.vad.process(frame_16k)
        self._last_vad_result = vad_result
        if vad_result.phase != "idle":
            self._current_max_queue_age_ms = max(self._current_max_queue_age_ms, queue_age_ms)

        if vad_result.transition == "started":
            self._in_speech = True
            while self._preroll:
                self.asr_adapter.process_audio(self.asr_session, self._preroll.popleft(), captured_at_ns)

        if vad_result.active:
            event = self.asr_adapter.process_audio(self.asr_session, frame_16k, captured_at_ns)
            if event is not None and event.text.strip():
                evidence = speech_evidence(vad_result, self._current_max_queue_age_ms)
                decision = self.guard.evaluate(event.text, evidence, event.model_info)
                if decision.accepted:
                    self._emit_event({
                        "type": "asr_partial", "direction": "outgoing", "text": event.text,
                        "sequence_id": event.sequence_id, "revision": event.revision,
                        "timestamp_ns": captured_at_ns,
                    })
                    commit = self.commit_controller.evaluate(event.text, now_ms=time.monotonic() * 1000.0)
                    # Without word timestamps, committing a prefix while discarding
                    # its remainder loses speech. Defer split hypotheses to endpoint.
                    if commit.should_commit and not commit.remaining_partial_text:
                        self._handle_commit(commit.committed_text, event.audio_start_ns, captured_at_ns, event.model_info)
                elif decision.reason in {
                    "known_hallucination_pattern", "repetitive_text", "whisper_no_speech",
                    "whisper_low_logprob", "whisper_repetition", "stale_audio",
                }:
                    self._note_rejection(decision.reason, event.text)
            return

        if vad_result.transition == "ended" and self._in_speech:
            self._in_speech = False
            final_event = self.asr_adapter.flush_session(self.asr_session)
            if final_event is not None and final_event.text.strip():
                self._handle_commit(
                    final_event.text,
                    final_event.audio_start_ns,
                    captured_at_ns,
                    final_event.model_info,
                )
            else:
                self._reject_current("no_asr_text", "")
            self.commit_controller.reset()
            reset_asr_utterance(self.asr_session)
            self.vad.reset()
            self._current_max_queue_age_ms = 0.0
            return

        self._preroll.append(frame_16k)

    def _handle_commit(self, text: str, audio_start_ns: int, audio_end_ns: int, model_info: dict) -> bool:
        evidence = speech_evidence(self._last_vad_result, self._current_max_queue_age_ms)
        decision = self.guard.evaluate(text, evidence, model_info)
        if not decision.accepted:
            self._reject_current(decision.reason, text)
            return False
        accepted_info = dict(model_info)
        accepted_info.update({"speech_evidence_accepted": True, "speech_evidence": asdict(evidence)})
        assert self.asr_session is not None
        event = UtteranceEvent(
            meeting_id=self.meeting_id, stream_id=self.asr_session.stream_id,
            direction=Direction.OUTGOING,
            utterance_id=f"{self.asr_session.stream_id}_{self._sequence_counter}",
            sequence_id=self._sequence_counter, revision=1, state=UtteranceState.COMMITTED,
            source_language="tr", text=text.strip(), audio_start_ns=audio_start_ns,
            audio_end_ns=audio_end_ns, is_final=True, model_info=accepted_info,
        )
        self._sequence_counter += 1
        self.asr_session.sequence_id = self._sequence_counter
        reset_asr_utterance(self.asr_session)
        self.commit_controller.reset()
        self._submit_queue(self.committed_queue, event, "outgoing_committed")
        self._emit_event({
            "type": "asr_committed", "direction": "outgoing", "text": event.text,
            "sequence_id": event.sequence_id, "timestamp_ns": time.monotonic_ns(),
        })
        return True

    def _reject_current(self, reason: str, text: str) -> None:
        self._note_rejection(reason, text)
        reset_asr_utterance(self.asr_session)
        self.commit_controller.reset()

    def _note_rejection(self, reason: str, text: str) -> None:
        self._last_rejection = {"reason": reason, "text": text, "timestamp_ns": time.monotonic_ns()}
        self._emit_event({"type": "asr_rejected", "direction": "outgoing", **self._last_rejection})

    def _submit_queue(self, queue: BoundedQueue, item, name: str) -> None:
        if self._loop is None or not self._loop.is_running():
            self._overloaded = True
            return
        future = asyncio.run_coroutine_threadsafe(queue.put(item), self._loop)

        def _done(done_future) -> None:
            try:
                accepted = done_future.result()
            except Exception as exc:
                accepted = False
                logger.error("%s queue submission failed: %s", name, exc)
            if not accepted:
                self._overloaded = True
                self._emit_event({"type": "queue_overload", "queue": name, "direction": "outgoing"})

        future.add_done_callback(_done)

    async def _mt_worker(self) -> None:
        while self.is_running:
            event = await self.committed_queue.get()
            t0 = time.monotonic_ns()
            translated = await asyncio.to_thread(self.mt_adapter.translate_event, event, self.target_language)
            t1 = time.monotonic_ns()
            self._record_latency(event, "mt_duration", t1, (t1 - t0) / 1e6)
            self._emit_event({
                "type": "mt_committed", "direction": "outgoing",
                "source_text": translated.source_text, "translated_text": translated.translated_text,
                "sequence_id": translated.sequence_id, "timestamp_ns": t1,
            })
            if not await self.tts_queue.put(translated):
                self._overloaded = True
                self._emit_event({"type": "queue_overload", "queue": "outgoing_tts", "direction": "outgoing"})

    async def _tts_worker(self) -> None:
        while self.is_running:
            event = await self.tts_queue.get()
            if (
                event.state != UtteranceState.COMMITTED
                or not event.model_info.get("speech_evidence_accepted")
                or not event.translated_text.strip()
                or self.guard.is_known_pattern(event.translated_text)
            ):
                self._emit_event({"type": "tts_rejected", "direction": "outgoing", "sequence_id": event.sequence_id})
                continue
            t0 = time.monotonic_ns()
            iterator = self.tts_adapter.synthesize_committed(event.translated_text, self.voice_profile, self.target_language)
            first_pcm = True
            pcm_routed = False
            while self.is_running:
                has_chunk, pcm = await asyncio.to_thread(next_pcm_chunk, iterator)
                if not has_chunk:
                    break
                now_ns = time.monotonic_ns()
                if first_pcm:
                    first_pcm = False
                    self._record_latency(event, "tts_first_pcm", now_ns, (now_ns - t0) / 1e6)
                if self.render_engine is not None:
                    source_rate = int(getattr(self.tts_adapter, "sample_rate", self.config.tts.sample_rate))
                    self.render_engine.push_pcm(pcm, source_rate=source_rate)
                    if not pcm_routed:
                        self._emit_event({
                            "type": "tts_started", "direction": "outgoing",
                            "source_text": event.source_text,
                            "translated_text": event.translated_text,
                            "sequence_id": event.sequence_id,
                            "timestamp_ns": now_ns,
                        })
                        # Event means first PCM reached bounded render path, once.
                        pcm_routed = True
            if not pcm_routed:
                self._emit_event({
                    "type": "tts_rejected", "direction": "outgoing",
                    "sequence_id": event.sequence_id,
                    "reason": "no_pcm" if first_pcm else "render_unavailable",
                })
            if self.render_engine is not None:
                source_rate = int(getattr(self.tts_adapter, "sample_rate", self.config.tts.sample_rate))
                self.render_engine.flush_source(source_rate)

    def _record_latency(self, event, event_type: str, now_ns: int, duration_ms: float) -> None:
        if self.on_latency_callback:
            self.on_latency_callback(LatencyEvent(
                meeting_id=self.meeting_id, utterance_id=event.utterance_id,
                direction=Direction.OUTGOING, event_type=event_type,
                monotonic_ns=now_ns, duration_ms=duration_ms,
            ))

    def get_diagnostics(self) -> dict:
        vad = asdict(self._last_vad_result)
        return {
            "direction": "outgoing", "asr_state": vad["phase"], "vad": vad,
            "last_rejection": self._last_rejection, "overloaded": self._overloaded,
            "audio_dropped_samples": self._dropped_audio_samples,
            "max_audio_queue_age_ms": self._max_queue_age_seen_ms,
            "capture": self.capture_engine.get_diagnostics() if self.capture_engine else None,
            "render": self.render_engine.get_diagnostics() if self.render_engine else None,
            "queues": [
                self.committed_queue.snapshot("outgoing_committed", "reject_new"),
                self.tts_queue.snapshot("outgoing_tts", "reject_new"),
            ],
        }

    def _emit_event(self, data: dict) -> None:
        if self.on_event_callback:
            try:
                self.on_event_callback(data)
            except Exception:
                logger.debug("Outgoing event subscriber failed", exc_info=True)

    async def stop(self) -> None:
        self.is_running = False
        if self.capture_engine:
            self.capture_engine.stop()
        if self.render_engine:
            self.render_engine.stop()
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self.asr_session:
            self.asr_adapter.close_session(self.asr_session)
        self.capture_engine = None
        self.render_engine = None
        self.asr_session = None
        logger.info("Outgoing pipeline stopped.")

    def set_voice_profile(self, profile: VoiceProfile) -> None:
        self.voice_profile = profile
        logger.info("Outgoing pipeline voice profile updated to '%s' (%s)", profile.display_name, profile.id)

    def set_target_language(self, target_language: str) -> None:
        self.target_language = target_language.lower().strip()
        logger.info("Outgoing pipeline target language updated to '%s'", self.target_language)
