"""Read-only external tool adapters used by the local assistant."""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from narrow.guards import redact
from narrow.ingest import _read_source


def web_search(query: str, base_url: str | None = None) -> dict[str, Any]:
    endpoint = (base_url or os.environ.get("SEARXNG_BASE_URL", "http://localhost:8081")).rstrip("/")
    url = f"{endpoint}/search?q={quote_plus(query)}&format=json"
    request = Request(url, headers={"User-Agent": "Narrow/0.1"})
    with urlopen(request, timeout=20) as response:  # noqa: S310 - endpoint is explicitly configured by the operator.
        payload = json.loads(response.read().decode("utf-8"))
    results = [
        {"title": item.get("title", ""), "url": item.get("url", ""), "content": item.get("content", "")}
        for item in payload.get("results", [])[:8]
    ]
    return {"query": query, "results": results}


def fetch_url(url: str) -> dict[str, str]:
    origin, text = _read_source(url)
    return {"url": origin, "content": redact(text[:100_000])}


def _run_gh(arguments: list[str]) -> Any:
    result = subprocess.run(["gh", *arguments], capture_output=True, text=True, timeout=30, check=False)
    output = redact(result.stdout or result.stderr)
    if result.returncode:
        raise RuntimeError(output or f"gh exited with status {result.returncode}")
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return output


def _repo(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise ValueError("repository must use owner/name format")
    return value


def gh_search(query: str) -> Any:
    return _run_gh(["search", "repos", query, "--limit", "10", "--json", "nameWithOwner,description,url"])


def gh_repo_view(repo: str) -> Any:
    return _run_gh(["api", f"repos/{_repo(repo)}"])


def gh_file_read(repo: str, path: str) -> str:
    if ".." in Path(path).parts:
        raise ValueError("path traversal is not allowed")
    payload = _run_gh(["api", f"repos/{_repo(repo)}/contents/{path.lstrip('/')}"])
    if not isinstance(payload, dict) or payload.get("encoding") != "base64":
        raise RuntimeError("GitHub did not return a base64 file response")
    return redact(base64.b64decode(payload["content"]).decode("utf-8", errors="replace"))


def gh_issues(repo: str) -> Any:
    return _run_gh(["api", f"repos/{_repo(repo)}/issues?state=all&per_page=20"])


def gh_prs(repo: str) -> Any:
    return _run_gh(["api", f"repos/{_repo(repo)}/pulls?state=all&per_page=20"])


def searchsploit(query: str, executable: str | Path | None = None) -> Any:
    script = Path(executable or os.environ.get("SEARCHSPLOIT_PATH", r"C:\narrow\exploitdb\searchsploit"))
    if not script.exists():
        raise FileNotFoundError(f"SearchSploit executable not found: {script}")
    result = subprocess.run(["python", str(script), "-j", query], capture_output=True, text=True, timeout=30, check=False)
    output = redact(result.stdout or result.stderr)
    if result.returncode:
        raise RuntimeError(output or f"searchsploit exited with status {result.returncode}")
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return output
