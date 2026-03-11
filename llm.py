"""llm.py — single call() function works with openai, anthropic, ollama — with retries"""

import json
import re
import time
import requests
from config import cfg
from logger import get_logger

log = get_logger("llm")

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds, doubles each retry


def call(prompt: str, mode: str = "extraction") -> str:
    """
    Call the configured LLM provider with automatic retries.

    mode: "classification" uses the fast/cheap model
          "extraction"     uses the quality model
    Returns raw text response.
    """
    model = cfg.classification_model() if mode == "classification" else cfg.extraction_model()
    provider = cfg.llm_provider

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if provider == "ollama":
                return _ollama(prompt, model)
            elif provider == "openai":
                return _openai(prompt, model)
            elif provider == "anthropic":
                return _anthropic(prompt, model)
            else:
                raise ValueError(f"Unknown llm.provider: {provider}. Use ollama, openai, or anthropic.")
        except ValueError:
            raise  # don't retry config errors
        except Exception as e:
            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                log.warning(f"LLM call failed (attempt {attempt}/{MAX_RETRIES}): {e} — retrying in {delay}s")
                time.sleep(delay)
            else:
                log.error(f"LLM call failed after {MAX_RETRIES} attempts: {e}")
                raise


def _ollama(prompt: str, model: str) -> str:
    base = cfg.ollama_base_url.rstrip("/")
    resp = requests.post(
        f"{base}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0},
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def _openai(prompt: str, model: str) -> str:
    import openai
    client = openai.OpenAI()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=2000,
    )
    return resp.choices[0].message.content.strip()


def _anthropic(prompt: str, model: str) -> str:
    import anthropic
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def parse_json(text: str) -> dict | list | None:
    """Strip markdown fences and parse JSON."""
    text = re.sub(r"```json\s*|```\s*", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # try to find JSON object or array inside the text
        for pattern in [r"\[.*\]", r"\{.*\}"]:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
    log.debug(f"Failed to parse JSON from LLM response ({len(text)} chars)")
    return None
