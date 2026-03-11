"""token_manager.py — rotate GitHub tokens from .env, handle rate limits"""

import os
import time
import threading
from dataclasses import dataclass
from config import cfg
from logger import get_logger

log = get_logger("tokens")


@dataclass
class Token:
    value: str
    label: str
    remaining: int = 5000
    reset_at: float = 0.0

    def exhausted(self) -> bool:
        return self.remaining < cfg.min_remaining

    def wait_seconds(self) -> float:
        return max(0.0, self.reset_at - time.time())


class TokenManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._tokens: list[Token] = []

        # Load tokens from GITHUB_TOKENS env var (set in .env file)
        env_tokens = os.environ.get("GITHUB_TOKENS", "").strip()
        if not env_tokens:
            raise ValueError(
                "GITHUB_TOKENS environment variable is not set.\n"
                "Set it in your .env file:\n"
                "  GITHUB_TOKENS=ghp_xxx,ghp_yyy,ghp_zzz\n"
                "Or export it directly:\n"
                "  export GITHUB_TOKENS=ghp_xxx"
            )

        lines = [t.strip() for t in env_tokens.split(",") if t.strip()]
        if not lines:
            raise ValueError(
                "GITHUB_TOKENS is set but contains no valid tokens.\n"
                "Format: GITHUB_TOKENS=ghp_xxx,ghp_yyy"
            )

        for i, v in enumerate(lines, 1):
            self._tokens.append(Token(value=v, label=f"token-{i}"))

        log.info(f"Loaded {len(self._tokens)} token(s) from GITHUB_TOKENS env var")

    def headers(self) -> tuple[dict, Token]:
        """Return (headers, token). Blocks if all exhausted."""
        with self._lock:
            token = self._pick()
            return {
                "Authorization": f"Bearer {token.value}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }, token

    def _pick(self) -> Token:
        available = [t for t in self._tokens if not t.exhausted()]
        if available:
            return max(available, key=lambda t: t.remaining)

        soonest = min(self._tokens, key=lambda t: t.reset_at)
        wait = soonest.wait_seconds() + 5
        log.warning(f"All tokens exhausted, sleeping {wait:.0f}s until reset...")
        time.sleep(wait)
        for t in self._tokens:
            t.remaining = 5000
        return self._tokens[0]

    def update(self, headers: dict, token: Token) -> None:
        with self._lock:
            remaining = headers.get("X-RateLimit-Remaining")
            if remaining:
                token.remaining = int(remaining)
            reset = headers.get("X-RateLimit-Reset")
            if reset:
                token.reset_at = float(reset)

    def status(self) -> str:
        return " | ".join(f"{t.label}:{t.remaining}" for t in self._tokens)
