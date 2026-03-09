"""config.py — load scraper_config.yaml, used by all scripts"""

import yaml
from pathlib import Path
from dataclasses import dataclass


def _load():
    p = Path(__file__).parent / "scraper_config.yaml"
    with open(p) as f:
        return yaml.safe_load(f)


@dataclass
class Repo:
    owner: str
    repo: str
    bug_labels: str
    exclude_labels: list
    category: str

    @property
    def full_name(self): return f"{self.owner}/{self.repo}"
    @property
    def slug(self): return f"{self.owner}_{self.repo}"


class Config:
    def __init__(self, raw):
        self._r = raw
        self.repos = [Repo(**{k: v for k, v in r.items()}) for r in raw["repos"]]

    # tokens
    @property def token_file(self): return self._r["tokens"]["file"]
    @property def min_remaining(self): return self._r["tokens"]["min_remaining"]
    @property def request_delay(self): return self._r["tokens"]["request_delay"]

    # discovery
    @property def since(self): return self._r["discovery"]["since"]
    @property def min_body_length(self): return self._r["discovery"]["min_body_length"]
    @property def title_reject_prefixes(self): return self._r["discovery"]["title_reject_prefixes"]
    @property def title_reject_words(self): return self._r["discovery"]["title_reject_words"]
    @property def bot_logins(self): return set(self._r["discovery"]["bot_logins"])

    # enrichment
    @property def checkpoint_every(self): return self._r["enrichment"]["checkpoint_every"]

    # classification
    @property def batch_size(self): return self._r["classification"]["batch_size"]
    @property def llm_min_confidence(self): return self._r["classification"]["llm_min_confidence"]
    @property def min_body_score(self): return self._r["classification"]["min_body_score"]
    @property def open_min_comments(self): return self._r["classification"]["open_min_comments"]
    @property def open_min_reactions(self): return self._r["classification"]["open_min_reactions"]
    @property def title_negative_words(self): return self._r["classification"]["title_negative_words"]

    # llm
    @property def llm_provider(self): return self._r["llm"]["provider"]
    @property def min_extraction_confidence(self): return self._r["llm"]["min_extraction_confidence"]
    @property def max_body_chars(self): return self._r["llm"]["max_body_chars"]
    @property def max_pr_body_chars(self): return self._r["llm"]["max_pr_body_chars"]

    def classification_model(self):
        p = self.llm_provider
        if p == "ollama":   return self._r["llm"]["ollama_classification_model"]
        if p == "openai":   return self._r["llm"]["openai_classification_model"]
        if p == "anthropic": return self._r["llm"]["anthropic_classification_model"]

    def extraction_model(self):
        p = self.llm_provider
        if p == "ollama":   return self._r["llm"]["ollama_extraction_model"]
        if p == "openai":   return self._r["llm"]["openai_extraction_model"]
        if p == "anthropic": return self._r["llm"]["anthropic_extraction_model"]

    # output
    @property def raw_dir(self): return Path(self._r["output"]["raw_dir"])
    @property def staging_dir(self): return Path(self._r["output"]["staging_dir"])
    @property def processed_dir(self): return Path(self._r["output"]["processed_dir"])
    @property def progress_file(self): return self._r["output"]["progress_file"]

    def phase_enabled(self, phase): return self._r["run_phases"].get(phase, True)

    def get_repo(self, full_name):
        for r in self.repos:
            if r.full_name == full_name: return r
        return None


cfg = Config(_load())
