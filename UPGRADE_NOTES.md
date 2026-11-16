# Narrow upgrade notes

Implemented:

- Local assistant tool loop with a four-call limit and real tool errors returned to the model.
- Read-only SearXNG `web_search` and public `fetch_url` adapters.
- Read-only SearchSploit JSON adapter.
- Read-only GitHub CLI adapters for repository search, repository metadata, file reads, issues, and pull requests.
- Secret redaction is applied to GitHub and SearchSploit outputs.
- Existing local RAG remains the first evidence source.

External setup still required:

- SearXNG must be reachable at `SEARXNG_BASE_URL` (default `http://localhost:8081`).
- SearchSploit must exist at `SEARCHSPLOIT_PATH` (default `C:\narrow\exploitdb\searchsploit`).
- GitHub CLI must be installed and authenticated with `gh auth login`.

Intentionally not implemented:

- Autonomous shell execution.
- Exploit, malware, reverse-shell, persistence, evasion, or credential-theft generation/execution.
- GitHub write actions. Any future write integration must require explicit confirmation.
