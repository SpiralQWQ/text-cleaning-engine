# Contributing to text-cleaning-engine

Thanks for considering a contribution! This project is small but cares about the details — every rule, regex and test matters. Any kind of help is welcome: new noise patterns, new rule groups, bug reports, docs, tests, or a better translation.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How to report a bug](#how-to-report-a-bug)
- [How to propose a feature](#how-to-propose-a-feature)
- [Setting up the dev environment](#setting-up-the-dev-environment)
- [Running the tests](#running-the-tests)
- [The most useful contribution: a new noise rule](#the-most-useful-contribution-a-new-noise-rule)
- [Coding style](#coding-style)
- [Pull request workflow](#pull-request-workflow)

## Code of Conduct

Be respectful and constructive. Disagreements are fine; personal attacks are not. This project has no formal CoC document yet — treat everyone the way you would want to be treated.

## How to report a bug

Open an [issue](https://github.com/SpiralQWQ/text-cleaning-engine/issues/new) and include:

1. What you ran (the exact command).
2. A **small** before/after sample (the dirtier the better — real noise samples are gold).
3. Expected vs. actual output.
4. Your OS / Python version, and whether the optional venvs (`TRAFILATURA_PY`, `PRESIDIO_PY`) were configured.

> Sample data is what makes this engine tick. Even a 5-line snippet of a noise pattern the rules miss is a valuable issue.

## How to propose a feature

Open an issue with a short description of the problem and the shape of input it affects (web HTML / plain text / ASR JSON / video OCR). Because rules live in `cleaning_rules.yaml`, many "features" are actually just a new rule group or a few regexes — see below.

## Setting up the dev environment

```bash
git clone https://github.com/SpiralQWQ/text-cleaning-engine.git
cd text-cleaning-engine
pip install -r requirements.txt
```

The optional `trafilatura` / `presidio` venvs are only needed when you touch HTML extraction or PII scrubbing — see [`.env.example`](.env.example).

## Running the tests

```bash
python tests/test_teaching_retention.py   # teaching-keep gate (≥95%)
python tests/test_acceptance.py           # acceptance suite (SKIPs without external samples)
python _tools/_verify_10rounds.py         # 10-round deep verification (fuzz / Unicode / perf / red-lines)
```

All three must pass before a pull request is merged. If your change touches cleaning behavior, also extend the benchmark in `tests/teaching_benchmark.json` with the cases you fixed — every labeled case makes the gate stronger.

## The most useful contribution: a new noise rule

The engine is designed so that **most new noise needs zero code**:

1. Open `rules/cleaning_rules.yaml`.
2. Pick the matching form group (`common` / `zhihu` / `video_ocr` / `video_asr`), or add a new group.
3. Add the substring to `noise_substr`, or a regex to `noise_regex`.

Three pitfalls to avoid:

- **Prefer anchored regex over substring** for UI watermarks (`^坚持打卡`), so GLM descriptions mentioning the same text are not deleted.
- **Never add a teaching-like short line** to the delete rules — IPA, translations and word cards are protected for a reason. Add them to `protect_teaching.teaching_words` instead.
- **Re-run the gate** — a rule that drops teaching retention below 95% will (and should) fail CI.

## Coding style

- Match the surrounding code: the codebase uses Chinese comments, `_snake_case` helpers, and conservative, comment-first style.
- Prefer the simplest implementation that is safe — "宁漏删不误删" (rather under-delete than over-delete) is a design principle.
- No hardcoded absolute paths, no API keys, no machine-local references — everything configurable goes through `.env` / environment variables.
- Keep changes minimal and scoped to the task.

## Pull request workflow

1. Fork the repo and create a branch (`fix/…`, `feat/…`, `docs/…`).
2. Make your change, add/adjust tests, run all three test commands.
3. Open a pull request describing what changed and why. If it changes cleaning behavior, show a small before/after sample.
4. The maintainer reviews and merges. Small, focused PRs get merged faster than large ones.

**Commit message convention** (Conventional Commits):

```
feat: add <what>
fix: correct <what>
docs: update <what>
test: add coverage for <what>
```

Copyright (c) 2026 Spiral QWQ. Licensed under the terms of the repository license.
