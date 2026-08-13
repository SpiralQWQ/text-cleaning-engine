"""文本清洗模块 — 把爬下来的脏文本清洗成可入知识库的干净文本。

当前数据形态(2026-08-09):
  知乎搜索结果页文本快照 40 篇(实为纯文本, 无 HTML 标签; 之前误判为 .html)
  主要噪音: 导航文字 / 答主水印 / AI标记 / 广告 / 零宽字符 / 相关内容推荐区

清洗流水线(各 task 逐步叠加):
  Stage0  trafilatura 网关  #87 — HTML 输入 → 提取正文去导航(favor_precision)
  Stage1  clean-text 归一化 #88 — Unicode/HTML实体/空白/URL
  Stage2  snownlp 中文辅助  #89 — 分词/水印识别
  Stage3  自研中文规则      #92 — 去答主水印/AI标记/广告
  Stage4  jsonschema 体检   #90 — 结构校验
  Stage5  presidio 脱敏     #91 — PII 打码

trafilatura/presidio 装于各自独立 venv(路径经 .env 配置),
均经 .env 定位, subprocess 调用 — 与 yt-dlp/ffmpeg 同模式, 不污染主环境。
clean-text/snownlp/jsonschema 为轻量纯 Python 库, 直接装主环境(requirements.txt), import 调用。

用法:
    python -m cleaner.cleaning --file <path>             # 清洗单文件
    python -m cleaner.cleaning --dir <dir> --suffix html # 批量清洗目录
    python -m cleaner.cleaning --preview <path>          # 预览清洗前后对比
"""
import argparse
import html
import os
import re
import subprocess
import sys
from collections import Counter

def _load_env() -> None:
    """加载项目根 .env(工具路径配置), 不依赖外部包。"""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_env()

# 零宽字符(知乎快照常见): 零宽空格/零宽不换行/零宽连接/零宽非连接/BOM
_ZERO_WIDTH = re.compile(r"[​‌‍﻿]")
# 真 HTML 标签(排除 >>广告<< 的 <): <div> </div> <p ...>  — < 后必须是字母
_HTML_TAG = re.compile(r"</?[a-zA-Z][\w.-]*")
# 带协议 URL(clean-text 缺失时降级用)
_URL = re.compile(r"https?://\S+|www\.\S+")
# 连续空白(含全角空格) → 单空格
_SPACES = re.compile(r"[ \t　]+")
# 空行规整: 连续 2+ 空行 → 1 个空行
_BLANK_LINES = re.compile(r"\n\s*\n+")

# 标点乱码规范化(ASR/OCR 转写常见, V3): 逗号/句号/问号连排, ,. / .,
#   如 "we have the new baby ,. The" → "we have the new baby . The"
_PUNCT_PAIRS = [
    (re.compile(r",{2,}"), ","),   # ,,, → ,
    (re.compile(r"\.{2,}"), "."),  # .. → .
    (re.compile(r"\?{2,}"), "?"),  # ?? → ?
    (re.compile(r",\."), "."),     # ,. → .
    (re.compile(r"\.,"), "."),     # ., → .
]

# ═══════ Stage3 自研中文规则(#92): 规则数据化(A1/A2) ═══════
# 规则权威源: rules/cleaning_rules.yaml (加噪音=改配置, 按站点分组 common/zhihu)
# 引擎降级: YAML 缺失/损坏 → 用内置默认, 不阻断流水线

# 内置默认规则(YAML 缺失时降级用)
_DEFAULT_SUBSTR = [
    "以上内容由 AI 生成", "以上内容由AI生成", "京ICP", "下载同款", "简历神器",
    "简历诊断", "阅读全文", "结果由 AI 大模型生成",
    "添加评论", "展开更多", "复制", "分享", "完成回答，用时", "全部来源",
    "内容发现", "相关搜索", "大家都在搜", "换一换", "深度搜索", "篇内容 AI 总结",
    "综合用户论文AI", "搜索专栏盐选内容", "写回答", "订阅", "精选专业知识库",
    "权威内容专家精选", "输入你的问题", "快捷引用", "0元做简历", "亲测好用",
    "神级", "秒杀", "高光履历",
]
_DEFAULT_REGEX = [
    r"[\d. ]+万?\s*赞同", r"赞同\s*[\d. ]+万?", r"[\d.]+\s*条?\s*评论",
    r"\d+\s*篇精选内容", r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$", r"^\d{1,2}[-/]\d{1,2}$",
    r"\d+\s*(分钟|小时|天)前", r"^(昨天|前天|今天)\s*\d{1,2}:\d{2}", r"^热$",
    r"^\d[\d 万.]*万$",
]
_DEFAULT_HEADINGS = {
    "教育经历", "求职意向", "工作经历", "项目经历", "基本信息", "专业技能",
    "证书", "自我评价", "实习经历", "荣誉奖项", "技能证书", "教育背景",
    "联系方式", "个人优势", "项目经验", "校园经历",
}
_DEFAULT_LANMU = {"量化成果", "工具推荐", "应届生急救", "STAR法则", "避坑指南", "深度搜索", "换一换"}


def _load_rules() -> dict:
    """加载 rules/cleaning_rules.yaml(规则权威源); 缺失 → {} 用内置默认。

    格式校验(G): 用 jsonschema 校验 YAML 结构, 正则写错/分组打错 → 明确报错,
    避免"静默失效"(规则坏了清洗悄悄变差却无人知)。
    """
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "rules", "cleaning_rules.yaml")
    try:
        import yaml as _yaml
        if not os.path.exists(path):
            return {}  # 缺失 → 正常降级内置默认
        with open(path, encoding="utf-8") as f:
            rules = _yaml.safe_load(f) or {}
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"cleaning_rules.yaml 读取失败: {e}") from e
    # schema 校验(jsonschema): 结构错 → 明确报错, 不静默
    import jsonschema
    try:
        jsonschema.validate(rules, _RULES_SCHEMA)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"cleaning_rules.yaml 格式校验失败: {e}") from e
    return rules


# cleaning_rules.yaml 的结构 schema(jsonschema, G 校验用)
_RULES_SCHEMA = {
    "type": "object",
    "required": ["noise_substr", "noise_regex", "keep_headings", "lanmu_buttons", "question_title"],
    "properties": {
        "version": {"type": "integer"},
        "noise_substr": {  # 按站点分组的固定噪音词: {common:[...], zhihu:[...]}
            "type": "object",
            "additionalProperties": {"type": "array", "items": {"type": "string"}},
        },
        "noise_regex": {"type": "array", "items": {"type": "string"}},
        "keep_headings": {"type": "array", "items": {"type": "string"}},
        "lanmu_buttons": {"type": "array", "items": {"type": "string"}},
        "question_title": {
            "type": "object",
            "properties": {
                "min_len": {"type": "integer"},
                "max_len": {"type": "integer"},
                "end_with": {"type": "array", "items": {"type": "string"}},
                "start_verbs": {"type": "array", "items": {"type": "string"}},
            },
        },
        "ui_short": {  # 短行 UI 交互词(≤12字独立短行含即删)
            "type": "object",
            "additionalProperties": {"type": "array", "items": {"type": "string"}},
        },
        # ── 多动作区块(R1, YAML v4): 转写内容保护 A-E ──
        "protect_teaching": {  # E: 教学短行保护(音标/翻译/单词卡/祈使句)
            "type": "object",
            "properties": {
                "teaching_words": {"type": "array", "items": {"type": "string"}},
                "min_word_count": {"type": "integer"},
            },
        },
        "compress_repeat": {  # A: 台词重复压缩参数
            "type": "object",
            "properties": {
                "min_count": {"type": "integer"},
            },
        },
        "watermark": {  # B: 界面水印参数
            "type": "object",
            "properties": {
                "min_count": {"type": "integer"},
            },
        },
        "garbled": {  # C: OCR乱码参数
            "type": "object",
            "properties": {
                "min_len": {"type": "integer"},
            },
        },
    },
}


# 模块加载: 读取规则(配置优先, 内置降级)
_RULES = _load_rules()
_NOISE_SUBSTR = (sum((list(v) for v in _RULES.get("noise_substr", {}).values()), [])
                 if _RULES else _DEFAULT_SUBSTR)
_NOISE_RE = [re.compile(p) for p in _RULES.get("noise_regex", [])] if _RULES \
    else [re.compile(p) for p in _DEFAULT_REGEX]
_KEEP_HEADINGS = set(_RULES.get("keep_headings", [])) if _RULES else _DEFAULT_HEADINGS
_LANMU_BUTTONS = set(_RULES.get("lanmu_buttons", [])) if _RULES else _DEFAULT_LANMU
_UI_SHORT = sum((list(v) for v in _RULES.get("ui_short", {}).values()), []) if _RULES else []
_QUESTION_TITLE = _RULES.get("question_title", {}) if _RULES else {}
_QUESTION_END = _QUESTION_TITLE.get("end_with", ["？", "?"])
_QUESTION_VERBS = _QUESTION_TITLE.get("start_verbs",
                                      ["如何", "怎么", "怎样", "为什么", "哪些", "什么", "有啥"])
_QUESTION_MIN = _QUESTION_TITLE.get("min_len", 3)
_QUESTION_MAX = _QUESTION_TITLE.get("max_len", 30)

# 多动作区块参数(R1): 教学词表/压缩阈值/水印阈值/乱码长度
_TEACHING_WORDS = set(_RULES.get("protect_teaching", {}).get("teaching_words", [])) if _RULES else set()
_COMPRESS_MIN = _RULES.get("compress_repeat", {}).get("min_count", 3) if _RULES else 3
_WATERMARK_MIN = _RULES.get("watermark", {}).get("min_count", 30) if _RULES else 30
_GARBLED_MIN = _RULES.get("garbled", {}).get("min_len", 2) if _RULES else 2


def is_html_like(raw: str) -> bool:
    """是否含真 HTML 标签(区分纯文本快照)。

    `>>点这里<<` 中的 < 后紧跟 < 不是字母, 不会误判为 HTML。
    """
    return _HTML_TAG.search(raw) is not None


def extract_article(raw: str, trafilatura_py: str = "") -> tuple[str, str]:
    """trafilatura 网关(Stage0): HTML 输入 → 提取正文去导航。

    - 纯文本快照 → 原样返回(engine='plain'), trafilatura 只服务真 HTML。
    - 真 HTML → venv trafilatura extract(favor_precision=True) 提取正文(engine='trafilatura')。
    - 未配置/调用失败/提取为空 → 降级原样返回, 不阻断流水线。

    Returns:
        (text, engine)  engine ∈ {"plain", "trafilatura"}
    """
    if not is_html_like(raw):
        return raw, "plain"
    if not trafilatura_py or not os.path.exists(trafilatura_py):
        return raw, "plain"
    # 内联脚本经 stdin 传原文(UTF-8), 避免命令行引号/编码转义
    code = (
        "import sys, trafilatura;"
        "raw=sys.stdin.buffer.read().decode('utf-8','replace');"
        "r=trafilatura.extract(raw, include_comments=False, include_tables=False,"
        " include_formatting=False, favor_precision=True);"
        "print(r or '')"
    )
    try:
        proc = subprocess.run(
            [trafilatura_py, "-c", code], input=raw.encode("utf-8"),
            capture_output=True, timeout=60)
    except (subprocess.SubprocessError, OSError):
        return raw, "plain"
    out = proc.stdout.decode("utf-8", "replace").strip()
    return (out or raw), "trafilatura"


def normalize_stage1(text: str) -> str:
    """Stage1 clean-text 归一化(#88): 去 URL + HTML实体还原 + 零宽/空白规整。

    - 不启用 fix_unicode(会把中文全角标点折叠成半角, 破坏中文排版)。
    - to_ascii=False 保留中文; no_urls 去带协议 URL(无协议广告域名由 #92 自研规则补)。
    - clean-text 缺失时降级为 html.unescape + URL 正则, 不阻断流水线。
    """
    t = html.unescape(text)  # HTML 实体还原(如 &amp; &nbsp;)
    try:
        from cleantext import clean
        t = clean(t, fix_unicode=False, to_ascii=False, lower=False,
                  no_line_breaks=False, no_urls=True, replace_with_url="",
                  no_emails=False, no_phone_numbers=False, no_numbers=False,
                  no_digits=False, no_punct=False)
    except ImportError:
        t = _URL.sub("", t)
    # 标点乱码规范化(ASR/OCR 文本): ,, → , / .. → . / ?? → ? / ,. → .
    for rx, repl in _PUNCT_PAIRS:
        t = rx.sub(repl, t)
    t = _ZERO_WIDTH.sub("", t)
    t = _SPACES.sub(" ", t)
    t = _BLANK_LINES.sub("\n\n", t)
    return t.strip()


# 轻量英文词表(用于教学英文 vs 乱码 词典校验, 覆盖常见教学词/短行)
# 子集: 常见单词卡/祈使句/教学短行常见词
_EN_WORDS = {
    "a","an","the","is","are","was","were","do","does","did","be","been","being","have","has","had",
    "can","could","will","would","shall","should","may","might","must","not","and","but","or","so","for",
    "okay","listen","up","down","look","say","said","see","watch","hear","learn","study","read","write",
    "good","bad","new","old","big","small","one","two","three","day","night","baby","family","home",
    "like","want","need","know","think","get","got","go","going","come","head","plan","mountain",
    "stellar","accommodation","reputation","rustic","cabin","laundry","dishwashing","milk","water","food",
    "this","that","these","those","there","here","where","what","when","why","who","how","now","then",
    "everybody","everyone","somebody","someone","duncan","dad","mom","mother","father","vacation",
    "great","deal","summer","school","teacher","class","lesson","word","phrase","sentence","grammar",
    "hell","talk","speak","english","chinese","subtitles","caption","listenup","goodbye","hello","hi",
    "oh","no","yes","yeah","yay","ye","me","you","he","she","it","we","they","them","his","her","my","your",
    "谢谢","我们","你们","大家","一个人","一群人","认真","注意","时候","就是","表示","用于","一个","如果","所以","因为","但是","可以","能够","应该","需要","然后","还有","很好","非常","真的","也许","总是","更多","计划","出去","告诉","觉得","看到","知道","喜欢","想要","觉得","以为","起来","下去",
}

def _looks_like_real_word(line: str) -> bool:
    """词典校验: 行内是否含真实英文单词(内置词表 + YAML 教学词表)。区分教学英文 vs OCR乱码。"""
    l = line.lower().strip(" .,!?;:()[]{}'\"-")
    words = set(_EN_WORDS) | _TEACHING_WORDS
    if l in words:
        return True
    for w in re.split(r"[^a-z']+", l):
        if w in words and len(w) >= 2:
            return True
    return False


def _near_dict_word(line: str) -> bool:
    """模糊词典校验: 乱码候选是否接近某真实词(OCR变体)。

    真实单词的OCR变体(如 Dishuching→Dishwashing, Laundry→Laundry) 距词表近, 判教学保留;
    无意义串(dnrduork/Chury) 距任何词都远, 判乱码。
    注意: 短词(≤4字母)阈值更严——MILR→milk 距离近但长度太短易误判。
    """
    from difflib import get_close_matches
    l = line.lower().strip(" .,!?;:()[]{}'\"-")
    if not l or len(l) < 3:
        return False
    for w in re.split(r"[^a-z]+", l):
        if len(w) < 3:
            continue
        # 短词要求更高相似度(防 MILR→milk 误判); 长词允许 OCR 变形
        cutoff = 0.85 if len(w) <= 4 else 0.7
        if get_close_matches(w, _EN_WORDS, n=1, cutoff=cutoff):
            return True
    return False


def compress_repetition(lines: list[str], min_count: int = 3) -> list[str]:
    """台词重复压缩(A): 教学台词重复(视频反复播放)压缩为"原文…[出现N次]"，不删除。

    调研2共识(gnehs compactRepetitiveSubtitleText/SubtitleEdit/YaoFANGUK):
    - 台词重复=教学强调信号, 应保留但压缩省token
    - 界面水印重复由 watermark 规则删(不在此压缩)
    - 中文翻译行: 与英文台词配对, 单独计数不误并

    策略:
      1. 归一化指纹统计每行出现次数
      2. 对出现≥min_count 的"长句"行(教学台词/翻译): 保留首现 + 标注 [出现N次]
      3. 短行(单词卡/音标)已由教学保护保留, 不受影响
      4. 保留首次出现的完整行, 后续重复行替换为标记(或删除, 因为首现已有全文)

    Args:
        lines: 清洗后行列表。
        min_count: 触发压缩的重复次数阈值。
    Returns:
        压缩后行列表。
    """
    if len(lines) < min_count:
        return lines
    lines = [l if isinstance(l, str) else (str(l) if l is not None else "") for l in lines]
    from collections import Counter
    # 归一化指纹(小写+去标点空白, 中文保留)
    def _key(s: str) -> str:
        return re.sub(r"[^a-z0-9一-鿿]", "", s.lower())
    cnt = Counter(_key(l) for l in lines if l.strip())
    compressed = []
    seen = set()
    for l in lines:
        if not l.strip():
            continue
        k = _key(l)
        n = cnt[k]
        if n >= min_count and k not in seen:
            # 首次出现: 保留全文 + 压缩标注
            compressed.append(f"{l} … [出现{n}次]")
            seen.add(k)
        elif n >= min_count:
            continue  # 重复行: 跳过(首现已有全文+标注)
        else:
            compressed.append(l)
    return compressed


def merge_broken_lines(lines: list[str]) -> list[str]:
    """续句合并(D): 被OCR拆断的台词拼回完整句。

    调研2共识(adrianmusante mergeShortLines/SubtitleEdit MergeShortLinesUtils):
    - 触发: 上一行不以句末标点(.?!。！？…)结尾 + 下一行以小写/连词(and,but,so,of)/&/,/开头
    - 教学行不参与合并(音标/翻译/单词卡独立保留)
    - 只合并一次(合并后不再递归, 避免吞掉独立短句)

    Args:
        lines: 清洗后保留的行列表。
    Returns:
        合并后的行列表。
    """
    if len(lines) < 2:
        return lines
    _SENT_END = (".", "!", "?", "。", "！", "？", "…", ":", "：")
    _CONTINUE_PREFIX = ("and", "but", "so", "of", "or", "the", "a", "an", "that", "this",
                        "because", "if", "when", "while", "as", "for", "to", "with", "at", "in", "on")
    merged = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        if nxt is not None:
            # 上一行不以句末标点结尾(允许末尾空格/逗号/省略号)
            cur_stripped = cur.rstrip()
            no_end = not cur_stripped.endswith(_SENT_END)
            # 下一行以小写开头 或 连词开头 或 &/, 开头
            nxt_stripped = nxt.lstrip()
            starts_lower = nxt_stripped[:1].islower() if nxt_stripped else False
            starts_cont = any(nxt_stripped.startswith(p) for p in _CONTINUE_PREFIX)
            starts_sym = nxt_stripped.startswith(("&", ",", "-"))
            # 教学行保护: 下一行若是明显教学结构(音标/中文翻译)则不合并;
            #   但"单词类短行"(Listen/up./there's) 可能是续行, 优先合并
            nxt_is_strong_teaching = _is_teaching_line(nxt) and re.search(r"[一-鿿]|/[^/\n]+/|[ˈˌɒəθðŋʃʒ]", nxt)
            cur_is_strong_teaching = _is_teaching_line(cur) and re.search(r"[一-鿿]|/[^/\n]+/|[ˈˌɒəθðŋʃʒ]", cur)
            if no_end and (starts_lower or starts_cont or starts_sym) and not cur_is_strong_teaching and not nxt_is_strong_teaching:
                merged.append(cur + " " + nxt)
                i += 2
                continue
        merged.append(cur)
        i += 1
    return merged


def _is_garbled(line: str) -> bool:
    """OCR乱码检测(C): 无意义碎片(dnrduork/Chury) → 删。

    调研2共识(SubtitleEdit OcrFixEngine/hide3tu/balance-joe):
    - 乱码特征: 无元音字母 / 词典零命中 / 字符熵低(重复字母块)
    - 保护: 教学行(_is_teaching_line)已先豁免, 不会误删音标/翻译/单词卡
    - 保守: 宁漏删不误删(教学英文如 MILK/Dishuching 由教学保护保留)

    判定(任一命中即乱码):
      1. 纯字母行(≥2字符)且无元音(a e i o u) → 乱码(dnrduork 但含u? 实际含u/o)
         —— 改用"无 aeiou 任一"更严? 但 dnrduork 含 u o。故用"词典零命中+乱码结构"
      2. 词典零命中 + 长度≥3 + 非真词: 纯字母串不在词表 → 疑似乱码(dnrduork/Chury/MILR)
         —— 但教学 OCR 变体(Dishuching)也不在词表, 会被误删! 需用"上下文"区分
      3. 纯数字/纯符号行 → 乱码(916)
    """
    if not line or len(line) < 2:
        return False
    if re.search(r"[一-鿿]", line):
        return False
    # 纯数字/纯符号行(无字母无中文) → 乱码
    if not re.search(r"[A-Za-z]", line):
        return True  # 916 / /eue6,/
    # 纯字母串(无空格): 词典零命中 且 不接近任何真词 → 乱码
    #   Dishuching→近dishwashing(保), dnrduork→距任何词远(删)
    letters = re.findall(r"[A-Za-z]", line)
    has_space = " " in line
    if letters and not has_space:
        in_dict = _looks_like_real_word(line)
        near_dict = _near_dict_word(line)
        if not in_dict and not near_dict:
            return True
    return False


def _is_teaching_line(line: str) -> bool:
    """教学短行识别(E保护): 音标/中文翻译/单词卡/祈使句/教学英文 → 永不删。

    调研2共识: 短行≠噪音, 音标/翻译/单词卡是教学精华。任何删除规则(水印/乱码/高频)
    都必须先豁免教学行, 再判断是否为噪音。

    判定特征(命中任一条即保护):
      1. 音标行: 含 IPA 音标字符(ˈ ˌ ɒ ə θ ð ŋ ʃ ʒ 或 /.../ 包裹)
      2. 中文翻译行: 含 CJK 字符(可能夹英文, 如"大家听好了（用于多人）")
      3. 教学英文: 含完整英文单词且 ≤3 词(单词卡/祈使句, 如 "Listen up."/"MILK")
         —— 单词由字母构成, OCR乱码(dnrduork)常无元音/含重复字母, 由 T5 乱码检测区分
      4. 音标结构: 以 / 开头或含 /.../ 音标标记
    """
    if not line:
        return False
    # ① 音标字符
    if re.search(r"[ˈˌɒəθðŋʃʒ]", line):
        return True
    # ② /.../ 音标包裹
    if re.search(r"/[^/\n]+/", line):
        return True
    # ③ 中文翻译行(含CJK即保护 —— 中文讲解是教学精华, 界面水印是纯中文短词由黑名单删)
    if re.search(r"[一-鿿]", line):
        return True
    # ④ 教学英文: 纯英文短行(≤3词) 且 词典命中 或 接近真词(OCR变体如 Dishuching→Dishwashing)
    #     —— 有元音但不接近任何词的(dnrduork/Chury) 不判教学, 交给乱码检测删
    words = [w for w in re.split(r"\s+", line.strip()) if w]
    if 1 <= len(words) <= 3 and all(re.fullmatch(r"[A-Za-z]+[.,]?", w) for w in words):
        if _looks_like_real_word(line) or _near_dict_word(line):
            return True
    return False


def _is_heading_line(line: str) -> bool:
    """教学标题识别: 序号式标题(第一章/第1讲/1.2) → 永不判水印。

    无 # 标记的纯文本章节标题("第一章 绪论")独立成行且短(≤12字), 会被
    _is_watermark_candidate 误判为答主水印/孤立短行而误删(教学 md 常见形态)。
    答主昵称不带"第X[章讲节]"序号、也不是教学标题词, 识别它们不会误伤。
    keep_headings 白名单词由调用处"not in _KEEP_HEADINGS"已豁免, 此处只管序号式。
    """
    s = line.strip()
    if not s:
        return False
    # ① 序号式标题: 以"第X[章讲节篇课部分]"开头(可带后续标题文字, 如"第一章 绪论"/"第1讲 变量")
    if re.match(r"^第[一二三四五六七八九十百0-9]+\s*[章讲节篇课部分]", s):
        return True
    # ② 数字小节: 1.2 / 1.2.3(含"."符号, 原 _is_watermark_candidate 已排除, 兜底防改判)
    if re.match(r"^\d+(\.\d+)+$", s):
        return True
    return False


def _is_watermark_candidate(line: str) -> bool:
    """水印(答主昵称)候选: 独立短行(≤12字符) + 无标点/符号 + 非纯数字行。

    答主防爬插眼形如: 正文句子\n徐火山\n正文句子\n
    注: 教学短行(音标/翻译/单词卡)由 _is_teaching_line 保护, 不判为水印;
        教学标题(第一章/第1讲/白名单词)由 _is_heading_line/keep_headings 保护, 不判为水印。
    """
    if _is_heading_line(line):
        return False
    if not line or len(line) > 12:
        return False
    # 含非中文/字母/数字/空格字符(标点/&/括号等) → 排除
    if re.search(r"[^\u4e00-\u9fff a-zA-Z0-9]", line):
        return False
    # 纯数字 / 浏览量"X万"行 → 排除
    if re.fullmatch(r"[\d 万.]+", line):
        return False
    return bool(re.search(r"[\u4e00-\u9fff]|[a-zA-Z]", line))


def _is_noise_line(line: str) -> bool:
    """固定噪音行(UI残留/AI标记/统计/推荐区/热搜/ICP/导航/赞同评论日期/阅读全文)。"""
    if any(s in line for s in _NOISE_SUBSTR):
        return True
    return any(rx.search(line) for rx in _NOISE_RE)


def _is_question_title(line: str) -> bool:
    """推荐问题标题: 独立短行以问号结尾, 或疑问词开头的短行(规则来自 YAML question_title)。

    知乎推荐区/答案列表的问题(如"如何写一份让 HR 眼前一亮的简历？"、"如何写一份成功的简历")，
    正文段落不会以"？"独立成短行, 也不以疑问词开独立短行。
    """
    l = line.strip()
    if re.match(rf"^.{{{_QUESTION_MIN},{_QUESTION_MAX}}}"
                rf"[{re.escape(''.join(_QUESTION_END))}]$", l):
        return True
    verbs = "|".join(re.escape(v) for v in _QUESTION_VERBS)
    if re.match(rf"^({verbs})[^\s。，]{{0,12}}$", l):
        return True
    return False


def remove_chinese_noise(text: str, noise_substr: list[str] | None = None) -> str:
    """Stage3 自研中文规则(#92): 去答主水印 + 固定噪音 + 尾部推荐区截断。

    Args:
        text: 待清洗文本。
        noise_substr: 指定形态的噪音词(common+对应分组); None 用全部分组。

    规则(基于 40 篇知乎快照的真实噪音分布设计, 保守优先防误删正文):
      1. 顶部导航行(综合用户论文AI...) → 删本行 + 紧随的搜索词行
      2. 固定噪音行(黑名单子串 + 正则: 评论数/时间/热搜/ICP/AI标记等) → 删
      3. 推荐栏目按钮(独立短行精确匹配: 量化成果/STAR法则等) → 删
      4. 答主水印: 出现 ≥2 次的"无标点短行"候选 → 删
         (正文小节标题在白名单内保护; "量化成果/STAR法则"等栏目词作句子时不受影响)
      5. "大家都在搜"之后的热搜/备案 → 截断
      6. 广告行(下载同款模板/AI诊断工具/简历神器) → 删

    零宽字符/URL 归 Stage1(clean-text); PII 归 Stage5(presidio)。
    低频(1次)水印保守保留, 避免误删正文短句。
    """
    noise = noise_substr if noise_substr is not None else _NOISE_SUBSTR

    def _is_noise(line: str) -> bool:
        if any(s in line for s in noise):
            return True
        return any(rx.search(line) for rx in _NOISE_RE)

    lines = [l.strip() for l in text.split("\n")]
    freq = Counter(l for l in lines if _is_watermark_candidate(l))
    # 阈值 2: 出现≥2次的"无标点短行"候选判为水印(正文小节标题由白名单保护)
    watermarks = {l for l, n in freq.items() if n >= 2}
    # 注: 原"整行重复≥3次删"(high_freq)已移除——它误删教学台词/中文翻译(视频反复播放的
    #   台词是教学强调信号, 应压缩保留而非删除, 见调研2补丁重构计划 R1)。台词压缩由
    #   compress_repeat 处理(T8), 此处不再全局计数删除。
    kept = []
    skip_next = False
    in_code = False
    for l in lines:
        if not l:
            continue
        if l.startswith("```"):  # MD 代码块围栏(E10): 切换模式, 围栏保留
            in_code = not in_code
            kept.append(l)
            continue
        if in_code:  # 代码块内容: 不判断噪音/水印, 原样保留
            kept.append(l)
            continue
        if "综合用户论文AI" in l:  # 顶部导航 → 删本行 + 下一行(搜索词)
            skip_next = True
            continue
        if skip_next:
            skip_next = False
            continue
        if "大家都在搜" in l:  # 尾部推荐区/热搜/ICP → 截断, 之后全部丢弃
            break
        if _is_noise(l):  # 先删已知噪音/水印(noise_regex 含 ^坚持打卡/^片名/^知识点)
            continue
        if _is_teaching_line(l):  # E保护: 教学短行(音标/翻译/单词卡) 优先保留
            kept.append(l)
            continue
        if _is_garbled(l):  # C: OCR乱码(dnrduork/916) → 删
            continue
        if _is_question_title(l):  # 推荐问题标题(问号结尾/疑问词开头短行) → 删
            continue
        if len(l) <= 12 and any(k in l for k in _UI_SHORT):  # 短行 UI 碎片(点赞/收藏/关注) → 删
            continue
        if l in _LANMU_BUTTONS:  # 推荐栏目按钮(独立短行) → 删
            continue
        if l in watermarks and l not in _KEEP_HEADINGS:
            continue
        kept.append(l)
    # 第二遍: 孤立短行(答主水印) — 基于已保留行, 前后行都存在且都是长内容 → 删
    #   单行文本/文件首尾短行(前后缺失)不删; 正文小标题(白名单)与连续短行列表不受影响
    out = []
    in_code = False
    for i, l in enumerate(kept):
        if l.startswith("```"):  # 第二遍: 代码块围栏保护(E10)
            in_code = not in_code
            out.append(l)
            continue
        if in_code:
            out.append(l)
            continue
        prev = kept[i - 1] if i > 0 else None
        nxt = kept[i + 1] if i + 1 < len(kept) else None
        if (_is_watermark_candidate(l) and l not in _KEEP_HEADINGS
                and prev is not None and nxt is not None
                and not _is_watermark_candidate(prev) and not _is_watermark_candidate(nxt)):
            continue
        out.append(l)
    # 第三遍: 续句合并(D) — 被OCR拆断的台词拼回(教学行不参与)
    out = merge_broken_lines(out)
    # 第四遍: 台词压缩(A) — 教学重复台词压缩为[出现N次](水印已删, 此处只余教学重复)
    out = compress_repetition(out)
    return "\n".join(out).strip()


def analyze_snownlp(text: str) -> dict:
    """Stage2 snownlp 中文分析(#89): 分句 + 词性标注, 供 #92 水印识别辅助。

    水印(答主昵称)识别不能只靠 snownlp——它对"野蛮生长永不彷徨"这类昵称
    会切成普通词序列而非人名; 需结合 #92 的"短行+无标点+句尾+重复"复合规则。
    本函数提供基础分析能力(分句/词性), 由 #92 自研规则消费。

    Returns:
        {"available": bool, "sentences": list[str], "tags": list[tuple[str,str]]}
    """
    try:
        from snownlp import SnowNLP
    except ImportError:
        return {"available": False}
    try:
        s = SnowNLP(text)
        return {"available": True, "sentences": s.sentences, "tags": list(s.tags)}
    except Exception:  # noqa: BLE001
        return {"available": False}


# 清洗结果结构体检 schema(Stage4, #90): 入知识库前必须合格
_CLEAN_SCHEMA = {
    "type": "object",
    "required": ["ok", "text", "engine", "stats"],
    "properties": {
        "ok": {"type": "boolean"},
        "text": {"type": "string"},
        "engine": {"enum": ["plain", "trafilatura"]},
        "stats": {
            "type": "object",
            "required": ["raw_len", "clean_len"],
            "properties": {
                "raw_len": {"type": "integer"},
                "clean_len": {"type": "integer"},
            },
        },
    },
}


def validate_schema(result: dict) -> tuple[bool, list[str]]:
    """Stage4 jsonschema 体检(#90): 校验清洗结果结构合格。

    未装 jsonschema 时跳过(返回 True), 不阻断流水线。

    Returns:
        (是否合格, 错误信息列表)
    """
    try:
        import jsonschema
    except ImportError:
        return True, []
    errors = sorted(
        jsonschema.Draft7Validator(_CLEAN_SCHEMA).iter_errors(result),
        key=lambda e: list(e.path))
    msgs = [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors]
    return (not errors), msgs


def anonymize_pii(text: str, presidio_py: str = "") -> dict:
    """Stage5 presidio 脱敏(#91): PII(手机号/邮箱/身份证) → ***。

    独立 venv(presidio, 路径经 .env 配置) subprocess 调用。
    自定义中国 PII 正则(手机号 1[3-9]\\d{9} / 18位身份证), score_threshold=0.6 滤掉
    US_BANK_NUMBER/URL 等低分误报。发布/导出前调用, 本地知识库不清洗 PII。

    Returns:
        {"ok": bool, "text": str, "count": int, "available": bool}
        available=False 表示未配置/调用失败(降级原文本)。
    """
    if not presidio_py or not os.path.exists(presidio_py):
        return {"ok": True, "text": text, "count": 0, "available": False}
    # 多行脚本避免单行 if/else 语法陷阱; 正则用 [0-9] 规避反斜杠转义
    code = """
import sys, json
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, PatternRecognizer, Pattern
from presidio_analyzer.predefined_recognizers import EmailRecognizer
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
text = sys.stdin.buffer.read().decode('utf-8', 'replace')
cn_phone = PatternRecognizer(supported_entity='PHONE_NUMBER', patterns=[Pattern(name='cn_phone', regex=r'(?<![0-9])1[3-9][0-9]{9}(?![0-9])', score=0.8)])
cn_id = PatternRecognizer(supported_entity='CHINA_ID', patterns=[Pattern(name='cn_id', regex=r'[0-9]{17}[0-9Xx]', score=0.8)])
# 精简 registry: 只保留真 PII 识别(邮箱+中国手机号+身份证)。
# 排除默认 NER(SpacyRecognizer 对中文乱识别) 与 URL/DATE_TIME 等非 PII 误报
registry = RecognizerRegistry()
registry.add_recognizer(EmailRecognizer())
registry.add_recognizer(cn_phone)
registry.add_recognizer(cn_id)
analyzer = AnalyzerEngine(registry=registry)
results = analyzer.analyze(text=text, language='en', score_threshold=0.5)
if results:
    ops = {'DEFAULT': OperatorConfig('replace', {'new_value': '***'})}
    anon = AnonymizerEngine()
    out = anon.anonymize(text=text, analyzer_results=results, operators=ops)
    print(json.dumps({'text': out.text, 'count': len(results)}, ensure_ascii=False))
else:
    print(json.dumps({'text': text, 'count': 0}, ensure_ascii=False))
"""
    try:
        proc = subprocess.run(
            [presidio_py, "-c", code], input=text.encode("utf-8"),
            capture_output=True, timeout=90)
    except (subprocess.SubprocessError, OSError):
        return {"ok": True, "text": text, "count": 0, "available": False}
    try:
        import json as _json
        out = _json.loads(proc.stdout.decode("utf-8", "replace").strip())
        return {"ok": True, "text": out.get("text", text), "count": out.get("count", 0),
                "available": True}
    except Exception:  # noqa: BLE001
        return {"ok": True, "text": text, "count": 0, "available": False}


def clean_text(raw: str, trafilatura_py: str = "", anonymize: bool = False,
               form: str = "") -> dict:
    """清洗主入口(Stage0/1/3/4/5; Stage2 分析辅助供 #92 使用)。

    Args:
        raw: 爬取到的原始文本(HTML 或纯文本快照)。
        trafilatura_py: trafilatura venv python 路径; 空则自动读配置。
        anonymize: 是否执行 presidio PII 脱敏(默认 False — 本地知识库保留 PII,
                   发布/导出前再置 True)。
        form: 数据形态(如 "video_ocr"/"video_asr"/"zhihu"), 指定时只用 common+对应
              分组规则; 空用全部分组。

    Returns:
        {"ok","text","engine","stats","valid","schema_errors"}
    """
    if raw is None:
        raw = ""
    elif not isinstance(raw, str):
        raw = str(raw)
    if not trafilatura_py:
        trafilatura_py = os.environ.get("TRAFILATURA_PY", "")
    stats = {"raw_len": len(raw)}
    text, engine = extract_article(raw, trafilatura_py)
    text = normalize_stage1(text)
    if form and _RULES:
        # 按形态选规则分组(common + 指定分组)
        groups = _RULES.get("noise_substr", {})
        form_substr = list(groups.get("common", [])) + list(groups.get(form, []))
        # R2: 视频转写先句子归一化(合并OCR拆行), 再跑规则 —— 修复"拆行台词匹配不上"根因
        if form.startswith("video"):
            try:
                from cleaner.sentence_normalize import normalize_sentences
                text = normalize_sentences(text)
            except ImportError:
                pass  # sentencex 未装则跳过, 不阻断
        text = remove_chinese_noise(text, noise_substr=form_substr)
    else:
        text = remove_chinese_noise(text)
    if anonymize:
        pii = anonymize_pii(text, os.environ.get("PRESIDIO_PY", ""))
        text = pii["text"]
        stats["pii_removed"] = pii["count"]
    stats["clean_len"] = len(text)
    result = {"ok": bool(text.strip()), "text": text, "engine": engine, "stats": stats}
    result["valid"], result["schema_errors"] = validate_schema(result)
    return result


# ─────────────────────── CLI ───────────────────────

def check_content_integrity(raw: str, cleaned: str) -> list[str]:
    """清洗质量验证(I): 检查正文是否被误删(保留率/中文内容/空壳)。

    与 scan_residual(查噪音残留)互补: 残留检测查"该删的没删",
    本检查查"该保留的被删了"(防误删正文)。
    Returns: 问题列表(空 = 正文完整)。
    """
    issues = []
    if not cleaned.strip():
        issues.append("清洗结果为空(可能正文被误删)")
    elif len(cleaned) < len(raw) * 0.15:
        issues.append(f"保留率过低 {len(cleaned) / max(1, len(raw)):.0%} (<15%, 疑似误删正文)")
    content_chars = len(re.sub(r"\s", "", cleaned))
    if content_chars < 30:
        issues.append("清洗后有效内容过少, 疑似误删正文")
    return issues


def scan_residual(text: str) -> list[str]:
    """残留噪音检测: 清洗后文本中仍命中任一"应删规则"的行(漏网噪音)。

    覆盖清洗会删的全部类型(与 remove_chinese_noise 对齐):
      固定词 / 正则 / 推荐问题标题 / 栏目按钮 / 高频水印 / 孤立答主名
    若返回非空 → 规则漏了变体, 需补进 YAML。
    Returns: 残留行列表(空 = 干净)。
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    hits = []
    for l in lines:
        if any(s in l for s in _NOISE_SUBSTR):
            matched = next(s for s in _NOISE_SUBSTR if s in l)
            hits.append(f"固定词[{matched}]: {l[:60]}")
        elif any(rx.search(l) for rx in _NOISE_RE):
            hits.append(f"正则: {l[:60]}")
        elif _is_question_title(l):
            hits.append(f"推荐问题标题: {l[:60]}")
        elif l in _LANMU_BUTTONS:
            hits.append(f"栏目按钮: {l}")
    # 高频水印(≥2次候选, 非白名单)
    freq = Counter(l for l in lines if _is_watermark_candidate(l))
    watermarks = {l for l, n in freq.items() if n >= 2}
    for l in lines:
        if l in watermarks and l not in _KEEP_HEADINGS:
            hits.append(f"高频水印: {l}")
    # 孤立答主名(前后行都是长内容, 非白名单) — 排除已命中的噪音行防重复
    kept = [l for l in lines if l not in watermarks
            and not any(s in l for s in _NOISE_SUBSTR)
            and not any(rx.search(l) for rx in _NOISE_RE)
            and not _is_question_title(l) and l not in _LANMU_BUTTONS]
    for i, l in enumerate(kept):
        prev = kept[i - 1] if i > 0 else None
        nxt = kept[i + 1] if i + 1 < len(kept) else None
        if (_is_watermark_candidate(l) and l not in _KEEP_HEADINGS
                and prev is not None and nxt is not None
                and not _is_watermark_candidate(prev) and not _is_watermark_candidate(nxt)):
            hits.append(f"孤立答主名: {l}")
    # 去重(同一行可能命中多条)
    seen = set()
    uniq = []
    for h in hits:
        if h not in seen:
            seen.add(h)
            uniq.append(h)
    return uniq


def _setup_stdout():
    """控制台用系统编码(WriteConsoleW 自动处理中文), 管道用 UTF-8。"""
    try:
        if not sys.stdout.isatty():
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if not sys.stderr.isatty():
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


def _walk_files(root: str, suffix: str):
    """递归收集指定后缀文件。"""
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            if f.lower().endswith("." + suffix.lower()):
                yield os.path.join(dirpath, f)


def _preview(filepath: str, text: str, engine: str, limit: int = 300) -> str:
    """清洗结果预览(前 limit 字符)。"""
    raw = open(filepath, encoding="utf-8", errors="replace").read()
    lines = [
        f"文件: {filepath}",
        f"引擎: {engine} | 原始 {len(raw)} → 清洗 {len(text)} 字符",
        "─" * 50,
        "【清洗前】",
        re.sub(r"\s+", " ", raw)[:limit],
        "",
        "【清洗后】",
        re.sub(r"\s+", " ", text)[:limit],
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="文本清洗(text-cleaning-engine)")
    parser.add_argument("--file", help="清洗单个文件")
    parser.add_argument("--dir", help="批量清洗目录(递归)")
    parser.add_argument("--suffix", default="html", help="批量时的文件后缀(默认 html)")
    parser.add_argument("--preview", nargs="?", const=True, default=False, metavar="FILE",
                        help="预览清洗前后对比(不写文件); 可带 FILE 路径")
    args = parser.parse_args()

    trafilatura_py = os.environ.get("TRAFILATURA_PY", "")

    files = []
    if isinstance(args.preview, str):
        files = [args.preview]
    elif args.file:
        files = [args.file]
    elif args.dir:
        files = list(_walk_files(args.dir, args.suffix))
        print(f"批量扫描 {args.dir}: 找到 {len(files)} 个 .{args.suffix} 文件")

    if not files:
        parser.print_help()
        sys.exit(1)

    preview = bool(args.preview)
    engine_cnt = {"trafilatura": 0, "plain": 0}
    ok_cnt = 0
    valid_cnt = 0
    ratios = []
    for fp in files:
        if not os.path.isfile(fp):
            print(f"⚠️ 跳过: 文件不存在或不是文件: {fp}")
            continue
        raw = open(fp, encoding="utf-8", errors="replace").read()
        res = clean_text(raw, trafilatura_py)
        if preview:
            print(_preview(fp, res["text"], res["engine"]))
            print()
        else:
            engine_cnt[res["engine"]] += 1
            ok_cnt += 1 if res["ok"] else 0
            valid_cnt += 1 if res.get("valid") else 0
            if res["stats"]["raw_len"]:
                ratios.append(res["stats"]["clean_len"] / res["stats"]["raw_len"])

    if not preview:
        avg_ratio = sum(ratios) / len(ratios) if ratios else 1.0
        print("─" * 50)
        print(f"✅ 完成: {len(files)} 个文件 | OK {ok_cnt} | 体检合格 {valid_cnt}")
        print(f"  引擎: trafilatura {engine_cnt['trafilatura']} / plain {engine_cnt['plain']}")
        print(f"  平均保留比例: {avg_ratio:.1%} (越小=去噪越多)")


_setup_stdout()


if __name__ == "__main__":
    main()
