"""
phase0_list_labels.py
─────────────────────
Shows all labels for every repo in config.
first to confirm bug_labels settings are correct.

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


def show_labels(client, owner, repo, configured_bug_labels):
    print(f"\n{'═'*55}")
    print(f"  {owner}/{repo}")
    print(f"  configured bug_labels: '{configured_bug_labels}'")
    print(f"{'═'*55}")

    try:
        labels = client.list_labels(owner, repo)
    except Exception as e:
        print(f"  ERROR: {e}")
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
        print(f"\n  [{prefix}]  ({len(names)} labels)")
        for name in names:
            marker = "  ◄ BUG LABEL (configured)" if name in configured else ""
            print(f"    {name}{marker}")

    # Validation
    print()
    for lbl in configured:
        if lbl in all_names:
            print(f"  ✓  '{lbl}' exists")
        else:
            print(f"  ✗  '{lbl}' NOT FOUND — fix bug_labels in scraper_config.yaml!")

    # Save to file
    out = cfg.raw_dir / f"{owner}_{repo}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "labels.json").write_text(json.dumps(labels, indent=2))
    print(f"\n  Saved full list → {out}/labels.json")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", help="owner/repo to check (default: all from config)")
    args = parser.parse_args()

    tm = TokenManager()
    client = GitHubClient(tm)

    repos = cfg.repos
    if args.repo:
        owner, repo = args.repo.split("/")
        repos = [r for r in repos if r.owner == owner and r.repo == repo]
        if not repos:
            print(f"'{args.repo}' not found in scraper_config.yaml")
            return

    for r in repos:
        show_labels(client, r.owner, r.repo, r.bug_labels)

    print("\n\nDone. If any label shows ✗, update bug_labels in scraper_config.yaml before running phase1.")


if __name__ == "__main__":
    main()
