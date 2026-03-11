"""
run_all.py — run the full scraping pipeline in sequence

Usage:
  python run_all.py                      # run all enabled phases
  python run_all.py --repo kubernetes/kubernetes  # single repo
  python run_all.py --phases 3 4         # only run phases 3 and 4
"""

import sys
import time
import json
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from logger import get_logger

log = get_logger("runner")

PHASES = [
    ("phase0_list_labels.py", "Phase 0 — Label Validation"),
    ("phase1_discover.py", "Phase 1 — Discovery"),
    ("phase2_enrich.py", "Phase 2 — Enrichment"),
    ("phase3_classify.py", "Phase 3 — Classification"),
    ("phase4_extract.py", "Phase 4 — Extraction"),
]


def run_phase(script: str, label: str, extra_args: list[str]) -> dict:
    """Run a single phase script and capture timing + exit code."""
    log.info(f"{'═' * 60}")
    log.info(f"  STARTING: {label}")
    log.info(f"  Script:   {script}")
    log.info(f"{'═' * 60}")

    start = time.time()
    cmd = [sys.executable, script] + extra_args

    try:
        result = subprocess.run(
            cmd,
            cwd=Path(__file__).parent,
            timeout=6 * 3600,  # 6 hour timeout per phase
        )
        elapsed = time.time() - start
        success = result.returncode == 0

        if success:
            log.info(f"  ✓ {label} completed in {elapsed / 60:.1f} min")
        else:
            log.error(f"  ✗ {label} failed (exit code {result.returncode}) after {elapsed / 60:.1f} min")

        return {
            "phase": label,
            "script": script,
            "exit_code": result.returncode,
            "duration_seconds": round(elapsed, 1),
            "success": success,
        }

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        log.error(f"  ✗ {label} TIMED OUT after {elapsed / 60:.1f} min")
        return {
            "phase": label,
            "script": script,
            "exit_code": -1,
            "duration_seconds": round(elapsed, 1),
            "success": False,
            "error": "timeout",
        }
    except Exception as e:
        elapsed = time.time() - start
        log.error(f"  ✗ {label} error: {e}")
        return {
            "phase": label,
            "script": script,
            "exit_code": -1,
            "duration_seconds": round(elapsed, 1),
            "success": False,
            "error": str(e),
        }


def main():
    parser = argparse.ArgumentParser(description="Run the full GitHub DevOps scraping pipeline")
    parser.add_argument("--repo", help="owner/repo (passed to each phase)")
    parser.add_argument("--phases", nargs="+", type=int, help="Phase numbers to run (e.g. --phases 1 2 3)")
    parser.add_argument("--skip-phase0", action="store_true", help="Skip label validation (phase 0)")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("  GitHub DevOps Scraper — Full Pipeline")
    log.info(f"  Started: {datetime.now():%Y-%m-%d %H:%M:%S}")
    log.info("=" * 60)

    extra_args = []
    if args.repo:
        extra_args.extend(["--repo", args.repo])

    # Determine which phases to run
    if args.phases:
        phases_to_run = [(s, l) for i, (s, l) in enumerate(PHASES) if i in args.phases]
    elif args.skip_phase0:
        phases_to_run = PHASES[1:]
    else:
        phases_to_run = PHASES

    results = []
    total_start = time.time()

    for script, label in phases_to_run:
        result = run_phase(script, label, extra_args)
        results.append(result)

        if not result["success"]:
            log.error(f"Pipeline stopped: {label} failed. Fix the issue and re-run.")
            break

    total_elapsed = time.time() - total_start

    # Summary
    log.info("")
    log.info("=" * 60)
    log.info("  PIPELINE SUMMARY")
    log.info("=" * 60)
    for r in results:
        status = "✓" if r["success"] else "✗"
        log.info(f"  {status}  {r['phase']:40s}  {r['duration_seconds'] / 60:6.1f} min")
    log.info(f"  {'─' * 55}")
    log.info(f"  Total: {total_elapsed / 60:.1f} min")

    # Save summary
    summary = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "total_duration_seconds": round(total_elapsed, 1),
        "phases": results,
        "all_passed": all(r["success"] for r in results),
    }
    summary_path = Path("run_summary.json")
    summary_path.write_text(json.dumps(summary, indent=2))
    log.info(f"  Summary saved → {summary_path}")


if __name__ == "__main__":
    main()
