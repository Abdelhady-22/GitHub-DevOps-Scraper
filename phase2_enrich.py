"""
phase2_enrich.py — fetch full issue body, timeline, linked PR

Usage:
  python phase2_enrich.py
  python phase2_enrich.py --repo kubernetes/kubernetes
  python phase2_enrich.py --repo kubernetes/kubernetes --state open
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

log = get_logger("phase2")


def enrich_closed(client: GitHubClient, repo: Repo) -> None:
    slug = repo.slug
    if P.enrichment_done(slug, "closed"):
        log.info(f"[{repo.full_name}:closed] already done")
        return

    all_ids = P.discovered_ids(slug, "closed")
    done = P.enriched_ids(slug, "closed")
    pending = [n for n in all_ids if n not in done]
    log.info(f"[{repo.full_name}:closed] {len(all_ids)} total | {len(done)} done | {len(pending)} pending")

    idir = cfg.raw_dir / slug / "closed" / "issues"
    tdir = cfg.raw_dir / slug / "closed" / "timelines"
    pdir = cfg.raw_dir / slug / "closed" / "prs"
    for d in [idir, tdir, pdir]:
        d.mkdir(parents=True, exist_ok=True)

    batch = []
    stats = {"ok": 0, "no_pr": 0, "err": 0}

    for i, number in enumerate(pending, 1):
        # 1 — full issue
        ip = idir / f"issue_{number}.json"
        if ip.exists():
            issue = json.loads(ip.read_text())
        else:
            issue = client.get_issue(repo.owner, repo.repo, number)
            if not issue:
                stats["err"] += 1
                batch.append(number)
                _checkpoint(batch, slug, "closed")
                batch = []
                continue
            ip.write_text(json.dumps(issue))

        # 2 — timeline
        tp = tdir / f"timeline_{number}.json"
        if tp.exists():
            timeline = json.loads(tp.read_text())
        else:
            timeline = client.get_timeline(repo.owner, repo.repo, number)
            tp.write_text(json.dumps(timeline))

        pr_nums = client.find_merged_prs(timeline)
        if not pr_nums:
            (idir / f"meta_{number}.json").write_text(json.dumps({"number": number, "no_pr": True}))
            stats["no_pr"] += 1
            batch.append(number)
            _checkpoint(batch, slug, "closed")
            batch = []
            continue

        # 3 — PR
        pr_num = pr_nums[0]
        pp = pdir / f"pr_{pr_num}.json"
        if pp.exists():
            pr = json.loads(pp.read_text())
        else:
            pr = client.get_pr(repo.owner, repo.repo, pr_num)
            if not pr:
                stats["err"] += 1
                batch.append(number)
                _checkpoint(batch, slug, "closed")
                batch = []
                continue
            pp.write_text(json.dumps(pr))

        (idir / f"meta_{number}.json").write_text(json.dumps({
            "number": number,
            "pr": pr_num,
            "merged": pr.get("merged", False),
            "merged_at": pr.get("merged_at"),
        }))
        stats["ok"] += 1
        batch.append(number)

        if i % 25 == 0:
            log.info(
                f"  [{i}/{len(pending)}] ok={stats['ok']} no_pr={stats['no_pr']} "
                f"err={stats['err']} | {client.tm.status()}"
            )
        if len(batch) >= cfg.checkpoint_every:
            _checkpoint(batch, slug, "closed")
            batch = []

    _checkpoint(batch, slug, "closed")
    P.mark_enrichment_done(slug, "closed")
    log.info(f"[{repo.full_name}:closed] DONE — ok={stats['ok']} no_pr={stats['no_pr']} err={stats['err']}")


def enrich_open(client: GitHubClient, repo: Repo) -> None:
    slug = repo.slug
    if P.enrichment_done(slug, "open"):
        log.info(f"[{repo.full_name}:open] already done")
        return

    all_ids = P.discovered_ids(slug, "open")
    done = P.enriched_ids(slug, "open")
    pending = [n for n in all_ids if n not in done]
    log.info(f"[{repo.full_name}:open] {len(pending)} pending")

    idir = cfg.raw_dir / slug / "open" / "issues"
    idir.mkdir(parents=True, exist_ok=True)

    batch = []
    errors = 0

    for i, number in enumerate(pending, 1):
        ip = idir / f"issue_{number}.json"
        if not ip.exists():
            issue = client.get_issue(repo.owner, repo.repo, number)
            if issue:
                ip.write_text(json.dumps(issue))
            else:
                errors += 1
        batch.append(number)

        if i % 50 == 0:
            log.info(f"  [{i}/{len(pending)}] errors={errors}")
        if len(batch) >= cfg.checkpoint_every:
            _checkpoint(batch, slug, "open")
            batch = []

    _checkpoint(batch, slug, "open")
    P.mark_enrichment_done(slug, "open")
    log.info(f"[{repo.full_name}:open] DONE — errors={errors}")


def _checkpoint(batch: list[int], slug: str, state: str) -> None:
    if batch:
        P.mark_enriched(slug, state, batch)


def main():
    parser = argparse.ArgumentParser(description="Enrich discovered issues with full data")
    parser.add_argument("--repo", help="owner/repo (default: all)")
    parser.add_argument("--state", choices=["closed", "open", "both"], default="both")
    args = parser.parse_args()

    log.info(f"Phase 2 — Enrichment  [{datetime.now():%Y-%m-%d %H:%M:%S}]")
    if not cfg.phase_enabled("phase2_enrichment"):
        log.info("Disabled in config. Skipping.")
        return

    repos = cfg.repos
    if args.repo:
        repos = [r for r in repos if r.full_name == args.repo]

    tm = TokenManager()
    client = GitHubClient(tm)
    states = ["closed", "open"] if args.state == "both" else [args.state]

    for repo in repos:
        log.info(f"── {repo.full_name}")
        for state in states:
            if state == "closed":
                enrich_closed(client, repo)
            else:
                enrich_open(client, repo)

    log.info("Done. Next: python phase3_classify.py")


if __name__ == "__main__":
    main()
