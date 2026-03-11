"""github_client.py — GitHub REST API wrapper, works with any repo"""

import time
import requests
from token_manager import TokenManager
from config import cfg
from logger import get_logger

log = get_logger("github")

BASE = "https://api.github.com"


class GitHubClient:
    def __init__(self, tm: TokenManager):
        self.tm = tm
        self.session = requests.Session()

    def _get(self, url: str, params: dict = None, retries: int = 3) -> requests.Response:
        for attempt in range(retries):
            headers, token = self.tm.headers()
            if "/timeline" in url:
                headers["Accept"] = "application/vnd.github.mockingbird-preview+json"
            try:
                time.sleep(cfg.request_delay)
                r = self.session.get(url, headers=headers, params=params, timeout=30)
                self.tm.update(dict(r.headers), token)

                if r.status_code == 200:
                    return r

                if r.status_code == 429:
                    wait = int(r.headers.get("Retry-After", 60))
                    log.warning(f"Rate limited (429), sleeping {wait}s...")
                    time.sleep(wait)
                    continue

                if r.status_code == 403 and "rate limit" in r.text.lower():
                    log.warning(f"Rate limit hit (403), retrying in 5s...")
                    time.sleep(5)
                    continue

                log.debug(f"HTTP {r.status_code} for {url}")
                return r

            except (requests.Timeout, requests.ConnectionError) as e:
                log.warning(f"{type(e).__name__} on attempt {attempt + 1}/{retries}: {url}")
                time.sleep(5 * (attempt + 1))

        raise RuntimeError(f"Failed after {retries} retries: {url}")

    def paginated(self, url: str, params: dict = None):
        """Generator — yields (items, page_num)"""
        params = {**(params or {}), "per_page": 100, "page": 1}
        while True:
            r = self._get(url, params)
            if r.status_code != 200 or not r.json():
                break
            yield r.json(), params["page"]
            if 'rel="next"' not in r.headers.get("Link", ""):
                break
            params["page"] += 1

    def list_labels(self, owner: str, repo: str) -> list[dict]:
        items = []
        for page, _ in self.paginated(f"{BASE}/repos/{owner}/{repo}/labels"):
            items.extend(page)
        return items

    def list_issues(self, owner: str, repo: str, state: str, labels: str, since: str):
        return self.paginated(
            f"{BASE}/repos/{owner}/{repo}/issues",
            {"state": state, "labels": labels, "since": since, "sort": "updated", "direction": "desc"},
        )

    def get_issue(self, owner: str, repo: str, number: int) -> dict | None:
        r = self._get(f"{BASE}/repos/{owner}/{repo}/issues/{number}")
        return r.json() if r.status_code == 200 else None

    def get_timeline(self, owner: str, repo: str, number: int) -> list[dict]:
        items = []
        for page, _ in self.paginated(f"{BASE}/repos/{owner}/{repo}/issues/{number}/timeline"):
            items.extend(page)
        return items

    def get_pr(self, owner: str, repo: str, number: int) -> dict | None:
        r = self._get(f"{BASE}/repos/{owner}/{repo}/pulls/{number}")
        return r.json() if r.status_code == 200 else None

    def find_merged_prs(self, timeline: list) -> list[int]:
        prs = []
        for e in timeline:
            if e.get("event") != "cross-referenced":
                continue
            src = e.get("source", {})
            if src.get("type") != "pullrequest":
                continue
            issue = src.get("issue", {})
            if issue.get("pull_request", {}).get("merged_at"):
                prs.append(issue["number"])
        return prs
