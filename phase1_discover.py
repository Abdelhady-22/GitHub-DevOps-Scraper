"""
phase1_discover.py — discover candidate issue IDs for all repos

Usage:
  python phase1_discover.py
  python phase1_discover.py --repo kubernetes/kubernetes
  python phase1_discover.py --repo kubernetes/kubernetes --state closed
"""

import json
import argparse
from pathlib import Path
from datetime import datetime
from config import cfg, Repo
from token_manager import TokenManager
from github_client import GitHubClient
import progress as P
from logger import get_logger

log = get_logger("phase1")


def keep(issue: dict, repo: Repo) -> tuple[bool, str]:
    """Check if an issue should be kept based on rule filters."""
    if "pull_request" in issue:
        return False, "is_pr"

    title = (issue.get("title") or "").lower()
    body = issue.get("body") or ""
    login = (issue.get("user") or {}).get("login", "").lower()
    lbls = [l["name"].lower() for l in issue.get("labels", [])]

    if login in cfg.bot_logins or login.endswith("[bot]"):
        return False, "bot"

    for p in cfg.title_reject_prefixes:
        if title.startswith(p.lower()):
            return False, f"prefix:{p}"

    for w in cfg.title_reject_words:
        if w.lower() in title:
            return False, f"word:{w}"

    if len(body) < cfg.min_body_length:
        return False, f"short_body:{len(body)}"

    excl = {l.lower() for l in repo.exclude_labels}
    for l in lbls:
        if l in excl:
            return False, f"label:{l}"

    return True, ""


def discover(client: GitHubClient, repo: Repo, state: str) -> None:
    slug = repo.slug
    if P.discovery_done(slug, state):
        n = len(P.discovered_ids(slug, state))
        log.info(f"[{repo.full_name}:{state}] already done ({n} found)")
        return

    raw_dir = cfg.raw_dir / slug / state / "discovery"
    rej_dir = cfg.raw_dir / slug / state / "rejected"
    raw_dir.mkdir(parents=True, exist_ok=True)
    rej_dir.mkdir(parents=True, exist_ok=True)

    seen = kept = rejected = 0
    rej_log = []

    for items, page in client.list_issues(repo.owner, repo.repo, state, repo.bug_labels, cfg.since):
        (raw_dir / f"page_{page:04d}.json").write_text(json.dumps(items))

        page_kept = []
        page_rej = []
        for issue in items:
            seen += 1
            ok, reason = keep(issue, repo)
            if ok:
                kept += 1
                page_kept.append(issue["number"])
            else:
                rejected += 1
                entry = {
                    "number": issue.get("number"),
                    "title": (issue.get("title") or "")[:80],
                    "reason": reason,
                }
                page_rej.append(entry)
                rej_log.append(entry)

        P.save_page(slug, state, page, page_kept)
        if page_rej:
            (rej_dir / f"page_{page:04d}.json").write_text(json.dumps(page_rej, indent=2))

        log.info(
            f"[{repo.full_name}:{state}] page={page:3d} | "
            f"seen={seen:5d} kept={kept:4d} rejected={rejected:4d} | "
            f"tokens: {client.tm.status()}"
        )

    (cfg.raw_dir / slug / state / "rejected_summary.json").write_text(json.dumps(rej_log, indent=2))
    P.mark_discovery_done(slug, state, kept)
    log.info(
        f"[{repo.full_name}:{state}] DONE — kept={kept} rejected={rejected} "
        f"({rejected / max(seen, 1) * 100:.0f}% rejection)"
    )


def main():
    parser = argparse.ArgumentParser(description="Discover candidate GitHub issues")
    parser.add_argument("--repo", help="owner/repo (default: all)")
    parser.add_argument("--state", choices=["closed", "open", "both"], default="both")
    args = parser.parse_args()

    log.info(f"Phase 1 — Discovery  [{datetime.now():%Y-%m-%d %H:%M:%S}]")
    if not cfg.phase_enabled("phase1_discovery"):
        log.info("Disabled in config. Skipping.")
        return

    repos = cfg.repos
    if args.repo:
        repos = [r for r in repos if r.full_name == args.repo]

    tm = TokenManager()
    client = GitHubClient(tm)
    states = ["closed", "open"] if args.state == "both" else [args.state]

    for repo in repos:
        log.info(f"── {repo.full_name}  labels={repo.bug_labels}")
        for state in states:
            discover(client, repo, state)

    log.info("Done. Next: python phase2_enrich.py")


if __name__ == "__main__":
    main()
