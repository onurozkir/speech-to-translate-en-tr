"""Full-duplex Meeting Orchestrator and lifecycle coordinator."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Callable, Dict, List, Optional

from teams_translator.asr.base import ASRAdapter, ASRSession
from teams_translator.asr.mock_backend import MockASRAdapter
from teams_translator.asr.whisper_backend import WhisperASRAdapter
from teams_translator.audio.devices import AudioDeviceManager, DeviceInfo
from teams_translator.config.models import AppConfig
from teams_translator.core.types import LatencyEvent, MeetingStatus
from teams_translator.persistence.database import PersistenceWorker
from teams_translator.streaming.pipeline_incoming import IncomingPipeline
from teams_translator.streaming.pipeline_outgoing import OutgoingPipeline
from teams_translator.telemetry.metrics import TelemetryTracker
from teams_translator.translation.base import MTAdapter
from teams_translator.translation.ctranslate_backend import CTranslate2MTAdapter
from teams_translator.translation.mock_backend import MockMTAdapter
from teams_translator.tts.base import TTSAdapter, VoiceProfile
from teams_translator.tts.conditioning import VoiceProfileManager
from teams_translator.tts.mock_backend import MockTTSAdapter
from teams_translator.tts.xtts_backend import XTTSv2Adapter

logger = logging.getLogger(__name__)


class MeetingOrchestrator:
    """Coordinates hardware devices, adapters, outgoing and incoming pipelines."""

    def __init__(self, config: AppConfig, use_mocks: bool = False):
        self.config = config
        self.use_mocks = use_mocks
        self.status = MeetingStatus.STOPPED
        self.current_meeting_id: Optional[str] = None

        self.device_manager = AudioDeviceManager()
        self.profile_manager = VoiceProfileManager(config.voice.profiles_root)
        self.telemetry = TelemetryTracker(window_size=config.telemetry.window_size)
        self.persistence = PersistenceWorker(config.persistence)

        self.asr_adapter: Optional[ASRAdapter] = None
        self.mt_adapter: Optional[MTAdapter] = None
        self.tts_adapter: Optional[TTSAdapter] = None

        self.outgoing_pipeline: Optional[OutgoingPipeline] = None
        self.incoming_pipeline: Optional[IncomingPipeline] = None

        self.event_subscribers: List[Callable[[dict], None]] = []
        self.resolved_devices: Dict[str, Optional[dict]] = {
            "physical_mic": None,
            "physical_speaker": None,
            "speaker_loopback": None,
            "vb_cable_render": None,
            "vb_cable_capture": None,
        }
        self.last_start_error: Optional[str] = None
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None

    def subscribe_events(self, callback: Callable[[dict], None]):
        self.event_subscribers.append(callback)

    def _broadcast_event(self, data: dict):
        for sub in self.event_subscribers:
            try:
                sub(data)
            except Exception:
                pass

    def _on_latency_event(self, event: LatencyEvent):
        self.telemetry.record_event(event)
        self.persistence.record_latency(event)
        self._broadcast_event({
            "type": "latency_update",
            "metrics": self.telemetry.get_snapshot(),
        })

    def _on_asr_inference_wait(self, session: ASRSession, sample: dict) -> None:
        meeting_id = str(session.metadata.get("meeting_id") or self.current_meeting_id or "local_session")
        event = LatencyEvent(
            meeting_id=meeting_id,
            utterance_id=f"{session.stream_id}_{session.sequence_id}",
            direction=session.direction,
            event_type="asr_inference_wait",
            monotonic_ns=time.monotonic_ns(),
            duration_ms=float(sample["wait_ms"]),
            metadata={
                "stream_id": session.stream_id,
                "queue_depth": int(sample["queue_depth"]),
                "deadline_miss_ms": float(sample["deadline_miss_ms"]),
                "is_final": bool(sample["is_final"]),
            },
        )
        if self._event_loop is not None and self._event_loop.is_running():
            self._event_loop.call_soon_threadsafe(self._on_latency_event, event)
        else:
            self._on_latency_event(event)

    async def initialize_and_warmup(self):
        """Initializes and warms all models before marking READY."""
        self._event_loop = asyncio.get_running_loop()
        self.last_start_error = None
        self.status = MeetingStatus.STARTING
        self._broadcast_status()

        try:
            logger.info("Initializing adapters...")
            if self.use_mocks:
                self.asr_adapter = MockASRAdapter()
                self.mt_adapter = MockMTAdapter()
                self.tts_adapter = MockTTSAdapter()
            else:
                self.asr_adapter = WhisperASRAdapter(
                    partial_interval_ms=self.config.asr.partial_interval_ms,
                    min_audio_rms=self.config.asr.min_audio_rms,
                    beam_size=self.config.asr.beam_size,
                    on_inference_wait=self._on_asr_inference_wait,
                )
                self.mt_adapter = CTranslate2MTAdapter(
                    beam_size=self.config.translation.beam_size,
                )
                self.tts_adapter = XTTSv2Adapter(
                    temperature=self.config.tts.temperature,
                    speed=self.config.tts.speed,
                )

            # Initialize models offline
            self.asr_adapter.initialize(
                model_path=self.config.asr.model_path,
                device=self.config.asr.device,
                compute_type=self.config.asr.compute_type,
            )
            self.mt_adapter.initialize(
                tr_en_model_path=self.config.translation.tr_en_model_path,
                en_tr_model_path=self.config.translation.en_tr_model_path,
                tr_fr_model_path=getattr(self.config.translation, "tr_fr_model_path", None),
                nllb_model_path=getattr(self.config.translation, "nllb_model_path", None) if getattr(self.config.translation, "model_type", "auto") == "nllb" else None,
                device=self.config.translation.device,
                compute_type=self.config.translation.compute_type,
            )
            self.tts_adapter.initialize(
                model_path=self.config.tts.model_path,
                device=self.config.tts.device,
                sample_rate=self.config.tts.sample_rate,
            )

            self.status = MeetingStatus.WARMING
            self._broadcast_status()
            logger.info("Warming up models...")

            # Model warming (hard invariant before READY)
            self.asr_adapter.warmup()
            self.mt_adapter.warmup()
            self.tts_adapter.warmup()

            # Warm voice profile
            default_profile = self.profile_manager.get_default_profile()
            if not self.use_mocks and default_profile is None:
                raise RuntimeError("No default voice profile is available for outgoing TTS.")
            if default_profile:
                self.tts_adapter.prepare_voice_profile(default_profile)

            await self.persistence.start()

            self.status = MeetingStatus.READY
            self._broadcast_status()
            logger.info("MeetingOrchestrator is READY.")
        except Exception as e:
            self.last_start_error = str(e)
            self.status = MeetingStatus.ERROR
            self._broadcast_status()
            logger.error(f"Failed to initialize models/adapters: {e}")
            raise

    async def start_meeting(
        self,
        mic_id: Optional[str] = None,
        loopback_id: Optional[str] = None,
        render_id: Optional[str] = None,
        voice_profile_id: Optional[str] = None,
        target_language: Optional[str] = "en",
        save_meeting: bool = False,
        context_prompt: Optional[str] = None,
    ):
        if context_prompt and context_prompt.strip():
            self.config.asr.initial_prompt = context_prompt.strip()

        if self.status != MeetingStatus.READY:
            if self.status == MeetingStatus.ERROR:
                raise RuntimeError(
                    self.last_start_error
                    or "Models failed to initialize or are missing. If models are not yet downloaded, launch with '--mock' (python src/teams_translator/main.py run --mock) or download models manually."
                )
            if self.status in (MeetingStatus.STARTING, MeetingStatus.WARMING):
                raise RuntimeError("Models are still warming up. Please wait for the READY status.")
            if self.status == MeetingStatus.RUNNING:
                raise RuntimeError("An active meeting session is already running.")
            raise RuntimeError(f"Cannot start meeting while status is '{self.status.value}'.")

        if not self.asr_adapter or not self.mt_adapter or not self.tts_adapter:
            raise RuntimeError("Adapters are not initialized. Please restart the service.")

        mic_selector = mic_id or self.config.audio.mic_device_id
        loop_selector = loopback_id or self.config.audio.loopback_device_id
        render_selector = render_id or self.config.audio.render_device_id

        mic_dev = None
        if mic_selector:
            try:
                mic_dev = self.device_manager.resolve_required(mic_selector, "mic")
            except ValueError as exc:
                logger.warning("Configured mic '%s' unavailable (%s). Falling back to default physical mic.", mic_selector, exc)
                mic_dev = self.device_manager.find_default_mic()
                if mic_dev is None:
                    raise
        else:
            mic_dev = self.device_manager.find_default_mic()

        loop_dev = None
        if loop_selector:
            try:
                loop_dev = self.device_manager.resolve_required(loop_selector, "loopback")
            except ValueError as exc:
                logger.warning("Configured loopback '%s' unavailable (%s). Falling back to default loopback.", loop_selector, exc)
                loop_dev = self.device_manager.find_default_loopback()
                if loop_dev is None:
                    raise
        else:
            loop_dev = self.device_manager.find_default_loopback()

        ren_dev = None
        if render_selector:
            try:
                ren_dev = self.device_manager.resolve_required(render_selector, "render")
            except ValueError as exc:
                logger.warning("Configured render '%s' unavailable (%s). Falling back to default VB-CABLE render.", render_selector, exc)
                ren_dev = self.device_manager.find_vbcable_render()
                if ren_dev is None:
                    raise
        else:
            ren_dev = self.device_manager.find_vbcable_render()
        speaker_dev = self.device_manager.find_render_for_loopback(loop_dev)
        cable_capture = self.device_manager.find_vbcable_capture()
        self.resolved_devices = {
            "physical_mic": mic_dev.to_dict() if mic_dev else None,
            "physical_speaker": speaker_dev.to_dict() if speaker_dev else None,
            "speaker_loopback": loop_dev.to_dict() if loop_dev else None,
            "vb_cable_render": ren_dev.to_dict() if ren_dev else None,
            "vb_cable_capture": cable_capture.to_dict() if cable_capture else None,
        }
        if not self.use_mocks and (not mic_dev or not loop_dev or not ren_dev):
            missing = [
                role for role, device in (("physical mic", mic_dev), ("speaker loopback", loop_dev), ("VB-CABLE render", ren_dev))
                if device is None
            ]
            raise RuntimeError("Required audio endpoints are missing: " + ", ".join(missing))

        self.current_meeting_id = f"m_{uuid.uuid4().hex[:8]}"
        self.last_start_error = None

        profile = self.profile_manager.get_profile(voice_profile_id or self.config.tts.voice_profile_id) or self.profile_manager.get_default_profile()
        if not self.use_mocks and profile is None:
            self.current_meeting_id = None
            raise RuntimeError("No valid voice profile is available for outgoing TTS.")
        if not self.use_mocks:
            try:
                self.tts_adapter.prepare_voice_profile(profile)
            except Exception as exc:
                self.last_start_error = str(exc)
                self.current_meeting_id = None
                raise

        # Outgoing Pipeline
        if mic_dev and ren_dev:
            self.outgoing_pipeline = OutgoingPipeline(
                meeting_id=self.current_meeting_id,
                mic_device=mic_dev,
                render_device=ren_dev,
                asr_adapter=self.asr_adapter,
                mt_adapter=self.mt_adapter,
                tts_adapter=self.tts_adapter,
                voice_profile=profile,
                config=self.config,
                on_event_callback=self._broadcast_event,
                on_latency_callback=self._on_latency_event,
            )
            if target_language:
                self.outgoing_pipeline.set_target_language(target_language)
            try:
                await self.outgoing_pipeline.start()
            except Exception as exc:
                self.last_start_error = str(exc)
                self.outgoing_pipeline = None
                self.current_meeting_id = None
                self.status = MeetingStatus.READY
                self._broadcast_status()
                raise

        # Incoming Pipeline
        if loop_dev:
            self.incoming_pipeline = IncomingPipeline(
                meeting_id=self.current_meeting_id,
                loopback_device=loop_dev,
                asr_adapter=self.asr_adapter,
                mt_adapter=self.mt_adapter,
                config=self.config,
                on_event_callback=self._broadcast_event,
                on_latency_callback=self._on_latency_event,
            )
            try:
                await self.incoming_pipeline.start()
            except Exception as exc:
                self.last_start_error = str(exc)
                if self.outgoing_pipeline:
                    await self.outgoing_pipeline.stop()
                    self.outgoing_pipeline = None
                self.incoming_pipeline = None
                self.current_meeting_id = None
                self.status = MeetingStatus.READY
                self._broadcast_status()
                raise

        self.status = MeetingStatus.RUNNING
        self._broadcast_status()
        logger.info(f"Meeting session '{self.current_meeting_id}' started.")

    def get_audio_diagnostics(self) -> dict:
        return {
            "status": self.status.value,
            "meeting_id": self.current_meeting_id,
            "configured": {
                "mic_device_id": self.config.audio.mic_device_id,
                "loopback_device_id": self.config.audio.loopback_device_id,
                "render_device_id": self.config.audio.render_device_id,
            },
            "resolved": self.resolved_devices,
            "last_start_error": self.last_start_error,
            "outgoing": self.outgoing_pipeline.get_diagnostics() if self.outgoing_pipeline else None,
            "incoming": self.incoming_pipeline.get_diagnostics() if self.incoming_pipeline else None,
        }

    async def stop_meeting(self):
        if self.outgoing_pipeline:
            await self.outgoing_pipeline.stop()
            self.outgoing_pipeline = None

        if self.incoming_pipeline:
            await self.incoming_pipeline.stop()
            self.incoming_pipeline = None

        self.status = MeetingStatus.READY
        self.current_meeting_id = None
        self._broadcast_status()
        logger.info("Meeting stopped.")

    def switch_voice_profile(self, profile_id: str) -> bool:
        profile = self.profile_manager.get_profile(profile_id)
        if not profile:
            raise RuntimeError(f"Voice profile '{profile_id}' not found.")
        if not self.use_mocks:
            if self.tts_adapter is None:
                raise RuntimeError("TTS adapter is not initialized.")
            self.tts_adapter.prepare_voice_profile(profile)
        if self.outgoing_pipeline:
            self.outgoing_pipeline.set_voice_profile(profile)
        logger.info("Switched active voice profile to '%s' (%s)", profile.display_name, profile_id)
        self._broadcast_event({
            "type": "profile_switched",
            "profile_id": profile_id,
            "display_name": profile.display_name,
        })
        return True

    def switch_target_language(self, target_language: str) -> bool:
        lang = target_language.lower().strip()
        if lang not in ("en", "fr"):
            raise RuntimeError(f"Target language '{target_language}' is not supported. Choose 'en' or 'fr'.")
        if self.outgoing_pipeline:
            self.outgoing_pipeline.set_target_language(lang)
        logger.info("Switched outgoing target language to '%s'", lang)
        self._broadcast_event({
            "type": "target_language_switched",
            "target_language": lang,
        })
        return True

    def _broadcast_status(self):
        self._broadcast_event({
            "type": "status_change",
            "status": self.status.value,
            "meeting_id": self.current_meeting_id,
            "error": self.last_start_error,
        })

    async def shutdown(self):
        await self.stop_meeting()
        await self.persistence.stop()
        if self.asr_adapter:
            self.asr_adapter.shutdown()
        if self.mt_adapter:
            self.mt_adapter.shutdown()
        if self.tts_adapter:
            self.tts_adapter.shutdown()
        self.device_manager.close()
        self._event_loop = None
        self.status = MeetingStatus.STOPPED
        logger.info("MeetingOrchestrator shut down completely.")
