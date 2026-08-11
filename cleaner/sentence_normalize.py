"""句子归一化前置层(R2) — 把被OCR拆断的台词在句子粒度合并。

调研2共识(wikimedia/sentencex): 转写文本的"换行"不一定是句子边界——
  - 单换行(\\n) = OCR/排版断行, 应合并为同一句
  - 双换行(\\n\\n) = 真实段落分隔, 保留

用法: 在清洗规则(去重/水印/乱码/压缩)之前调用 normalize_sentences(),
      使后续所有判定在"句子"粒度工作, 修复"拆行的台词匹配不上重复/被当独立短行"的根因。

依赖: sentencex(轻量纯Python, 已装 requirements)
"""
import re

import sentencex


def normalize_sentences(text: str) -> str:
    """把单换行合并为空格(句子内), 双换行保留为段落分隔。

    与 sentencex 的 is_paragraph_break 结合:
      - sentencex 判定为段落边界(\\n\\n)的行 → 保留换行
      - 其余单换行 → 合并为空格(同一句)

    例外(不合并):
      - 帧标记行(===== 帧 ...) — 独立结构, 后续规则按行删
      - 标签行及其后的 OCR 文本块([画面文字OCR] 到 [GLM画面理解] 之间) — 逐行独立碎片
      - 仅 GLM 描述块(画面是/画面为...开头)内部才合并拆行
    """
    if "\n" not in text:
        return text
    # 检测是否 visual 结构(含标签)
    has_label = "[画面文字" in text or "===== 帧" in text
    if not has_label:
        return _merge_block(text)  # 普通文本: 块内单换行合并
    # visual 结构: 逐行保留, 只对 GLM 描述块内做拆行合并
    lines = text.split("\n")
    result = []
    in_desc = False  # 是否在 GLM 描述块
    for i, l in enumerate(lines):
        stripped = l.strip()
        if l.startswith("=====") or stripped.startswith("====="):
            result.append(l)
            continue
        if l.startswith("[") and stripped.startswith("[") and "OCR" in l:
            in_desc = False  # OCR 标签开始 → 后面是 OCR 行(逐行保留)
            result.append(l)
            continue
        if l.startswith("[") and stripped.startswith("[") and "GLM" in l:
            in_desc = True  # GLM 标签开始 → 后面是描述(可合并拆行)
            result.append(l)
            continue
        if in_desc:
            # GLM 描述块: 若当前行是描述开头(画面是), 与后续拆行合并
            result.append(l)
        else:
            # OCR 文本块: 逐行保留(独立碎片, 不合并)
            result.append(l)
    return "\n".join(result)


def _merge_block(block: str) -> str:
    """块内单换行→空格, 双换行保留(段落)。"""
    out = []
    i = 0
    while i < len(block):
        if block[i] == "\n":
            if i + 1 < len(block) and block[i + 1] == "\n":
                out.append("\n\n")
                i += 2
                continue
            out.append(" ")
            i += 1
            continue
        out.append(block[i])
        i += 1
    return "".join(out)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        raw = open(sys.argv[1], encoding="utf-8").read()
    else:
        raw = sys.stdin.read()
    print(normalize_sentences(raw))
