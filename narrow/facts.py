"""Cached lookups for NVD CVE, CISA KEV, and FIRST EPSS facts."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
EPSS_URL = "https://api.first.org/data/v1/epss"
TTL = timedelta(hours=24)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class FactsDB:
    def __init__(
        self,
        path: str | Path | None = None,
        api_key: str | None = None,
        timeout: float = 20,
    ) -> None:
        default_path = os.environ.get("NARROW_CACHE_DB", "data/facts.sqlite3")
        self.path = Path(path or default_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.api_key = api_key if api_key is not None else os.environ.get("NVD_API_KEY")
        self.timeout = timeout
        with self._connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS facts_cache (
                    cache_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                )"""
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _cached(self, key: str) -> tuple[dict[str, Any], datetime] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT payload, fetched_at FROM facts_cache WHERE cache_key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row[0]), _timestamp(row[1])

    def _save(self, key: str, payload: dict[str, Any], fetched_at: datetime) -> None:
        with self._connect() as db:
            db.execute(
                """INSERT INTO facts_cache(cache_key, payload, fetched_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(cache_key) DO UPDATE SET
                     payload = excluded.payload, fetched_at = excluded.fetched_at""",
                (key, json.dumps(payload), fetched_at.isoformat()),
            )

    def _request_json(
        self, url: str, headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        request_headers = {"Accept": "application/json", "User-Agent": "narrow/0.1.0"}
        request_headers.update(headers or {})
        request = urllib.request.Request(url, headers=request_headers)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _source(
        self, source: str, cve_id: str, loader: Any
    ) -> dict[str, Any]:
        key = f"{source}:{cve_id}"
        cached = self._cached(key)
        now = _utcnow()
        if cached and now - cached[1] < TTL:
            return {
                **cached[0],
                "fetched_date": cached[1].date().isoformat(),
                "cache_status": "fresh",
            }
        try:
            payload = loader()
            fetched_at = _utcnow()
            self._save(key, payload, fetched_at)
            return {
                **payload,
                "fetched_date": fetched_at.date().isoformat(),
                "cache_status": "fetched",
            }
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            if cached:
                return {
                    **cached[0],
                    "fetched_date": cached[1].date().isoformat(),
                    "cache_status": "stale_offline",
                }
            return {
                "error": f"{type(exc).__name__}: {exc}",
                "fetched_date": None,
                "cache_status": "unavailable",
            }

    def _nvd(self, cve_id: str) -> dict[str, Any]:
        params = urllib.parse.urlencode({"cveId": cve_id})
        headers = {"apiKey": self.api_key} if self.api_key else {}
        data = self._request_json(f"{NVD_URL}?{params}", headers)
        vulnerabilities = data.get("vulnerabilities", [])
        if not vulnerabilities:
            return {"found": False, "cvss": None, "description": None}
        cve = vulnerabilities[0].get("cve", {})
        metrics = cve.get("metrics", {})
        cvss = None
        for metric_name in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            metric_list = metrics.get(metric_name, [])
            if metric_list:
                metric = metric_list[0].get("cvssData", {})
                cvss = {
                    "version": metric.get("version"),
                    "score": metric.get("baseScore"),
                    "severity": metric.get("baseSeverity") or metric_list[0].get("baseSeverity"),
                }
                break
        description = next(
            (item.get("value") for item in cve.get("descriptions", []) if item.get("lang") == "en"),
            None,
        )
        return {"found": True, "cvss": cvss, "description": description}

    def _kev(self, cve_id: str) -> dict[str, Any]:
        feed = self._request_json(KEV_URL)
        match = next(
            (item for item in feed.get("vulnerabilities", []) if item.get("cveID") == cve_id),
            None,
        )
        return {
            "listed": match is not None,
            "details": match,
            "feed_date": feed.get("dateReleased"),
        }

    def _epss(self, cve_id: str) -> dict[str, Any]:
        params = urllib.parse.urlencode({"cve": cve_id})
        data = self._request_json(f"{EPSS_URL}?{params}")
        items = data.get("data", [])
        if not items:
            return {"score": None, "percentile": None}
        return {
            "score": float(items[0]["epss"]),
            "percentile": float(items[0]["percentile"]),
        }

    def cve_facts(self, cve_id: str) -> dict[str, Any]:
        normalized = cve_id.upper()
        if not normalized.startswith("CVE-"):
            raise ValueError("CVE identifier must start with CVE-")
        return {
            "cve_id": normalized,
            "nvd": self._source("nvd", normalized, lambda: self._nvd(normalized)),
            "kev": self._source("kev", normalized, lambda: self._kev(normalized)),
            "epss": self._source("epss", normalized, lambda: self._epss(normalized)),
        }


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python -m narrow.facts CVE-YYYY-NNNN", file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(FactsDB().cve_facts(sys.argv[1]), indent=2))


if __name__ == "__main__":
    main()
