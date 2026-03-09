"""
phase4_extract.py — extract structured RAG entries via LLM

Usage:
  python phase4_extract.py
  python phase4_extract.py --repo kubernetes/kubernetes
"""

import json
import argparse
from pathlib import Path
from datetime import datetime
from config import cfg
import llm


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


def trunc(text, n): return (text or "")[:n] + ("\n[truncated]" if len(text or "") > n else "")


def extract_closed(number, candidate, repo):
    idir = cfg.raw_dir / repo.slug / "closed" / "issues"
    pdir = cfg.raw_dir / repo.slug / "closed" / "prs"

    ip = idir / f"issue_{number}.json"
    mp = idir / f"meta_{number}.json"
    if not ip.exists(): return None

    issue = json.loads(ip.read_text())
    meta  = json.loads(mp.read_text()) if mp.exists() else {}
    pr_number = meta.get("pr")

    pr_title = pr_body = ""
    if pr_number:
        pp = pdir / f"pr_{pr_number}.json"
        if pp.exists():
            pr = json.loads(pp.read_text())
            pr_title = pr.get("title", "")
            pr_body  = trunc(pr.get("body") or "", cfg.max_pr_body_chars)

    prompt = CLOSED_PROMPT.format(
        title=issue.get("title",""),
        body=trunc(issue.get("body") or "", cfg.max_body_chars),
        pr_title=pr_title, pr_body=pr_body,
    )

    try:
        raw = llm.call(prompt, mode="extraction")
        ext = llm.parse_json(raw)
    except Exception as e:
        print(f"    #{number} LLM error: {e}"); return None

    if not ext or not isinstance(ext, dict): return None
    if ext.get("confidence_in_extraction", 0) < cfg.min_extraction_confidence: return None

    base = f"https://github.com/{repo.full_name}"
    return {
        "source_repo": repo.full_name,
        "source_issue": number,
        "source_pr": pr_number,
        "source_url": f"{base}/issues/{number}",
        "source_pr_url": f"{base}/pull/{pr_number}" if pr_number else None,
        "scraped_at": datetime.utcnow().isoformat() + "Z",
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


def extract_open(number, candidate, repo):
    ip = cfg.raw_dir / repo.slug / "open" / "issues" / f"issue_{number}.json"
    if not ip.exists(): return None

    issue = json.loads(ip.read_text())
    prompt = OPEN_PROMPT.format(
        title=issue.get("title",""),
        body=trunc(issue.get("body") or "", cfg.max_body_chars),
    )

    try:
        raw = llm.call(prompt, mode="extraction")
        ext = llm.parse_json(raw)
    except Exception as e:
        print(f"    #{number} LLM error: {e}"); return None

    if not ext or not isinstance(ext, dict): return None
    if ext.get("confidence_in_extraction", 0) < cfg.min_extraction_confidence: return None

    return {
        "source_repo": repo.full_name,
        "source_issue": number,
        "source_url": f"https://github.com/{repo.full_name}/issues/{number}",
        "scraped_at": datetime.utcnow().isoformat() + "Z",
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


def run_repo(repo):
    slug = repo.slug
    for state in ["closed", "open"]:
        cp = cfg.staging_dir / slug / state / "candidates.jsonl"
        if not cp.exists():
            print(f"  [{repo.full_name}:{state}] no candidates, skipping"); continue

        out_dir = cfg.processed_dir / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{state}_entries.jsonl"

        # already done
        done = set()
        if out_path.exists():
            for line in out_path.open():
                try: done.add(json.loads(line).get("source_issue"))
                except: pass

        candidates = []
        for line in cp.open():
            try:
                c = json.loads(line)
                if c.get("number") not in done: candidates.append(c)
            except: pass

        print(f"  [{repo.full_name}:{state}] {len(candidates)} to extract ({len(done)} done)")
        fn = extract_closed if state == "closed" else extract_open
        ok = skip = 0

        with open(out_path, "a") as out_f:
            for i, cand in enumerate(candidates, 1):
                n = cand["number"]
                try: entry = fn(n, cand, repo)
                except Exception as e:
                    print(f"    #{n} error: {e}"); skip += 1; continue

                if entry:
                    out_f.write(json.dumps(entry) + "\n"); out_f.flush(); ok += 1
                else:
                    skip += 1

                if i % 20 == 0:
                    print(f"    [{i}/{len(candidates)}] ok={ok} skip={skip}")

        print(f"  [{repo.full_name}:{state}] DONE — extracted={ok} skipped={skip}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", help="owner/repo (default: all)")
    args = parser.parse_args()

    print(f"Phase 4 — Extraction  [{datetime.now():%Y-%m-%d %H:%M:%S}]")
    print(f"LLM: {cfg.llm_provider} / {cfg.extraction_model()}")
    if not cfg.phase_enabled("phase4_extraction"):
        print("Disabled in config. Skipping."); return

    repos = cfg.repos
    if args.repo:
        repos = [r for r in repos if r.full_name == args.repo]

    for repo in repos:
        print(f"\n── {repo.full_name}")
        run_repo(repo)

    print("\n── Final counts:")
    for repo in repos:
        for state in ["closed", "open"]:
            p = cfg.processed_dir / repo.slug / f"{state}_entries.jsonl"
            if p.exists():
                n = sum(1 for _ in p.open())
                print(f"  {repo.full_name}/{state}: {n:,}")

    print("\nDone. Import processed/**/*.jsonl into Qdrant.")


if __name__ == "__main__":
    main()
