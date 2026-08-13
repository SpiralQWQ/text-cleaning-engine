<p align="center">
  <!-- Cover: add assets/cover.png (1280x640) and uncomment the line below -->
  <!-- <img src="assets/cover.png" alt="text-cleaning-engine" width="800"> -->
</p>

<h1 align="center">text-cleaning-engine</h1>

<p align="center">
  <b>A rule-driven engine that turns dirty text — web pages, ASR transcripts, OCR output — into clean, RAG-ready text.</b>
</p>

<p align="center">
  Web pages · Plain text · ASR JSON (structure-preserving) · Video OCR / visual transcripts
</p>

<p align="center">
  <kbd>English</kbd> · <kbd><a href="README_zh.md">简体中文</a></kbd>
</p>

<p align="center">
  <a href="https://github.com/SpiralQWQ/text-cleaning-engine/actions/workflows/ci.yml"><img src="https://github.com/SpiralQWQ/text-cleaning-engine/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/SpiralQWQ/text-cleaning-engine/releases"><img src="https://img.shields.io/badge/version-0.6.1-blue" alt="version"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-3776AB" alt="Python 3.10+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL%203.0%20%7C%20Commercial-blue" alt="license"></a>
  <a href="#"><img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey" alt="platform"></a>
  <img src="https://img.shields.io/github/stars/SpiralQWQ/text-cleaning-engine" alt="GitHub stars">
  <img src="https://img.shields.io/github/last-commit/SpiralQWQ/text-cleaning-engine" alt="Last commit">
</p>

---

## Table of Contents

- [Why this engine](#why-this-engine)
- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Architecture](#architecture)
- [Transcript content protection (A-E)](#transcript-content-protection-a-e)
- [Integration](#integration)
- [Running Tests](#running-tests)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [FAQ](#faq)
- [Support](#support)
- [License](#license)

---

## Why this engine

Web scrapers and transcriber pipelines produce text full of **noise**: navigation bars, watermarks, UI remnants, repeated subtitles, OCR garbling, split lines. Hand-written cleaning code is a maintenance nightmare — every new site or transcript shape means a code change.

`text-cleaning-engine` pushes cleaning rules **into data** (`cleaning_rules.yaml`), so:

- **Add a new noise pattern without touching code** — edit the YAML, re-run.
- **Multi-action rules**, not just "delete": `delete` / `compress` / `protect` / `merge`.
- **Teaching content is never wrongly removed** — subtitles, IPA, translations and glossary lines are protected (see *Transcript content protection*).
- **Verifiable output** — a retention gate, residual-noise detector, and fallback to the original text when the cleaner over-deletes.

## Features

| Input shape | Handled noise | Output |
|-------------|---------------|--------|
| Web page HTML | navigation, ads, comments, hot-search, UI remnants | clean body text |
| Plain text (e.g. zhihu snapshot) | watermark, prompt text, recommendations | clean text |
| ASR transcript JSON (`text`+`segments`+`sentences`) | punctuation garbling, duplicate records, empty segments | structure-preserving `_clean.json` |
| Video OCR / visual transcript | frame markers, OCR tags, UI watermarks, split lines, repeated subtitles | clean transcript with teaching kept |

Core capabilities:

- **Multi-action rule engine** (YAML v4): `delete` · `compress_repeat` · `protect_teaching` · `merge_broken_lines`
- **Transcript content protection (A-E)**: subtitle compression (`原文…[出现N次]`), watermark deletion, OCR-garbling detection, broken-line merging, teaching whitelist
- **Structure-preserving ASR cleaning**: `start_ms`/`end_ms`/`confidence`/`review` untouched; Chinese teaching segments never deleted
- **Retention gate**: teaching-keep rate ≥ 95% (benchmarked); empty-output fallback if the cleaner removes > 70%
- **Residual-noise scan** + **content-integrity check** after every batch
- **PII scrubbing** via optional presidio (phone / email / ID → `***`)
- **Incremental + parallel batch cleaning**: file-hash + rule-fingerprint based, crash-resume safe

## Installation

**Requirements**: Python 3.10+

```bash
git clone https://github.com/SpiralQWQ/text-cleaning-engine.git
cd text-cleaning-engine
pip install -r requirements.txt
```

`requirements.txt` covers the main environment (`clean-text`, `snownlp`, `jsonschema`, `sentencex`, `PyYAML`). The optional HTML-extraction (`trafilatura`) and PII-scrubbing (`presidio`) tools run in their own venvs — see [`.env.example`](.env.example).

## Configuration

```bash
cp .env.example .env
# optional: point to your trafilatura / presidio python venvs and knowledge-base directory
```

The engine reads every tool path from the environment — **no hardcoded absolute paths** in the code. Configure only what you use.

| Env var | Purpose | Required |
|---------|---------|----------|
| `TRAFILATURA_PY` | python of the trafilatura venv (HTML body extraction) | only for real HTML input |
| `PRESIDIO_PY` | python of the presidio venv (PII scrubbing) | only with `--anonymize` |
| `CLEAN_KB` | input knowledge-base dir for batch cleaning | or use `--input` |

## Quick Start

The fastest path to a clean transcript — 3 commands, no extra config:

```bash
# 1. Clean an ASR transcript JSON (structure-preserving)
python -m cleaner.clean_asr_json transcript.json        # → transcript_clean.json

# 2. Preview what a dirty file becomes (no write)
python -m cleaner.cleaning --preview dirty.txt

# 3. Batch-clean a directory of text files
python cli/clean_batch.py --input ./texts --dry-run    # stats first
python cli/clean_batch.py --input ./texts --parallel 4 # → output/知识库_clean/
```

## Usage

```bash
# Clean a single file with before/after preview
python -m cleaner.cleaning --preview <file>

# Clean a single file (batch mode, prints summary)
python -m cleaner.cleaning --file <file>

# Clean an ASR transcript JSON (structure-preserving)
python -m cleaner.clean_asr_json transcript.json           # → transcript_clean.json

# Batch-clean a directory (incremental, parallel, residual-scan)
python cli/clean_batch.py --input <dir> --parallel 4       # → output/知识库_clean/

# Dry-run (stats only, no writes)
python cli/clean_batch.py --input <dir> --dry-run

# Optional PII scrubbing while batch-cleaning (needs PRESIDIO_PY)
python cli/clean_batch.py --input <dir> --anonymize

# Post-clean duplicate check (exact md5 + approximate similarity)
python cli/clean_batch.py --input <dir> --dedup
```

## Architecture

```
dirty text
 └─ cleaner/                 rule engine
     ├─ cleaning.py           multi-action engine (delete/compress/protect/merge) + residual scan
     ├─ clean_asr_json.py     ASR JSON → structure-preserving _clean.json
     ├─ clean_md.py           standard Markdown cleaning entry point (for external tools)
     └─ sentence_normalize.py sentence-level normalization (merges OCR split lines, protects frames)
 ├─ cli/clean_batch.py       batch pipeline (incremental · parallel · fallback · audit meta)
 ├─ rules/cleaning_rules.yaml rule data (per-form groups, multi-action v4)
 ├─ tests/                   retention gate (≥95%) + acceptance suite
 └─ docs/                    design, interface-contract, license-compliance reports
```

Rules are grouped by input form (`common` / `zhihu` / `video_ocr` / `video_asr`) and selected automatically. Adding a new site = add a group in the YAML, re-run.

## Transcript content protection (A-E)

Problems unique to video transcripts, and how the engine solves them:

| # | Problem | Solution |
|---|---------|----------|
| A | Repeated subtitles (video replays) | **compress** to `原文…[出现N次]` — signal kept, not deleted |
| B | UI watermarks in OCR frames | **delete** via anchored regex, teaching lines exempt first |
| C | OCR garbling (`garblec`→`garbage`) | **detect** with dictionary + fuzzy match, teaching exempt |
| D | OCR split lines (one subtitle → 2 lines) | **merge** with sentence normalization, time-adjacency check |
| E | Short teaching lines (IPA / translation / glossary) | **protect** via whitelist + fuzzy match, before any deletion |

## Integration

Pair `text-cleaning-engine` with [**document-to-markdown**](https://github.com/SpiralQWQ/document-to-markdown)
— a PDF / Word / PPT → Markdown converter built on MinerU — for a full document pipeline:

```
PDF / Word / PPT → (document-to-markdown) → Markdown → (text-cleaning-engine) → clean text → LLM
```

The standard cleaning entry point is callable from any external tool:

```bash
python -m cleaner.clean_md full.md [--anonymize]           # → JSON {ok, cleaned_text, stats}
python -m cleaner.clean_md full.md --output full_clean.md  # → also write the cleaned file
```

`document-to-markdown` calls this interface automatically via its `--clean` hook
(after conversion), stripping watermarks / navigation / garbled fragments before
the text reaches your LLM.

## Running Tests

```bash
# Acceptance suite (auto-skips items that need optional external samples)
python tests/test_acceptance.py

# Teaching-retention gate — guards against over-aggressive rules (≥95%)
python tests/test_teaching_retention.py

# 10-round deep verification (fuzz, Unicode, performance, red-line compliance)
python _tools/_verify_10rounds.py
```

> Optional external samples: set `CLEAN_TEST_ZHI_HU` (zhihu text dir) and
> `CLEAN_TEST_VIDEO_FILE` (video transcript) to run the full suite locally.
> Without them the dependent items are skipped gracefully — clone-and-run works out of the box.

## Documentation

| Doc | What it covers |
|-----|----------------|
| [`docs/视频转写清洗方案_v1.0.md`](docs/视频转写清洗方案_v1.0.md) | design of transcript (OCR/ASR) cleaning rules |
| [`docs/接口对接/接口对接报告.md`](docs/接口对接/接口对接报告.md) | input contract: transcript JSON → clean JSON (format / red lines / API + examples) |
| [`docs/开源许可合规_v1.0.md`](docs/开源许可合规_v1.0.md) | dependency-license compliance (AGPL-3.0 feasibility) |

## Contributing

Contributions of any kind are welcome — new rule groups, noise patterns, bug reports, docs, tests. Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

## FAQ

**Q: Does cleaning run on the GPU / need a heavy ML stack?**
No. The core engine is pure Python (regex + dictionaries + rule data). The optional `trafilatura` / `presidio` venvs are lightweight and only used when configured.

**Q: Will it delete my teaching content (subtitles / translations)?**
No — that's the core design guarantee. Teaching lines (IPA, translations, word cards, teaching English) are protected before any deletion rule runs, and a retention gate (≥95%) plus a >70% over-delete fallback guards the output.

**Q: How do I add a new noise pattern?**
Edit `rules/cleaning_rules.yaml` — add a substring / regex to the matching form group (or a new group), re-run. No code change. A JSON-schema check catches typos.

**Q: Why does the batch output path contain `知识库_clean`?**
That is the default mirror directory (see `cli/clean_batch.py`); every cleaned file keeps its relative path so the cleaned library stays navigable.

**Q: The `--preview` output looks shorter than expected.**
The preview is capped at the first 300 characters of the before/after text. Run `--file` or batch mode for full output.

## Support

If this project has helped you in any way, you're welcome to buy me a coffee. It's completely voluntary — the project stays free and open-source regardless. For an independent developer, every small token of appreciation matters.

<p align="center">
  <img src="assets/donate_wechat.jpg" alt="WeChat Pay" width="200">
  <img src="assets/donate_alipay.jpg" alt="Alipay" width="200">
</p>

<p align="center"><i>Thanks for reading all the way down here. 🙏</i></p>

## Changelog

All versions are tracked in [CHANGELOG.md](CHANGELOG.md) (English) and [CHANGELOG_zh.md](CHANGELOG_zh.md) (中文).

## License

`text-cleaning-engine` is **dual-licensed**:

1. **Open Source** — [GNU Affero General Public License v3 (AGPL-3.0)](LICENSE)
2. **Commercial** — for use cases where AGPL-3.0 obligations are not acceptable, see [COMMERCIAL.md](COMMERCIAL.md)

Copyright (c) 2026 Spiral QWQ. All rights reserved.
