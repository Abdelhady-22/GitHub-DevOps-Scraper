"""
phase4_extract.py — extract structured RAG entries via LLM

Usage:
  python phase4_extract.py
  python phase4_extract.py --repo kubernetes/kubernetes
"""

import json
import argparse
from pathlib import Path
from datetime import datetime, timezone
from config import cfg, Repo
from schemas import validate_closed_entry, validate_open_entry
import llm
from logger import get_logger

log = get_logger("phase4")


CLOSED_PROMPT = """Extract a DevOps incident RAG entry from this GitHub issue and its fix PR.

Issue Title: {title}
Issue Body:
{body}

PR Title: {pr_title}
PR Body:
{pr_body}

Respond ONLY in JSON, no markdown fences:
{{
  "problem_signature": "short reusable name, e.g. 'Kubernetes Pod OOMKilled'",
  "problem_description": "2-3 sentences: what broke, symptoms",
  "error_indicators": ["exact error message or log pattern"],
  "root_cause": "why this happens",
  "proposed_fix": "one sentence: what operational action resolves it",
  "execution_steps": ["kubectl/config command 1", "command 2"],
  "fix_type": "restart|scale|rollback|config|custom",
  "environment_clues": ["kubernetes","docker","etc"],
  "services_affected": ["service names or empty"],
  "confidence_in_extraction": 8
}}
Rules: execution_steps must be specific runnable commands. fix_type: restart=pod restart,
scale=replica change, rollback=version revert, config=configmap/limit change, custom=other.
confidence_in_extraction 1-10: 9+=perfect commands, 7=good, 4=vague, 1=guessed.
"""

OPEN_PROMPT = """Extract a DevOps problem entry from this open GitHub issue (no fix yet).

Issue Title: {title}
Issue Body:
{body}

Respond ONLY in JSON, no markdown fences:
{{
  "problem_signature": "short reusable name for this problem class",
  "problem_description": "2-3 sentences: what breaks, symptoms",
  "error_indicators": ["exact error or log pattern"],
  "likely_root_cause": "best guess from discussion",
  "environment_clues": ["technologies involved"],
  "services_affected": ["service names or empty"],
  "workarounds_mentioned": ["any temp workarounds or empty"],
  "confidence_in_extraction": 8
}}
"""


def trunc(text: str, n: int) -> str:
    """Truncate text to n characters with indicator."""
    text = text or ""
    if len(text) > n:
        return text[:n] + "\n[truncated]"
    return text


def extract_closed(number: int, candidate: dict, repo: Repo) -> dict | None:
    """Extract a structured RAG entry from a closed issue + PR."""
    idir = cfg.raw_dir / repo.slug / "closed" / "issues"
    pdir = cfg.raw_dir / repo.slug / "closed" / "prs"

    ip = idir / f"issue_{number}.json"
    mp = idir / f"meta_{number}.json"
    if not ip.exists():
        return None

    issue = json.loads(ip.read_text())
    meta = json.loads(mp.read_text()) if mp.exists() else {}
    pr_number = meta.get("pr")

    pr_title = pr_body = ""
    if pr_number:
        pp = pdir / f"pr_{pr_number}.json"
        if pp.exists():
            pr = json.loads(pp.read_text())
            pr_title = pr.get("title", "")
            pr_body = trunc(pr.get("body") or "", cfg.max_pr_body_chars)

    prompt = CLOSED_PROMPT.format(
        title=issue.get("title", ""),
        body=trunc(issue.get("body") or "", cfg.max_body_chars),
        pr_title=pr_title,
        pr_body=pr_body,
    )

    try:
        raw = llm.call(prompt, mode="extraction")
        ext = llm.parse_json(raw)
    except Exception as e:
        log.error(f"#{number} LLM error: {e}")
        return None

    if not ext or not isinstance(ext, dict):
        log.warning(f"#{number} LLM returned non-dict or empty response")
        return None

    if ext.get("confidence_in_extraction", 0) < cfg.min_extraction_confidence:
        log.debug(f"#{number} below confidence threshold ({ext.get('confidence_in_extraction', 0)})")
        return None

    base = f"https://github.com/{repo.full_name}"
    entry = {
        "source_repo": repo.full_name,
        "source_issue": number,
        "source_pr": pr_number,
        "source_url": f"{base}/issues/{number}",
        "source_pr_url": f"{base}/pull/{pr_number}" if pr_number else None,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "problem_signature": ext.get("problem_signature", ""),
        "problem_description": ext.get("problem_description", ""),
        "error_indicators": ext.get("error_indicators", []),
        "root_cause": ext.get("root_cause", ""),
        "proposed_fix": ext.get("proposed_fix", ""),
        "execution_steps": ext.get("execution_steps", []),
        "fix_type": ext.get("fix_type", "custom"),
        "environment_clues": ext.get("environment_clues", []),
        "services_affected": ext.get("services_affected", []),
        "category": candidate.get("category", repo.category),
        "confidence_in_extraction": ext.get("confidence_in_extraction", 0),
        "source": "github_closed_scrape",
        "synthetic": False,
        "confidence_score": 1,
        "failed_count": 0,
        "suspended": False,
        "deprecated": False,
        "version": 1,
        "issue_comments": issue.get("comments", 0),
        "issue_created_at": issue.get("created_at", ""),
        "pr_merged_at": meta.get("merged_at", ""),
    }

    # Validate against schema
    is_valid, error = validate_closed_entry(entry)
    if not is_valid:
        log.warning(f"#{number} schema validation failed: {error}")
        return None

    return entry


def extract_open(number: int, candidate: dict, repo: Repo) -> dict | None:
    """Extract a problem entry from an open issue (no fix)."""
    ip = cfg.raw_dir / repo.slug / "open" / "issues" / f"issue_{number}.json"
    if not ip.exists():
        return None

    issue = json.loads(ip.read_text())
    prompt = OPEN_PROMPT.format(
        title=issue.get("title", ""),
        body=trunc(issue.get("body") or "", cfg.max_body_chars),
    )

    try:
        raw = llm.call(prompt, mode="extraction")
        ext = llm.parse_json(raw)
    except Exception as e:
        log.error(f"#{number} LLM error: {e}")
        return None

    if not ext or not isinstance(ext, dict):
        log.warning(f"#{number} LLM returned non-dict or empty response")
        return None

    if ext.get("confidence_in_extraction", 0) < cfg.min_extraction_confidence:
        log.debug(f"#{number} below confidence threshold ({ext.get('confidence_in_extraction', 0)})")
        return None

    entry = {
        "source_repo": repo.full_name,
        "source_issue": number,
        "source_url": f"https://github.com/{repo.full_name}/issues/{number}",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "problem_signature": ext.get("problem_signature", ""),
        "problem_description": ext.get("problem_description", ""),
        "error_indicators": ext.get("error_indicators", []),
        "likely_root_cause": ext.get("likely_root_cause", ""),
        "proposed_fix": None,
        "execution_steps": [],
        "fix_type": "unknown",
        "workarounds_mentioned": ext.get("workarounds_mentioned", []),
        "environment_clues": ext.get("environment_clues", []),
        "services_affected": ext.get("services_affected", []),
        "category": candidate.get("category", repo.category),
        "confidence_in_extraction": ext.get("confidence_in_extraction", 0),
        "status": "open_unresolved",
        "source": "github_open_scrape",
        "synthetic": False,
        "confidence_score": 0,
        "suspended": False,
        "deprecated": False,
        "issue_comments": issue.get("comments", 0),
        "issue_created_at": issue.get("created_at", ""),
    }

    # Validate against schema
    is_valid, error = validate_open_entry(entry)
    if not is_valid:
        log.warning(f"#{number} schema validation failed: {error}")
        return None

    return entry


def run_repo(repo: Repo) -> dict:
    """Process all candidates for a repo. Returns stats dict."""
    slug = repo.slug
    stats = {"closed_ok": 0, "closed_skip": 0, "open_ok": 0, "open_skip": 0}

    for state in ["closed", "open"]:
        cp = cfg.staging_dir / slug / state / "candidates.jsonl"
        if not cp.exists():
            log.info(f"[{repo.full_name}:{state}] no candidates, skipping")
            continue

        out_dir = cfg.processed_dir / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{state}_entries.jsonl"

        # Load already-done issue numbers
        done = set()
        if out_path.exists():
            for line in out_path.open():
                try:
                    done.add(json.loads(line).get("source_issue"))
                except json.JSONDecodeError:
                    pass

        candidates = []
        for line in cp.open():
            try:
                c = json.loads(line)
                if c.get("number") not in done:
                    candidates.append(c)
            except json.JSONDecodeError:
                pass

        log.info(f"[{repo.full_name}:{state}] {len(candidates)} to extract ({len(done)} done)")
        fn = extract_closed if state == "closed" else extract_open
        ok = skip = 0

        with open(out_path, "a") as out_f:
            for i, cand in enumerate(candidates, 1):
                n = cand["number"]
                try:
                    entry = fn(n, cand, repo)
                except Exception as e:
                    log.error(f"#{n} extraction error: {e}")
                    skip += 1
                    continue

                if entry:
                    out_f.write(json.dumps(entry) + "\n")
                    out_f.flush()
                    ok += 1
                else:
                    skip += 1

                if i % 20 == 0:
                    log.info(f"  [{i}/{len(candidates)}] ok={ok} skip={skip}")

        log.info(f"[{repo.full_name}:{state}] DONE — extracted={ok} skipped={skip}")

        if state == "closed":
            stats["closed_ok"] = ok
            stats["closed_skip"] = skip
        else:
            stats["open_ok"] = ok
            stats["open_skip"] = skip

    return stats


def main():
    parser = argparse.ArgumentParser(description="Extract structured RAG entries via LLM")
    parser.add_argument("--repo", help="owner/repo (default: all)")
    args = parser.parse_args()

    log.info(f"Phase 4 — Extraction  [{datetime.now():%Y-%m-%d %H:%M:%S}]")
    log.info(f"LLM: {cfg.llm_provider} / {cfg.extraction_model()}")
    if not cfg.phase_enabled("phase4_extraction"):
        log.info("Disabled in config. Skipping.")
        return

    repos = cfg.repos
    if args.repo:
        repos = [r for r in repos if r.full_name == args.repo]

    for repo in repos:
        log.info(f"── {repo.full_name}")
        run_repo(repo)

    log.info("── Final counts:")
    for repo in repos:
        for state in ["closed", "open"]:
            p = cfg.processed_dir / repo.slug / f"{state}_entries.jsonl"
            if p.exists():
                n = sum(1 for _ in p.open())
                log.info(f"  {repo.full_name}/{state}: {n:,}")

    log.info("Done. Import processed/**/*.jsonl into Qdrant.")


if __name__ == "__main__":
    main()
