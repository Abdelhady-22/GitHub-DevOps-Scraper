"""config.py — load scraper_config.yaml with validation and .env support"""

import os
import yaml
from pathlib import Path
from dataclasses import dataclass
from logger import get_logger

log = get_logger("config")

# Load .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
    log.debug(".env file loaded")
except ImportError:
    pass


def _load() -> dict:
    p = Path(__file__).parent / "scraper_config.yaml"
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass
class Repo:
    owner: str
    repo: str
    bug_labels: str
    exclude_labels: list
    category: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def slug(self) -> str:
        return f"{self.owner}_{self.repo}"


_REQUIRED_SECTIONS = ["repos", "tokens", "discovery", "enrichment", "classification", "llm", "output", "run_phases"]

_REQUIRED_KEYS = {
    "tokens": ["file", "min_remaining", "request_delay"],
    "discovery": ["since", "min_body_length", "title_reject_prefixes", "title_reject_words", "bot_logins"],
    "enrichment": ["checkpoint_every"],
    "classification": ["batch_size", "llm_min_confidence", "min_body_score", "open_min_comments", "open_min_reactions", "title_negative_words"],
    "llm": ["provider", "min_extraction_confidence", "max_body_chars", "max_pr_body_chars"],
    "output": ["raw_dir", "staging_dir", "processed_dir", "progress_file"],
}


def _validate(raw: dict) -> None:
    """Validate config structure and raise clear errors for missing keys."""
    for section in _REQUIRED_SECTIONS:
        if section not in raw:
            raise ValueError(f"Missing required config section: '{section}'")

    for section, keys in _REQUIRED_KEYS.items():
        for key in keys:
            if key not in raw[section]:
                raise ValueError(f"Missing required config key: '{section}.{key}'")

    provider = raw["llm"]["provider"]
    if provider not in ("ollama", "openai", "anthropic"):
        raise ValueError(f"Invalid llm.provider: '{provider}'. Must be ollama, openai, or anthropic.")

    if provider == "ollama":
        for k in ["ollama_base_url", "ollama_classification_model", "ollama_extraction_model"]:
            if k not in raw["llm"]:
                raise ValueError(f"Provider is 'ollama' but '{k}' is missing from llm config.")
    elif provider == "openai":
        for k in ["openai_classification_model", "openai_extraction_model"]:
            if k not in raw["llm"]:
                raise ValueError(f"Provider is 'openai' but '{k}' is missing from llm config.")
    elif provider == "anthropic":
        for k in ["anthropic_classification_model", "anthropic_extraction_model"]:
            if k not in raw["llm"]:
                raise ValueError(f"Provider is 'anthropic' but '{k}' is missing from llm config.")

    if not raw.get("repos"):
        raise ValueError("No repos configured. Add at least one repo to 'repos' section.")

    log.debug("Config validation passed")


class Config:
    def __init__(self, raw: dict):
        _validate(raw)
        self._r = raw
        self.repos = [Repo(**{k: v for k, v in r.items()}) for r in raw["repos"]]

    # tokens
    @property
    def token_file(self) -> str:
        return self._r["tokens"]["file"]

    @property
    def min_remaining(self) -> int:
        return self._r["tokens"]["min_remaining"]

    @property
    def request_delay(self) -> float:
        return self._r["tokens"]["request_delay"]

    # discovery
    @property
    def since(self) -> str:
        return self._r["discovery"]["since"]

    @property
    def min_body_length(self) -> int:
        return self._r["discovery"]["min_body_length"]

    @property
    def title_reject_prefixes(self) -> list[str]:
        return self._r["discovery"]["title_reject_prefixes"]

    @property
    def title_reject_words(self) -> list[str]:
        return self._r["discovery"]["title_reject_words"]

    @property
    def bot_logins(self) -> set[str]:
        return set(self._r["discovery"]["bot_logins"])

    # enrichment
    @property
    def checkpoint_every(self) -> int:
        return self._r["enrichment"]["checkpoint_every"]

    # classification
    @property
    def batch_size(self) -> int:
        return self._r["classification"]["batch_size"]

    @property
    def llm_min_confidence(self) -> float:
        return self._r["classification"]["llm_min_confidence"]

    @property
    def min_body_score(self) -> int:
        return self._r["classification"]["min_body_score"]

    @property
    def open_min_comments(self) -> int:
        return self._r["classification"]["open_min_comments"]

    @property
    def open_min_reactions(self) -> int:
        return self._r["classification"]["open_min_reactions"]

    @property
    def title_negative_words(self) -> list[str]:
        return self._r["classification"]["title_negative_words"]

    # llm
    @property
    def llm_provider(self) -> str:
        return self._r["llm"]["provider"]

    @property
    def min_extraction_confidence(self) -> int:
        return self._r["llm"]["min_extraction_confidence"]

    @property
    def max_body_chars(self) -> int:
        return self._r["llm"]["max_body_chars"]

    @property
    def max_pr_body_chars(self) -> int:
        return self._r["llm"]["max_pr_body_chars"]

    @property
    def ollama_base_url(self) -> str:
        return self._r["llm"].get("ollama_base_url", "http://localhost:11434")

    def classification_model(self) -> str:
        p = self.llm_provider
        if p == "ollama":
            return self._r["llm"]["ollama_classification_model"]
        if p == "openai":
            return self._r["llm"]["openai_classification_model"]
        if p == "anthropic":
            return self._r["llm"]["anthropic_classification_model"]
        raise ValueError(f"Unknown provider: {p}")

    def extraction_model(self) -> str:
        p = self.llm_provider
        if p == "ollama":
            return self._r["llm"]["ollama_extraction_model"]
        if p == "openai":
            return self._r["llm"]["openai_extraction_model"]
        if p == "anthropic":
            return self._r["llm"]["anthropic_extraction_model"]
        raise ValueError(f"Unknown provider: {p}")

    # output
    @property
    def raw_dir(self) -> Path:
        return Path(self._r["output"]["raw_dir"])

    @property
    def staging_dir(self) -> Path:
        return Path(self._r["output"]["staging_dir"])

    @property
    def processed_dir(self) -> Path:
        return Path(self._r["output"]["processed_dir"])

    @property
    def progress_file(self) -> str:
        return self._r["output"]["progress_file"]

    def phase_enabled(self, phase: str) -> bool:
        return self._r["run_phases"].get(phase, True)

    def get_repo(self, full_name: str):
        for r in self.repos:
            if r.full_name == full_name:
                return r
        return None


cfg = Config(_load())
