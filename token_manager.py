"""token_manager.py — rotate GitHub tokens, handle rate limits"""

import time
import threading
from dataclasses import dataclass, field
from config import cfg


@dataclass
class Token:
    value: str
    label: str
    remaining: int = 5000
    reset_at: float = 0.0

    def exhausted(self):
        return self.remaining < cfg.min_remaining

    def wait_seconds(self):
        return max(0.0, self.reset_at - time.time())


class TokenManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._tokens: list[Token] = []
        with open(cfg.token_file) as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        if not lines:
            raise ValueError(f"No tokens in {cfg.token_file}")
        for i, v in enumerate(lines, 1):
            self._tokens.append(Token(value=v, label=f"token-{i}"))
        print(f"[tokens] loaded {len(self._tokens)} token(s)")

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
        print(f"[tokens] all exhausted, sleeping {wait:.0f}s...")
        time.sleep(wait)
        for t in self._tokens:
            t.remaining = 5000
        return self._tokens[0]

    def update(self, headers: dict, token: Token):
        with self._lock:
            if r := headers.get("X-RateLimit-Remaining"):
                token.remaining = int(r)
            if r := headers.get("X-RateLimit-Reset"):
                token.reset_at = float(r)

    def status(self):
        return " | ".join(f"{t.label}:{t.remaining}" for t in self._tokens)
