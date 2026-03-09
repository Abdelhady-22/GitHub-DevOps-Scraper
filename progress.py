"""progress.py — persistent progress, keyed by repo slug + state"""

import json
import threading
from pathlib import Path
from config import cfg

_lock = threading.Lock()


def _load():
    p = Path(cfg.progress_file)
    return json.loads(p.read_text()) if p.exists() else {}


def _save(d):
    Path(cfg.progress_file).write_text(json.dumps(d, indent=2))


def _k(slug, suffix):
    return f"{slug}__{suffix}"


def discovery_done(slug, state): 
    with _lock: return _load().get(_k(slug, f"disc_{state}_done"), False)

def mark_discovery_done(slug, state, total):
    with _lock:
        d = _load(); d[_k(slug, f"disc_{state}_done")] = True; d[_k(slug, f"disc_{state}_total")] = total; _save(d)

def save_page(slug, state, page, ids):
    with _lock:
        d = _load(); pages = d.setdefault(_k(slug, f"disc_{state}_pages"), {}); pages[str(page)] = ids; _save(d)

def discovered_ids(slug, state):
    with _lock:
        d = _load(); pages = d.get(_k(slug, f"disc_{state}_pages"), {})
        return [n for ids in pages.values() for n in ids]

def enriched_ids(slug, state):
    with _lock: return set(_load().get(_k(slug, f"enr_{state}_ids"), []))

def mark_enriched(slug, state, ids: list):
    with _lock:
        d = _load(); key = _k(slug, f"enr_{state}_ids")
        existing = set(d.get(key, [])); d[key] = list(existing | set(ids)); _save(d)

def enrichment_done(slug, state): 
    with _lock: return _load().get(_k(slug, f"enr_{state}_done"), False)

def mark_enrichment_done(slug, state):
    with _lock: d = _load(); d[_k(slug, f"enr_{state}_done")] = True; _save(d)
