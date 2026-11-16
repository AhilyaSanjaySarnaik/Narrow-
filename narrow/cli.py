"""Command-line entry point for the Phase 1 Narrow foundation."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from narrow.facts import FactsDB
from narrow.guards import verify_claims
from narrow.ingest import ingest_source
from narrow.rag import KnowledgeBase


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="narrow")
    commands = parser.add_subparsers(dest="command", required=True)

    facts = commands.add_parser("facts", help="look up cached NVD, KEV, and EPSS facts")
    facts.add_argument("cve_id")

    search = commands.add_parser("search", help="search the local Markdown knowledge base")
    search.add_argument("query")
    search.add_argument("--root", type=Path, default=Path("kb"))
    search.add_argument("--model-path", type=Path, default=Path("models/bge-small-en-v1.5"))
    search.add_argument("--limit", type=int, default=5)
    search.add_argument("--threshold", type=float, default=0.35)

    ingest = commands.add_parser("ingest", help="import a local text file or public web page")
    ingest.add_argument("source", help="path to .md/.txt/.html or an http(s) URL")
    ingest.add_argument("--root", type=Path, default=Path("kb"))

    commands.add_parser("gui", help="open the local desktop interface")

    commands.add_parser("config", help="show non-secret local configuration")

    verify = commands.add_parser("verify", help="check an answer for unsupported claims")
    verify.add_argument("answer_file", type=Path)
    verify.add_argument(
        "--source-score",
        type=float,
        action="append",
        default=[],
        help="CVSS score from a source to compare against (repeatable)",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "facts":
        print(json.dumps(FactsDB().cve_facts(args.cve_id), indent=2))
        return
    if args.command == "search":
        try:
            result = KnowledgeBase(
                root=args.root,
                model_path=args.model_path,
                abstain_threshold=args.threshold,
            ).search(args.query, limit=args.limit)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            raise SystemExit(str(exc)) from exc
        print(json.dumps(result, indent=2))
        return
    if args.command == "ingest":
        try:
            destination = ingest_source(args.source, root=args.root)
        except (OSError, RuntimeError, ValueError) as exc:
            raise SystemExit(str(exc)) from exc
        print(json.dumps({"imported": str(destination), "source": args.source}, indent=2))
        return
    if args.command == "gui":
        from narrow.gui import main as gui_main

        gui_main()
        return
    if args.command == "config":
        print(f"LLM_BASE_URL={os.environ.get('LLM_BASE_URL', 'http://localhost:11434/v1')}")
        print(f"LLM_MODEL={os.environ.get('LLM_MODEL', 'qwen3:4b')}")
        print(f"NVD_API_KEY={'configured' if os.environ.get('NVD_API_KEY') else 'not configured'}")
        print(f"NARROW_CACHE_DB={os.environ.get('NARROW_CACHE_DB', 'data/facts.sqlite3')}")
        return
    if args.command == "verify":
        answer = args.answer_file.read_text(encoding="utf-8")
        sources = [{"cvss_score": score} for score in args.source_score]
        issues = verify_claims(answer, sources)
        if issues:
            print(json.dumps({"passed": False, "issues": issues}, indent=2))
            raise SystemExit(1)
        print(json.dumps({"passed": True, "issues": []}, indent=2))
        return
    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
