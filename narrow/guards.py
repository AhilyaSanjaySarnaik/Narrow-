"""Output sanitization and lightweight evidence-claim checks."""

from __future__ import annotations

import html
import os
import re
import secrets
import string
from collections.abc import Mapping, Sequence
from typing import Any

_SECRET_PATTERNS = [
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----.*?"
        r"-----END (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----",
        re.DOTALL,
    ),
]
_ZERO_WIDTH = re.compile("[\u200b-\u200f\u2060\ufeff]")
_INSTRUCTION_LINE = re.compile(
    r"^\s*(?:ignore\s+(?:all\s+)?previous\s+instructions|you\s+are\s+now\b|system\s*:)",
    re.IGNORECASE,
)
_CVE = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.IGNORECASE)
_CITATION = re.compile(r"\[E\d+\]")
_CVSS = re.compile(r"\bCVSS(?:\s+(?:v\d(?:\.\d)?))?\s*[:=]?\s*([0-9]\.\d)\b", re.I)
_URL = re.compile(r"https?://[^\s)\]>]+", re.IGNORECASE)
_ATTACK_ID = re.compile(r"\bT\d{4}(?:\.\d{3})?\b", re.IGNORECASE)
_ATTACK_LIKE = re.compile(r"\bT\d+(?:\.\d+)?\b", re.IGNORECASE)
_ALLOWLISTED_DOMAINS = {
    "nvd.nist.gov",
    "services.nvd.nist.gov",
    "cisa.gov",
    "www.cisa.gov",
    "first.org",
    "api.first.org",
    "attack.mitre.org",
    "cwe.mitre.org",
    "owasp.org",
    "www.owasp.org",
    "nist.gov",
    "www.nist.gov",
}


def new_canary() -> str:
    alphabet = string.ascii_letters + string.digits
    return "CANARY-" + "".join(secrets.choice(alphabet) for _ in range(24))


def redact(text: str, env: Mapping[str, str] | None = None) -> str:
    result = text
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    environment = os.environ if env is None else env
    secret_values = {
        value
        for name, value in environment.items()
        if any(part in name.upper() for part in ("KEY", "SECRET", "TOKEN", "PASSWORD"))
        and value
    }
    for value in sorted(secret_values, key=len, reverse=True):
        result = result.replace(value, "[REDACTED]")
    return result


def wrap_tool_output(tool: str, output: str) -> str:
    cleaned = _ZERO_WIDTH.sub("", output)
    retained = [
        line for line in cleaned.splitlines()
        if not _INSTRUCTION_LINE.match(line)
    ]
    safe_tool = re.sub(r"[^A-Za-z0-9_.-]", "_", tool)
    body = html.escape(redact("\n".join(retained)), quote=False)
    return f'<untrusted tool="{safe_tool}">\n{body}\n</untrusted>'


def _source_scores(passages: Sequence[Any]) -> list[float]:
    scores: list[float] = []
    for passage in passages:
        if isinstance(passage, Mapping):
            candidate = passage.get("cvss_score", passage.get("score"))
            if isinstance(candidate, (int, float)):
                scores.append(float(candidate))
            for key in ("text", "content", "description"):
                text = passage.get(key)
                if isinstance(text, str):
                    scores.extend(float(item) for item in re.findall(r"\b(?:CVSS\s*)?([0-9]\.\d)\b", text, re.I))
        elif isinstance(passage, str):
            scores.extend(float(item) for item in re.findall(r"\b(?:CVSS\s*)?([0-9]\.\d)\b", passage, re.I))
    return scores


def _sentence_at(text: str, position: int) -> str:
    start, end = 0, len(text)
    for separator in re.finditer(r"\n|(?<=[.!?])\s+", text):
        if separator.end() <= position:
            start = separator.end()
        elif separator.start() > position:
            end = separator.start()
            break
    return text[start:end]


def verify_claims(answer: str, kb_passages: Sequence[Any]) -> list[str]:
    issues: list[str] = []
    for match in _CVE.finditer(answer):
        if not _CITATION.search(_sentence_at(answer, match.start())):
            issues.append(f"{match.group(0)} appears without an evidence citation.")

    source_scores = _source_scores(kb_passages)
    for match in _CVSS.finditer(answer):
        value = float(match.group(1))
        sentence = _sentence_at(answer, match.start())
        citations = {int(item) for item in re.findall(r"\[E(\d+)\]", sentence)}
        cited_scores = []
        for passage in kb_passages:
            if not isinstance(passage, Mapping):
                continue
            evidence_id = passage.get("evidence_id")
            score = passage.get("cvss_score", passage.get("score"))
            if (
                isinstance(evidence_id, (int, str))
                and str(evidence_id).removeprefix("E").isdigit()
                and int(str(evidence_id).removeprefix("E")) in citations
                and isinstance(score, (int, float))
            ):
                cited_scores.append(float(score))
        candidate_scores = cited_scores or source_scores
        if not citations or not candidate_scores or not any(abs(value - score) <= 0.1 for score in candidate_scores):
            issues.append(f"CVSS score {value:.1f} is not supported by a cited source score.")

    for url in _URL.findall(answer):
        host_match = re.match(r"https?://([^/:?#]+)", url.rstrip(".,;:!?"), re.IGNORECASE)
        host = host_match.group(1).lower() if host_match else ""
        if host not in _ALLOWLISTED_DOMAINS:
            issues.append(f"URL host is not allowlisted: {host or 'invalid URL'}.")

    malformed = [match.group(0) for match in _ATTACK_LIKE.finditer(answer) if not _ATTACK_ID.fullmatch(match.group(0))]
    if malformed:
        issues.append("Malformed MITRE ATT&CK identifier(s): " + ", ".join(sorted(set(malformed))))
    return issues
