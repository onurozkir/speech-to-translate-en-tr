"""Commit Controller for stable-prefix and semantic boundary commits."""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Tuple

from teams_translator.core.types import UtteranceEvent, UtteranceState


@dataclass
class CommitDecision:
    should_commit: bool
    committed_text: str
    remaining_partial_text: str
    reason: str  # "punctuation", "stable_prefix", "silence_endpoint", "deadline_timeout"


class CommitController:
    """Manages irreversible commit decisions from streaming ASR hypotheses."""

    def __init__(
        self,
        min_words: int = 3,
        max_wait_ms: int = 1800,
        stable_prefix_min_count: int = 2,
    ):
        self.min_words = min_words
        self.max_wait_ms = max_wait_ms
        self.stable_prefix_min_count = stable_prefix_min_count

        self.last_hypotheses: List[str] = []
        self.first_hypothesis_time_ms: float = 0
        self.stable_prefix_candidate = ""
        self.stable_prefix_matches = 0

        # Punctuation / conjunction clause delimiters
        self._punct_regex = re.compile(r'([.?!;:]+)(\s+|$)', re.UNICODE)
        self._conjunction_regex = re.compile(r'(\s+(?:ve|veya|ama|fakat|ancak|çünkü|ise|ki|böylece)\s+)', re.IGNORECASE | re.UNICODE)

    def reset(self):
        self.last_hypotheses.clear()
        self.first_hypothesis_time_ms = 0
        self.stable_prefix_candidate = ""
        self.stable_prefix_matches = 0

    def evaluate(
        self,
        current_text: str,
        is_silence_endpoint: bool = False,
        now_ms: Optional[float] = None,
    ) -> CommitDecision:
        current_text = current_text.strip()
        if not current_text:
            return CommitDecision(False, "", "", "empty")

        now = now_ms or (time.monotonic() * 1000.0)
        if self.first_hypothesis_time_ms == 0:
            self.first_hypothesis_time_ms = now

        words = current_text.split()
        elapsed_wait_ms = now - self.first_hypothesis_time_ms

        # 1. Silence Endpoint flush
        if is_silence_endpoint:
            self.reset()
            return CommitDecision(
                should_commit=True,
                committed_text=current_text,
                remaining_partial_text="",
                reason="silence_endpoint",
            )

        # 2. Punctuation boundary check (e.g. "Merhaba nasılsınız? Bugün...")
        punct_match = self._punct_regex.search(current_text)
        if punct_match:
            split_idx = punct_match.end()
            committed = current_text[:split_idx].strip()
            remainder = current_text[split_idx:].strip()
            if len(committed.split()) >= self.min_words or is_silence_endpoint:
                self.reset()
                return CommitDecision(
                    should_commit=True,
                    committed_text=committed,
                    remaining_partial_text=remainder,
                    reason="punctuation",
                )

        # 3. Stable prefix detection across consecutive revisions
        self.last_hypotheses.append(current_text)
        if len(self.last_hypotheses) > 5:
            self.last_hypotheses.pop(0)

        if len(self.last_hypotheses) >= 2:
            common_prefix = self._longest_common_word_prefix(self.last_hypotheses[-2], self.last_hypotheses[-1])
            prefix_words = common_prefix.split()
            if len(prefix_words) >= self.min_words:
                if self._comparison_key(common_prefix) == self._comparison_key(self.stable_prefix_candidate):
                    self.stable_prefix_matches += 1
                else:
                    self.stable_prefix_candidate = common_prefix
                    self.stable_prefix_matches = 1

                if self.stable_prefix_matches >= self.stable_prefix_min_count:
                    # Check for conjunction boundary within stable prefix
                    conj_match = self._conjunction_regex.search(common_prefix)
                    if conj_match:
                        split_idx = conj_match.start()
                        committed = common_prefix[:split_idx].strip()
                        remainder = current_text[len(committed):].strip()
                        if len(committed.split()) >= self.min_words:
                            self.reset()
                            return CommitDecision(
                                should_commit=True,
                                committed_text=committed,
                                remaining_partial_text=remainder,
                                reason="stable_prefix_clause",
                            )
            else:
                self.stable_prefix_candidate = ""
                self.stable_prefix_matches = 0

        # 4. Max wait deadline timeout
        if elapsed_wait_ms >= self.max_wait_ms and len(words) >= self.min_words:
            committed, remainder = self._deadline_safe_split(current_text)
            if committed:
                self.reset()
                return CommitDecision(
                    should_commit=True,
                    committed_text=committed,
                    remaining_partial_text=remainder,
                    reason="deadline_timeout",
                )

        return CommitDecision(
            should_commit=False,
            committed_text="",
            remaining_partial_text=current_text,
            reason="buffering_partial",
        )

    def _longest_common_word_prefix(self, s1: str, s2: str) -> str:
        w1 = s1.split()
        w2 = s2.split()
        common = []
        for a, b in zip(w1, w2):
            if self._comparison_key(a) == self._comparison_key(b):
                common.append(a)
            else:
                break
        return " ".join(common)

    @staticmethod
    def _comparison_key(text: str) -> str:
        normalized = unicodedata.normalize("NFKC", " ".join(text.split())).casefold()
        return normalized.replace("i\u0307", "i")

    def _deadline_safe_split(self, current_text: str) -> Tuple[str, str]:
        """Return only text supported by stable revisions or a clause boundary."""
        stable_words = self.stable_prefix_candidate.split()
        current_words = current_text.split()
        if (
            len(stable_words) >= self.min_words
            and len(current_words) >= len(stable_words)
            and all(self._comparison_key(a) == self._comparison_key(b) for a, b in zip(stable_words, current_words))
        ):
            split_at = len(stable_words)
            return " ".join(current_words[:split_at]), " ".join(current_words[split_at:])

        boundaries = [match.end() for match in self._punct_regex.finditer(current_text)]
        boundaries.extend(match.start() for match in self._conjunction_regex.finditer(current_text))
        for split_idx in sorted(boundaries, reverse=True):
            committed = current_text[:split_idx].strip()
            if len(committed.split()) >= self.min_words:
                return committed, current_text[split_idx:].strip()
        return "", current_text
