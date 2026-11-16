from datetime import timedelta
from urllib.error import URLError

from narrow.facts import FactsDB, _utcnow


def test_facts_are_cached_by_source_and_cve(tmp_path, monkeypatch):
    db = FactsDB(tmp_path / "facts.sqlite3")
    calls = []

    def nvd(cve):
        calls.append(("nvd", cve))
        return {"found": True, "cvss": {"score": 9.8}}

    monkeypatch.setattr(db, "_nvd", nvd)
    monkeypatch.setattr(db, "_kev", lambda _: {"listed": True})
    monkeypatch.setattr(db, "_epss", lambda _: {"score": 0.9})

    first = db.cve_facts("cve-2021-44228")
    second = db.cve_facts("CVE-2021-44228")

    assert first["cve_id"] == "CVE-2021-44228"
    assert first["nvd"]["cvss"]["score"] == 9.8
    assert first["nvd"]["fetched_date"]
    assert first["nvd"]["cache_status"] == "fetched"
    assert second["nvd"]["cache_status"] == "fresh"
    assert calls == [("nvd", "CVE-2021-44228")]


def test_stale_cache_is_used_when_source_is_offline(tmp_path, monkeypatch):
    db = FactsDB(tmp_path / "facts.sqlite3")
    old_date = _utcnow() - timedelta(days=2)
    db._save("nvd:CVE-2021-44228", {"found": True, "cvss": {"score": 9.8}}, old_date)

    def unavailable(_):
        raise URLError("offline")

    monkeypatch.setattr(db, "_nvd", unavailable)
    result = db._source("nvd", "CVE-2021-44228", lambda: db._nvd("CVE-2021-44228"))

    assert result["cvss"]["score"] == 9.8
    assert result["cache_status"] == "stale_offline"
    assert result["fetched_date"] == old_date.date().isoformat()
