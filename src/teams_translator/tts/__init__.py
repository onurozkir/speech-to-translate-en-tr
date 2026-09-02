"""TTS and Voice Cloning Layer."""

from teams_translator.tts.base import TTSAdapter, VoiceProfile
from teams_translator.tts.conditioning import VoiceProfileManager
from teams_translator.tts.mock_backend import MockTTSAdapter
from teams_translator.tts.xtts_backend import XTTSv2Adapter

__all__ = [
    "TTSAdapter",
    "VoiceProfile",
    "VoiceProfileManager",
    "XTTSv2Adapter",
    "MockTTSAdapter",
]

