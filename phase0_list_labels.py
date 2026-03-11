"""
phase0_list_labels.py
─────────────────────
Shows all labels for every repo in config.
Run first to confirm bug_labels settings are correct.

Usage:
  python phase0_list_labels.py                         # all repos
  python phase0_list_labels.py --repo kubernetes/kubernetes  # one repo
"""

import json
import argparse
from pathlib import Path
from config import cfg
from token_manager import TokenManager
from github_client import GitHubClient
from logger import get_logger

log = get_logger("phase0")


def show_labels(client: GitHubClient, owner: str, repo: str, configured_bug_labels: str) -> None:
    log.info(f"{'═' * 55}")
    log.info(f"  {owner}/{repo}")
    log.info(f"  configured bug_labels: '{configured_bug_labels}'")
    log.info(f"{'═' * 55}")

    try:
        labels = client.list_labels(owner, repo)
    except Exception as e:
        log.error(f"Failed to fetch labels for {owner}/{repo}: {e}")
        return

    all_names = {l["name"] for l in labels}
    configured = [l.strip() for l in configured_bug_labels.split(",")]

    # Group by prefix
    groups: dict[str, list[str]] = {}
    for l in sorted(labels, key=lambda x: x["name"]):
        name = l["name"]
        prefix = name.split("/")[0] if "/" in name else "other"
        groups.setdefault(prefix, []).append(name)

    for prefix, names in sorted(groups.items()):
        log.info(f"  [{prefix}]  ({len(names)} labels)")
        for name in names:
            marker = "  ◄ BUG LABEL (configured)" if name in configured else ""
            log.info(f"    {name}{marker}")

    # Validation
    for lbl in configured:
        if lbl in all_names:
            log.info(f"  ✓  '{lbl}' exists")
        else:
            log.warning(f"  ✗  '{lbl}' NOT FOUND — fix bug_labels in scraper_config.yaml!")

    # Save to file
    out = cfg.raw_dir / f"{owner}_{repo}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "labels.json").write_text(json.dumps(labels, indent=2))
    log.info(f"  Saved full list → {out}/labels.json")


def main():
    parser = argparse.ArgumentParser(description="List and validate GitHub repo labels")
    parser.add_argument("--repo", help="owner/repo to check (default: all from config)")
    args = parser.parse_args()

    tm = TokenManager()
    client = GitHubClient(tm)

    repos = cfg.repos
    if args.repo:
        owner, repo = args.repo.split("/")
        repos = [r for r in repos if r.owner == owner and r.repo == repo]
        if not repos:
            log.error(f"'{args.repo}' not found in scraper_config.yaml")
            return

    for r in repos:
        show_labels(client, r.owner, r.repo, r.bug_labels)

    log.info("Done. If any label shows ✗, update bug_labels in scraper_config.yaml before running phase1.")


if __name__ == "__main__":
    main()
