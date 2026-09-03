"""REST API routes for Teams Translator."""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from teams_translator.streaming.orchestrator import MeetingOrchestrator
from teams_translator.telemetry.system import SystemResourceMonitor


class StartMeetingRequest(BaseModel):
    mic_id: Optional[str] = None
    loopback_id: Optional[str] = None
    render_id: Optional[str] = None
    voice_profile_id: Optional[str] = None
    target_language: Optional[str] = "en"
    save_meeting: bool = False
    prompt: Optional[str] = None


class SwitchVoiceRequest(BaseModel):
    profile_id: str


class SwitchLanguageRequest(BaseModel):
    target_language: str


def create_routes(orchestrator: MeetingOrchestrator) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/status")
    async def get_status():
        return {
            "status": orchestrator.status.value,
            "meeting_id": orchestrator.current_meeting_id,
            "error": orchestrator.last_start_error,
            "system": SystemResourceMonitor.get_stats(),
        }

    @router.get("/devices")
    async def get_devices():
        devices = orchestrator.device_manager.list_devices(wasapi_only=False)
        configured_mic = orchestrator.device_manager.find_by_identifier(orchestrator.config.audio.mic_device_id)
        configured_loopback = orchestrator.device_manager.find_by_identifier(orchestrator.config.audio.loopback_device_id)
        configured_render = orchestrator.device_manager.find_by_identifier(orchestrator.config.audio.render_device_id)
        return {
            "devices": [d.to_dict() for d in devices],
            "defaults": {
                "mic": getattr(configured_mic or orchestrator.device_manager.find_default_mic(), "stable_id", None),
                "loopback": getattr(configured_loopback or orchestrator.device_manager.find_default_loopback(), "stable_id", None),
                "render": getattr(configured_render or orchestrator.device_manager.find_vbcable_render(), "stable_id", None),
                "vb_capture": getattr(orchestrator.device_manager.find_vbcable_capture(), "stable_id", None),
            }
        }

    @router.get("/audio/diagnostics")
    async def get_audio_diagnostics():
        return orchestrator.get_audio_diagnostics()

    @router.get("/profiles")
    async def get_profiles():
        profiles = orchestrator.profile_manager.list_profiles()
        return {
            "profiles": [
                {
                    "id": p.id,
                    "display_name": p.display_name,
                    "backend": p.backend,
                    "is_default": p.is_default,
                    "reference_language": p.reference_language,
                    "target_language": p.target_language,
                    "target_languages": getattr(p, "target_languages", [p.target_language]),
                }
                for p in profiles
            ]
        }

    @router.post("/meeting/start")
    async def start_meeting(req: StartMeetingRequest):
        try:
            await orchestrator.start_meeting(
                mic_id=req.mic_id,
                loopback_id=req.loopback_id,
                render_id=req.render_id,
                voice_profile_id=req.voice_profile_id,
                target_language=req.target_language or "en",
                save_meeting=req.save_meeting,
                context_prompt=req.prompt,
            )
            return {"status": "ok", "meeting_id": orchestrator.current_meeting_id}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/meeting/switch_voice")
    async def switch_voice(req: SwitchVoiceRequest):
        try:
            orchestrator.switch_voice_profile(req.profile_id)
            return {"status": "ok", "profile_id": req.profile_id}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/meeting/switch_language")
    async def switch_language(req: SwitchLanguageRequest):
        try:
            orchestrator.switch_target_language(req.target_language)
            return {"status": "ok", "target_language": req.target_language}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/meeting/stop")
    async def stop_meeting():
        try:
            await orchestrator.stop_meeting()
            return {"status": "ok"}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/telemetry")
    async def get_telemetry():
        return orchestrator.telemetry.get_snapshot()

    return router
