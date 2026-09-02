"""Speaker conditioning cache and voice profile manager."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from teams_translator.tts.base import VoiceProfile

logger = logging.getLogger(__name__)


class VoiceProfileManager:
    """Discovers and caches voice cloning profiles on disk."""

    def __init__(self, profiles_root: str = "voices"):
        self.profiles_root = Path(profiles_root)
        self.profiles: Dict[str, VoiceProfile] = {}
        self.load_profiles()

    def load_profiles(self):
        self.profiles.clear()
        if not self.profiles_root.exists():
            self.profiles_root.mkdir(parents=True, exist_ok=True)
            return

        for profile_dir in self.profiles_root.iterdir():
            if profile_dir.is_dir():
                manifest_file = profile_dir / "profile.json"
                if manifest_file.exists():
                    try:
                        with open(manifest_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        
                        profile_id = data.get("id", profile_dir.name)
                        ref_audio = data.get("reference_audio_path", "reference.wav")
                        # Resolve audio path relative to profile dir if not absolute
                        ref_audio_path = Path(ref_audio)
                        if not ref_audio_path.is_absolute():
                            ref_audio_path = profile_dir / ref_audio

                        cache_dir = profile_dir / "cache"
                        cache_dir.mkdir(exist_ok=True)

                        target_langs = data.get("target_languages")
                        if not target_langs:
                            target_langs = [data.get("target_language", "en")]
                        elif isinstance(target_langs, str):
                            target_langs = [target_langs]

                        prof = VoiceProfile(
                            id=profile_id,
                            display_name=data.get("display_name", profile_id),
                            backend=data.get("backend", "xtts_v2"),
                            reference_audio_path=str(ref_audio_path.resolve()),
                            reference_text=data.get("reference_text"),
                            reference_language=data.get("reference_language", "tr"),
                            target_language=data.get("target_language", target_langs[0] if target_langs else "en"),
                            target_languages=target_langs,
                            is_default=bool(data.get("is_default", False)),
                            conditioning_cache_path=str(cache_dir.resolve()),
                            metadata=data.get("metadata", {}),
                        )
                        self.profiles[profile_id] = prof
                    except Exception as e:
                        logger.error(f"Failed to load profile manifest '{manifest_file}': {e}")

    def get_default_profile(self) -> Optional[VoiceProfile]:
        for prof in self.profiles.values():
            if prof.is_default:
                return prof
        if self.profiles:
            return next(iter(self.profiles.values()))
        return None

    def get_profile(self, profile_id: str) -> Optional[VoiceProfile]:
        return self.profiles.get(profile_id)

    def list_profiles(self) -> List[VoiceProfile]:
        return list(self.profiles.values())

    @staticmethod
    def compute_audio_hash(audio_path: str) -> str:
        """Compute SHA256 of reference audio file for cache keying."""
        p = Path(audio_path)
        if not p.exists():
            return ""
        hasher = hashlib.sha256()
        with open(p, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

