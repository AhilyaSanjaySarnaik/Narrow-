# Narrow

Air-gapped. Evidence-grounded. Defensive security assistance for local, explicitly
authorized work.

Narrow keeps vulnerability facts in a local SQLite cache and treats retrieved
content as untrusted data. It is designed to abstain when evidence is unavailable.
It does not provide malware, credential theft, evasion, exploit payloads, or
autonomous offensive workflows.

## Quickstart

1. Install Python 3.12+ and Ollama.
2. `python -m venv .venv`
3. Activate `.venv`.
4. `python -m pip install -e ".[test]"`
5. Copy `.env.example` to `.env` and configure local settings.
6. `ollama pull qwen3:4b`
7. `python -m narrow.facts CVE-2021-44228`

Search the local Markdown knowledge base with the hybrid retriever:

```text
python -m narrow.cli search "least privilege" \\
  --root kb \\
  --model-path models/bge-small-en-v1.5
```

The command returns ranked passages as JSON. If the best result is below the
configured confidence threshold, it sets `"abstain": true`.

Open the local desktop interface:

```text
python -m narrow.cli gui
```

The GUI lets you choose files, import public article URLs, and search the local
knowledge base while showing the evidence passages and abstention state.

Import a local text/Markdown/HTML file or a public web article:

```text
python -m narrow.cli ingest path/to/report.md
python -m narrow.cli ingest path/to/report.pdf
python -m narrow.cli ingest path/to/report.docx
python -m narrow.cli ingest path/to/data.xlsx
python -m narrow.cli ingest path/to/photo.png
python -m narrow.cli ingest path/to/video.mp4
python -m narrow.cli ingest https://example.com/article
```

Imported content is saved under `kb/` and remains local after download. Web
imports are limited to public HTTP(S) URLs and 20 MB; scripts and styles are
removed from HTML imports. PDF, Word, PowerPoint, and Excel text is extracted
locally. Images are inspected and OCR is attempted; install Tesseract for image
text. Audio/video metadata is extracted with FFprobe when available. Full image
captioning and audio/video transcription require additional local AI models.
Encrypted files and unknown proprietary binary formats are reported as unsupported.

The local dashboard, sandbox integration, and agent loop are not part of this
Phase 1 foundation yet. No runtime cloud LLM API is used.

## Architecture

```text
                 +---------------------------+
                 | Local operator / terminal |
                 +-------------+-------------+
                               |
                 +-------------v-------------+
                 | Narrow safety + evidence  |
                 +------+------+-------------+
                        |      |
               +--------v+   +-v----------------+
               | SQLite  |   | Local KB / model |
               | NVD/KEV/|   | hybrid retrieval |
               | EPSS    |   +------------------+
               +---------+
```

## Read-only tools

The local assistant can call SearXNG, SearchSploit, and GitHub CLI adapters when
those services are installed and configured. See [UPGRADE_NOTES.md](./UPGRADE_NOTES.md)
for setup and safety boundaries. GitHub write actions and autonomous shell
execution are not enabled.

## Screenshot

The local Tkinter GUI is started with `python -m narrow.cli gui`.

## Locality and exposure

The planned web dashboard must bind to `127.0.0.1` only. It will have no
authentication by default; do not expose it on a network interface or through a
reverse proxy.

## Threat model

- **Prompt injection in tool output:** output is untrusted data, stripped of
  common instruction-like lines, and wrapped in `<untrusted>` tags.
- **Secret leakage:** known token formats and secret-valued environment variables
  are redacted before output is used.
- **Sandbox escape:** autonomous shell execution is disabled in this foundation.
- **Cache poisoning:** cache records are locally stored and timestamped; this
  phase does not authenticate cached data cryptographically.
- **GUI exposure:** the GUI is local desktop-only; no network server is exposed.
