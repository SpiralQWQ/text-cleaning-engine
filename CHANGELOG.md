# Changelog
All notable changes to text-cleaning-engine are documented here, following [Keep a Changelog](https://keepachangelog.com/en/1.0.0/). Versioning follows [Semantic Versioning](https://semver.org/).

## [0.5.0] — 2026-08-11 · Transcript content protection (A–E)

**Added — teaching-vs-noise classification (core)**
- Teaching-whitelist protection (E): `_is_teaching_line` detects IPA / Chinese translation / word cards / teaching English (word list + fuzzy match), runs before all deletion
- Garbling detection (C): `_is_garbled` = dictionary zero-hit + no vowels + char entropy, teaching lines exempt, conservative by default
- Broken-line merging (D): `merge_broken_lines` merges lines with no terminal punctuation + lowercase next line + time adjacency; teaching lines excluded
- Subtitle compression (A): `compress_repetition` compresses repeated teaching subtitles to `原文…[出现N次]` (not deleted — keeps the emphasis signal)

**Fixed — root cause of problem A**
- Removed the "delete whole line repeated ≥3×" rule (`high_freq`) in `cleaning.py` — it mistook teaching subtitles / Chinese translations (video replays) for watermarks; replaced with compression-preserve

**Rules upgrade (R1, YAML v3 → v4)**
- Rule engine upgraded from boolean-delete to multi-action: `protect_teaching` / `compress_repeat` / `watermark` / `garbled` configurable blocks, parameters externalized

**Sentence-granularity prep (R2)**
- New `cleaner/sentence_normalize.py` + `sentencex` dependency: transcript sentences normalized first (merges OCR split subtitles), frame markers / OCR text blocks independently protected — fixes "split subtitle doesn't match repetition detection" root cause

**Engineering hardening (R3/R4)**
- `clean_batch.py` empty-output fallback: retention <30% → revert to original (prevents deleting 70%+ of teaching)
- Audit fields: output meta records `fallback` / `residual` / `content_issue` for traceability
- Teaching-retention gate: `tests/teaching_benchmark.json` (30 labeled cases) + `test_teaching_retention.py` (≥95%)

**Acceptance**: T1–T12 reviewed one by one; verified on a real 179-frame transcript (subtitle compression kept / garbling removed / broken lines merged / teaching kept / watermarks deleted); teaching retention 100%; zero regression on the original 14-item suite — see `docs/验收报告_v3.0.md`

---

## [0.4.0] — 2026-08-11 · Interface adaptation (stage 0, transcript-JSON input)

**Added — structure-preserving ASR JSON cleaning (prototype)**
- `cleaner/clean_asr_json.py`: cleans ASR JSON (`text` + `segments` + `sentences`) segment-by-segment / sentence-by-sentence, **keeps the JSON structure** → `_clean.json` (original kept for traceability)
- Interface red lines honored: structure not flattened / Chinese teaching never deleted / `start_ms`·`confidence`·`review` untouched / srt not cleaned
- Segment-level dedup: same text + same timestamps = duplicate record, keep the first; same text + different timestamps = video replay, keep; Chinese segments never deleted
- Punctuation-garbling normalization (`??`→`?`, `,,`→`,` …) + empty segment clearing + safe degradation on empty input

**Fixed**
- Rule-fingerprint path bug in `clean_batch.py`: referenced `config/` (doesn't exist) → `rules/`, restoring "rule change triggers incremental re-clean"

**Rules expansion**
- `cleaning_rules.yaml`: 8 new video UI-watermark regexes (`^坚持打卡` / `^片名：` / `^知识点\d+` / `^高手盲听` / `^初学看字幕` / `^纯英[文宇字]+幕$` / `^爱说英语的福安` / `^爱悦英烫`), line-start anchored to avoid deleting GLM scene descriptions; fixes watermark under-deletion on short samples

**Docs**
- `docs/接口对接/`: interface-contract report + examples (format / red lines / API)
- `docs/补丁重构计划_v1.1.md`: interface contract + open-question resolutions
- `docs/验收报告_v2.0.md`: stage-0 interface acceptance

**Acceptance**: T1–T7 reviewed one by one; 15/15 interface red lines honored; `_clean.json` structure-preserving; original 14-item suite all green (zero regression)

---

## [0.3.0] — 2026-08-10 · Standalone module

**Restructure**:
- Extracted from the crawler project `_crawl` into a standalone module (sibling of `_crawl`)
- Layered layout: `cleaner/` (engine) `cli/` (commands) `rules/` (rule data) `tests/` (acceptance) `docs/` (docs) `output/` (runtime output)
- Decoupled `upstream.config` dependency (tool paths read `.env`, KB parameterized, output to `output/`)
- `.env.example` tool-path template (for open source); independent `requirements.txt`

**Acceptance**: `tests/test_acceptance.py` 14/14; 40-article zhihu full clean (0 residual, body intact) to the standalone project; `_crawl` originals removed (standalone is the single source)

---

## [0.2.0] — 2026-08-10 · Video-transcript form + engineering hardening

**Added — video-transcript cleaning (V)**
- `video_ocr` rule group: frame markers (`=====`) / OCR tags (`[画面文字OCR]`) / GLM tags cleared; per-frame repeated watermarks auto-deleted by the high-freq rule (GLM scene descriptions kept)
- `video_asr` rule group: ASR punctuation-garbling normalization (`,,`→`,`、`..`→`.`、`??`→`?`、`,.`→`.`, universal)
- Engine selects rules by form (`clean_text(form=...)`), each form uses its own groups
- MD code-block protection (``` fenced content not wrongly deleted)
- Transcript cleaning design doc (`视频转写清洗方案.md`)

**Engineering hardening (E)**
- E1/E9 incremental cleaning + crash-resume: file hash + rule fingerprint; unchanged skipped, rule change re-cleans, interrupted resumes without loss
- E2 structured index (`_clean_results.json`)
- E3 cleaning log (`logs/clean_kb.log`)
- E4 parallel batch cleaning (`--parallel N`)
- E5 post-clean dedup check (`--dedup`, exact md5 + approximate similarity)
- E6 quality-assertion extension (English videos no longer false-report "low Chinese")
- E7 rule version management (YAML `version` + `规则变更日志.md`)
- E8 cleaning stats report (`_clean_report.json`, historical accumulation)
- E11 worker failure retry ×3

**Acceptance**: suite extended to 14 items all green (incl. video_ocr / video_asr / MD / rule validation); 40 zhihu articles incrementally skipped, 0 residual, body intact, 0 dedup.

---

## [0.1.0] — 2026-08-10 · Initial workflow

**Core pipeline**: Stage0–5 (trafilatura body extraction / clean-text normalization / snownlp analysis / jsonschema validation / presidio scrubbing) + custom Chinese rules (navigation / watermark / AI markers / comments / hot-search / ads removal)

**Rule datafication**: `cleaning_rules.yaml` (`noise_substr` / `noise_regex` / `keep_headings` / `lanmu_buttons` / `question_title`, common+zhihu groups), jsonschema-validated against typos

**Detection & quality**: `scan_residual` residual detector (6 classes) + `check_content_integrity` body integrity (prevents over-deletion)

**Form branching**: `is_html_like` plain-text/HTML adaptive; structural-algorithm fallback chain (trafilatura → jusText → dragnet)

**Engineering**: `clean_kb.py` batch cleaning → `知识库_clean/`; 40 zhihu articles cleaned into RAG (bge-m3, 100% accuracy)

**Acceptance**: 18 minimal tasks reviewed one by one + acceptance report

[0.5.0]: https://github.com/SpiralQWQ/text-cleaning-engine/releases/tag/v0.5.0
[0.4.0]: https://github.com/SpiralQWQ/text-cleaning-engine/releases/tag/v0.4.0
[0.3.0]: https://github.com/SpiralQWQ/text-cleaning-engine/releases/tag/v0.3.0
[0.2.0]: https://github.com/SpiralQWQ/text-cleaning-engine/releases/tag/v0.2.0
[0.1.0]: https://github.com/SpiralQWQ/text-cleaning-engine/releases/tag/v0.1.0
