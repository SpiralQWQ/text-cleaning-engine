"""ASR json 逐段清洗 → 保结构 _clean.json（接口契约 v1.1 原型）

上游转写工具 转写 json（text + segments + sentences）→ 清洗后保 json 结构输出 _clean.json。
遵守接口红线：
  1. segments/sentences 结构不拼平（逐段/逐句清洗）
  2. start_ms/end_ms/confidence/review 不改值
  3. 中文讲解段永不删（教学精华）
  4. srt 不清洗（本脚本不碰 srt）

去重逻辑（接口契约 v1.1 R3）：
  - 同文本 + 同时间戳 → 数据重复记录 → 删后留前
  - 同文本 + 不同时间戳 → 视频重播（中间夹中文讲解） → 保留
  - 带中文的段 → 永不删

用法:
    python -m cleaner.clean_asr_json input.json [output.json]
"""
import json
import os
import re
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8') if sys.stdout.encoding.lower() != 'utf-8' else sys.stdout

# 标点乱码规范化（与 cleaning.normalize_stage1 一致）
_PUNCT_PAIRS = [
    (re.compile(r",{2,}"), ","),
    (re.compile(r"\.{2,}"), "."),
    (re.compile(r"\?{2,}"), "?"),
    (re.compile(r",\."), "."),
    (re.compile(r"\.,"), "."),
    # 中文标点乱码(中文 ASR 常见): 。，→。 / ，。→。 / 。。→。 / ，，→，
    (re.compile(r"。，"), "。"),
    (re.compile(r"，。"), "。"),
    (re.compile(r"。{2,}"), "。"),
    (re.compile(r"，{2,}"), "，"),
]

def _norm_punct(text: str) -> str:
    """标点乱码规范化（ASR 转写常见）: ,,→, / ..→. / ??→? / 。，→。 / ，。→。"""
    for rx, repl in _PUNCT_PAIRS:
        text = rx.sub(repl, text)
    return text.strip()


def _segment_key(text: str) -> str:
    """段文本 → 归一化指纹（小写+去非字母数字+去空白），用于重复检测。"""
    return re.sub(r"[^a-z0-9一-鿿]", "", text.lower())


def _has_chinese(text: str) -> bool:
    """段是否含中文（教学讲解标记）。"""
    return any("一" <= ch <= "鿿" for ch in text)


def _dedup_segments(segments: list[dict]) -> list[dict]:
    """段级去重：同文本+同时间戳=数据重复记录删后留前；中文段永不删。

    Returns:
        去重后的 segments 列表（保持原顺序）。
    """
    seen = {}   # key -> (index, 时间戳特征) 已见过的段
    kept = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        text = seg.get("text") or ""
        key = _segment_key(text)
        ts = (seg.get("start_ms"), seg.get("end_ms"))
        if _has_chinese(text):
            # 中文讲解段永不删
            kept.append(seg)
            seen[key] = (len(kept) - 1, ts)
            continue
        if key in seen:
            prev_idx, prev_ts = seen[key]
            if prev_ts == ts:
                # 同文本 + 同时间戳 → 数据重复记录 → 删后留前（跳过本段）
                continue
            # 同文本 + 不同时间戳 → 视频重播 → 保留
            kept.append(seg)
        else:
            kept.append(seg)
            seen[key] = (len(kept) - 1, ts)
    return kept


def _clean_text_segment(text: str) -> str:
    """单段 text 清洗：标点乱码规范化 + 空白规整（不拼平、不改结构）。

    注意：不做语义级纠错（词级错误留给 Claude，见接口开放问题 #3 定案）。
    """
    if text is None:
        return ""
    t = _norm_punct(text)
    t = re.sub(r"[ \t　]+", " ", t)
    t = t.strip()
    # 纯标点/纯空白段 → 清空（如 ",,. . ??" 规范化后只剩 ". . ?" 无实际内容）
    if not re.search(r"[A-Za-z0-9一-鿿]", t):
        return ""
    return t


def clean_asr_json(data: dict) -> dict:
    """清洗 ASR json：逐段/逐句清洗 text，保留结构/时间戳/review/confidence。

    健壮性：data 非 dict / segments·sentences 为 None 或非 list 时安全降级（[]），不崩溃。

    Returns:
        保结构的 dict（与原 json 同构），可直接 dump 为 _clean.json。
    """
    if not isinstance(data, dict):
        return {"text": "", "segments": [], "sentences": []}
    segs_in = data.get("segments") or []
    sents_in = data.get("sentences") or []
    if not isinstance(segs_in, list):
        segs_in = []
    if not isinstance(sents_in, list):
        sents_in = []
    out = {
        "text": _clean_text_segment(data.get("text", "")),
        "segments": [],
        "sentences": [],
    }
    # segments: 逐段清洗 + 段级去重
    segs = _dedup_segments(segs_in)
    for seg in segs:
        if not isinstance(seg, dict):
            continue
        cleaned = _clean_text_segment(seg.get("text", ""))
        out["segments"].append({
            "text": cleaned,
            "start_ms": seg.get("start_ms"),
            "end_ms": seg.get("end_ms"),
            "confidence": seg.get("confidence"),
            "review": seg.get("review", False),
        })
    # sentences: 逐句清洗（保留全部，不去重——句是段内结构）
    for sent in sents_in:
        if not isinstance(sent, dict):
            continue
        cleaned = _clean_text_segment(sent.get("text", ""))
        out["sentences"].append({
            "text": cleaned,
            "start_ms": sent.get("start_ms"),
            "end_ms": sent.get("end_ms"),
            "confidence": sent.get("confidence"),
        })
    return out


def main():
    if len(sys.argv) < 2:
        print("用法: python -m cleaner.clean_asr_json input.json [output.json]")
        sys.exit(1)
    src = sys.argv[1]
    data = json.load(open(src, encoding="utf-8"))
    result = clean_asr_json(data)
    if len(sys.argv) >= 3:
        dst = sys.argv[2]
    else:
        dst = os.path.splitext(src)[0] + "_clean.json"
    with open(dst, "w", encoding="utf-8", newline="") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"✅ 已生成: {dst}")
    print(f"   segments: {len(data.get('segments', []))} → {len(result['segments'])} (去重 {len(data.get('segments', [])) - len(result['segments'])} 段)")
    print(f"   sentences: {len(data.get('sentences', []))} → {len(result['sentences'])}")


if __name__ == "__main__":
    main()
