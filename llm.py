"""llm.py — single call() function works with openai, anthropic, ollama"""

import json
import re
import requests
from config import cfg


def call(prompt: str, mode: str = "extraction") -> str:
    """
    mode: "classification" uses the fast/cheap model
          "extraction"     uses the quality model
    Returns raw text response.
    """
    model = cfg.classification_model() if mode == "classification" else cfg.extraction_model()
    provider = cfg.llm_provider

    if provider == "ollama":
        return _ollama(prompt, model)
    elif provider == "openai":
        return _openai(prompt, model)
    elif provider == "anthropic":
        return _anthropic(prompt, model)
    else:
        raise ValueError(f"Unknown llm.provider: {provider}. Use ollama, openai, or anthropic.")


def _ollama(prompt: str, model: str) -> str:
    base = cfg._r["llm"]["ollama_base_url"].rstrip("/")
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
    except Exception:
        # try to find JSON object or array inside the text
        for pattern in [r"\[.*\]", r"\{.*\}"]:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    pass
    return None
