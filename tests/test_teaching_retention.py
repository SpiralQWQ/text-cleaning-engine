"""教学保留率门禁 — 防规则误删教学内容

用 tests/teaching_benchmark.json 标注基准集验证：
- 该保留的（教学台词/中文翻译/音标/单词卡/教学英文）必须保留
- 该删的（水印/OCR乱码）必须删除
- 教学保留率 ≥ 95% 才算通过

用途: 每次改 cleaning 规则后跑一次，防"规则越改越激进误删教学"（对应 400 调研 R4 门禁思想）
用法: python tests/test_teaching_retention.py
"""
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, PROJ)

from cleaner import cleaning as c

THRESHOLD = 0.95  # 教学保留率阈值


def main():
    bench = json.load(open(os.path.join(SCRIPT_DIR, "teaching_benchmark.json"), encoding="utf-8"))
    cases = bench["cases"]
    teach_total = sum(1 for x in cases if x["expect"] == "keep")
    teach_kept = 0
    errors = []

    for i, case in enumerate(cases):
        text = case["text"]
        res = c.clean_text(text, form="video_ocr")
        cleaned = res["text"]
        kept = text.strip() in cleaned or (text.strip() == "" and cleaned == "")

        expect = case["expect"]
        if expect == "keep":
            if kept:
                teach_kept += 1
            else:
                errors.append(f"❌ 教学被误删 [{i}]: 「{text}」")
        elif expect == "delete":
            if kept:
                errors.append(f"❌ 噪音未删 [{i}]: 「{text}」")
        # compress: 单行场景不验证（压缩需多行上下文），留 T8 后补

    print("=" * 50)
    print(f"教学保留率门禁 — {len(cases)} 条基准")
    print(f"  教学样本: {teach_total} | 保留: {teach_kept} | 误删: {teach_total - teach_kept}")
    for e in errors:
        print(f"  {e}")

    retention = teach_kept / max(1, teach_total)
    print(f"  教学保留率: {retention:.0%} (阈值 {THRESHOLD:.0%})")
    passed = retention >= THRESHOLD and not errors
    print(f"  结果: {'✅ 通过' if passed else '❌ 失败'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
