"""Translation Adapter Layer."""

from teams_translator.translation.base import MTAdapter
from teams_translator.translation.ctranslate_backend import CTranslate2MTAdapter
from teams_translator.translation.mock_backend import MockMTAdapter

__all__ = ["MTAdapter", "CTranslate2MTAdapter", "MockMTAdapter"]

