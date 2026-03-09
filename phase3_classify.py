"""
phase3_classify.py — classify issues: rule-based filters then LLM batch

Usage:
  python phase3_classify.py
  python phase3_classify.py --repo kubernetes/kubernetes
"""

import json
import re
import argparse
from pathlib import Path
from datetime import datetime
from config import cfg
import llm


ERROR_PATTERNS = [
    r"error:", r"fatal:", r"panic:", r"exception:", r"traceback",
    r"exit code \d+", r"oomkilled", r"crashloopbackoff", r"imagepullbackoff",
    r"failed to", r"unable to", r"cannot ", r"connection refused",
    r"timed? ?out", r"level=error", r"\[error\]", r"status=\d{3}",
]


def body_score(body: str) -> int:
    if not body: return 0
    bl = body.lower()
    score = min(sum(1 for p in ERROR_PATTERNS if re.search(p, bl)) * 2, 4)
    score += min(len(re.findall(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", body)), 2)
    score += min(sum(1 for p in [r"kubectl ", r"helm ", r"docker "] if re.search(p, body, re.I)), 2)
    score += 1 if re.search(r"(steps to reproduce|to reproduce)", bl) else 0
    score += 1 if re.search(r"(expected|actual|what happened)", bl) else 0
    return min(score, 10)


def rule_filter(issue, meta, state, repo) -> tuple[bool, str, int]:
    title = (issue.get("title") or "").lower()
    labels = [l["name"].lower() for l in issue.get("labels", [])]
    excl = {l.lower() for l in repo.exclude_labels}

    for l in labels:
        if l in excl: return False, f"label:{l}", 0
    if state == "closed":
        if meta.get("no_pr"): return False, "no_pr", 0
        if not meta.get("merged"): return False, "pr_not_merged", 0
    for w in cfg.title_negative_words:
        if w.lower() in title: return False, f"neg_title:{w}", 0

    score = body_score(issue.get("body") or "")
    if score < cfg.min_body_score: return False, f"low_score:{score}", score

    if state == "open":
        comments  = issue.get("comments", 0)
        reactions = (issue.get("reactions") or {}).get("+1", 0)
        if comments < cfg.open_min_comments and reactions < cfg.open_min_reactions:
            return False, "no_engagement", score

    return True, "", score


def llm_classify(issues: list[dict]) -> list[dict]:
    blocks = []
    for i, iss in enumerate(issues, 1):
        preview = (iss.get("body") or "")[:500].replace("\n", " ")
        lbls    = ", ".join(l["name"] for l in iss.get("labels", []))
        blocks.append(
            f"Issue {i}:\nNumber: {iss['number']}\nTitle: {iss.get('title','')}\n"
            f"Labels: {lbls}\nBody: {preview}"
        )

    prompt = (
        "Classify GitHub issues for a DevOps incident RAG database.\n"
        "KEEP: real infrastructure broke — pods crashing, services down, DB unreachable, pipelines failing.\n"
        "REJECT: feature requests, how-to questions, docs, UI bugs, refactors, dependency bumps.\n\n"
        f"Classify these {len(issues)} issues. Return ONLY a JSON array:\n\n"
        + "\n---\n".join(blocks)
        + '\n\n[{"number":1234,"keep":true,"category":"kubernetes|database|application|cicd|infrastructure","confidence":0.9},...]'
    )

    raw = llm.call(prompt, mode="classification")
    result = llm.parse_json(raw)
    return result if isinstance(result, list) else []


def classify_repo(repo):
    slug = repo.slug
    for state in ["closed", "open"]:
        idir = cfg.raw_dir / slug / state / "issues"
        if not idir.exists():
            print(f"  [{repo.full_name}:{state}] no enriched issues, skipping")
            continue

        out_dir = cfg.staging_dir / slug / state
        out_dir.mkdir(parents=True, exist_ok=True)
        (cfg.staging_dir / "rejected").mkdir(parents=True, exist_ok=True)

        issue_files = [f for f in sorted(idir.glob("issue_*.json"))]
        meta_cache  = {}
        for mf in idir.glob("meta_*.json"):
            try: m = json.loads(mf.read_text()); meta_cache[m["number"]] = m
            except: pass

        print(f"  [{repo.full_name}:{state}] classifying {len(issue_files)} issues...")

        kept = []; rejected = []; llm_queue = []

        for f in issue_files:
            try: issue = json.loads(f.read_text())
            except: continue
            n    = issue.get("number")
            meta = meta_cache.get(n, {})
            ok, reason, score = rule_filter(issue, meta, state, repo)
            if not ok:
                rejected.append({"number": n, "title": (issue.get("title") or "")[:80], "layer": "rules", "reason": reason})
            else:
                llm_queue.append({"number": n, "title": issue.get("title",""), "body": issue.get("body",""),
                                   "labels": issue.get("labels",[]), "score": score, "meta": meta})

        print(f"    rules: {len(llm_queue)} pass, {len(rejected)} rejected — running LLM batches...")

        total_batches = (len(llm_queue) + cfg.batch_size - 1) // cfg.batch_size
        for bi in range(0, len(llm_queue), cfg.batch_size):
            batch     = llm_queue[bi:bi + cfg.batch_size]
            batch_num = bi // cfg.batch_size + 1
            print(f"    batch {batch_num}/{total_batches} ({len(batch)} issues)...", end=" ", flush=True)

            try: results = llm_classify(batch)
            except Exception as e:
                print(f"LLM error: {e} — keeping batch")
                for iss in batch:
                    meta = iss.pop("meta", {})
                    iss["category"] = repo.category; iss["llm_skipped"] = True; kept.append(iss)
                continue

            rmap = {r.get("number"): r for r in results if isinstance(r, dict)}
            lk = lr = 0
            for iss in batch:
                n    = iss["number"]
                meta = iss.pop("meta", {})
                res  = rmap.get(n)
                conf = (res or {}).get("confidence", 0)

                if res and res.get("keep") and conf >= cfg.llm_min_confidence:
                    iss["category"]   = res.get("category", repo.category)
                    iss["confidence"] = conf
                    iss["pr"]         = meta.get("pr")
                    iss["merged_at"]  = meta.get("merged_at")
                    kept.append(iss); lk += 1
                else:
                    rejected.append({"number": n, "layer": "llm",
                                     "reason": (res or {}).get("reject_reason", "llm_reject"),
                                     "confidence": conf})
                    lr += 1
            print(f"kept={lk} rejected={lr}")

        # save
        with open(out_dir / "candidates.jsonl", "w") as f:
            for e in kept:
                f.write(json.dumps({k: v for k, v in e.items() if k != "body"}) + "\n")
        with open(cfg.staging_dir / "rejected" / f"{slug}_{state}.jsonl", "w") as f:
            for e in rejected: f.write(json.dumps(e) + "\n")

        print(f"  [{repo.full_name}:{state}] DONE — kept={len(kept)} rejected={len(rejected)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", help="owner/repo (default: all)")
    args = parser.parse_args()

    print(f"Phase 3 — Classification  [{datetime.now():%Y-%m-%d %H:%M:%S}]")
    print(f"LLM: {cfg.llm_provider} / {cfg.classification_model()}")
    if not cfg.phase_enabled("phase3_classification"):
        print("Disabled in config. Skipping."); return

    repos = cfg.repos
    if args.repo:
        repos = [r for r in repos if r.full_name == args.repo]

    for repo in repos:
        print(f"\n── {repo.full_name}")
        classify_repo(repo)

    print("\nDone. Next: python phase4_extract.py")


if __name__ == "__main__":
    main()
