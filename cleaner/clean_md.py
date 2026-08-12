"""markdown 清洗接口 — 供 document-to-markdown 等外部工具集成调用。

把清洗引擎封装成标准 CLI：读 .md 文件 → 规则清洗（去导航/水印/广告/乱码碎片）→
输出 JSON 到 stdout。外部通过子进程调用（如 document-to-markdown 的 clean_hook），
避免"内联 -c 代码"式集成（引号转义易错、输出解析脆弱）。

与 clean_asr_json.py（ASR 保结构）互补：本接口针对整篇文本/markdown。

用法:
    python -m cleaner.clean_md input.md [--anonymize] [--form markdown] [--output out.md]

输出(JSON, stdout, 强制 UTF-8):
    {"ok": true, "cleaned_text": "...", "engine": "plain", "stats": {...}}
    ok=false 时含 "error" 字段；退出码 0=成功, 1=失败。
"""
import argparse
import json
import os
import sys


def clean_md(filepath: str, anonymize: bool = False, form: str = "markdown") -> dict:
    """清洗 markdown 文件 → 返回结果 dict（JSON 序列化友好）。

    Args:
        filepath: .md 文件路径。
        anonymize: 是否 presidio PII 脱敏（默认 False，依赖 PRESIDIO_PY 配置）。
        form: 清洗形态（默认 "markdown" 走 common 规则；可传 "video_ocr" 等）。

    Returns:
        {"ok", "cleaned_text", "engine", "stats"}；文件不存在/异常时 ok=false + "error"。
    """
    if not os.path.isfile(filepath):
        return {"ok": False, "error": f"文件不存在或不是文件: {filepath}"}
    from cleaner.cleaning import clean_text
    raw = open(filepath, encoding="utf-8", errors="replace").read()
    res = clean_text(raw, anonymize=anonymize, form=form)
    return {
        "ok": bool(res.get("ok")),
        "cleaned_text": res.get("text", ""),
        "engine": res.get("engine", ""),
        "stats": res.get("stats", {}),
    }


def main():
    parser = argparse.ArgumentParser(description="markdown 清洗接口（供外部工具集成）")
    parser.add_argument("file", help="markdown 文件路径")
    parser.add_argument("--anonymize", action="store_true", help="presidio PII 脱敏(需配置)")
    parser.add_argument("--form", default="markdown", help="清洗形态(默认 markdown → common 规则)")
    parser.add_argument("--output", default="", help="同时把清洗结果写入该文件(可选)")
    args = parser.parse_args()

    result = clean_md(args.file, anonymize=args.anonymize, form=args.form)

    if args.output and result.get("ok"):
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result["cleaned_text"])

    # 强制 UTF-8 stdout（Windows GBK 控制台防乱码）
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
