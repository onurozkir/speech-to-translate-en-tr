"""Configuration module for Teams Translator."""

from teams_translator.config.loader import load_config
from teams_translator.config.models import AppConfig

__all__ = ["AppConfig", "load_config"]

