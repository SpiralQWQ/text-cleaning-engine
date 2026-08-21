# Acceptance Report · noise_inline + channel-watermark cleaning (v0.7.0)

> Date: 2026-08-21
> Scope: text-cleaning-engine gains `noise_inline` (in-line watermark removal) and a
> precise `clean_watermark_text()` entry / `clean_md.py --watermark-only` for
> document-to-markdown to strip channel ad watermarks (QQ-group / WeChat / email)
> without touching any other content.
> Process: S1 task breakdown → S3 per-task 4-round review → S2 exhaustive tests → S4 final acceptance.

---

## 1. Conclusion

**PASS.** Channel-watermark cleaning implemented and verified: rules tolerate OCR
variants while never matching plain "微信公众号" in TOC / code / teaching lines; precise
mode leaves all non-watermark content untouched (100% retention). 14 tests pass
(noise_inline + watermark_text); real-document residual dropped 3 → 0.

## 2. Task checklist (S1)

| Task | Content | Acceptance |
|---|---|---|
| B-01 | `noise_inline` in-line watermark removal (cleaning.py + schema + rules) | ✅ |
| B-02 | channel-watermark rules (QQ-group / WeChat / email / public-account + fallback phrases) | ✅ |
| B-03 | verification + tests (14) + real-doc residual 3→0 | ✅ |
| B-04 | integration entry `clean_watermark_text()` + `--watermark-only` for document-to-markdown | ✅ |

## 3. Exhaustive test results (S2)

### ① Paths
| Entry | Endpoint | Result |
|---|---|---|
| `clean_text(form="markdown")` | full rules + inline removal | ✅ |
| `clean_watermark_text(text)` | precise, watermark only | ✅ |
| `clean_md.py --watermark-only` | CLI precise mode | ✅ |

### ② Boundaries
- Spliced watermark (header + body on one line) → watermark stripped, body kept
  (`## 欢迎加入QQ群xxx免费领书！ 1.8 使用TensorFlow` → `## 1.8 使用TensorFlow`).
- Standalone ad lines (QQ-group number / email+WeChat / public-account) → removed.
- OCR variants (mis-OCRed channel words) → tolerated by regex.
- Fallback phrases ("免费提供…本Python书籍", "非盈利…学习交流…") → stripped.
- **No false positives**: TOC "微信公众号文章", teaching "在微信公众号中回复",
  code comments (in-code protection), plain body → all kept.
- Empty lines preserved (structure); code blocks untouched.

### ③ Endpoint consistency
- `clean_watermark_text` vs `clean_md.py --watermark-only` → same output (verified).
- dry-run / real runs agree; real document residual 3 → 0 with 100% content retention.

## 4. Per-task 4-round review (S3, summary)

Completion / regression / hidden defect / design — key fixes:
- Empty-line deletion in `clean_watermark_text` → keep original blank lines (structure).
- "微信公众号" regex too broad (matched TOC "微信公众号文章") → guarded by "（微信号" structure.
- Trailing "！" after stripped watermark → regex eats `[！!]?\s*`.

## 5. Final acceptance (S4)

- Regression: 14/14 tests pass (noise_inline + watermark_text); `cleaning.py` / `clean_md.py` compile.
- Original teaching-retention logic unaffected (no shared-rule changes).
- CHANGELOG (en/zh) updated with 0.7.0.

## 6. Naming & location

- This report: `docs/acceptance-report-v0.7.0.md`
- CHANGELOG: `CHANGELOG.md` / `CHANGELOG_zh.md` (0.7.0)
- Source: `cleaner/cleaning.py` (noise_inline + clean_watermark_text), `cleaner/clean_md.py`
  (--watermark-only), `rules/cleaning_rules.yaml` (rules)
- Tests: `tests/test_noise_inline.py`, `tests/test_watermark_text.py`, `tests/conftest.py`
