# OCR/爬虫/NLP/字幕类仓库分析（30+ 份报告）

> **版本**: v1.0 · **状态**: 调研分析材料 · 2026-08-11
> **内容**: 4 份分类分析之一，供《补丁重构计划_v1.0》使用；完整版见该报告第五节。

---

## 一、可直接打补丁的

| 补丁 | 落点 | 来源 |
|------|------|------|
| typo 纠错表机制 | rules 新增 `typo_fix` 段 | YaoFANGUK typoMap、jiwer |
| 英文单词纠错器 | `cleaner/word_repair.py` | YaoFANGUK reformat.py |
| 标点/空格归一化正则集 | rules 追加 | YaoFANGUK |
| 连续+跨区两层重复清洗器 | `cleaner/repetition_dedup.py` | WhisperJAV、YaoFANGUK、gnehs |
| 词级纠错表 | rules 加 `lexicon`/`ocr_error_map` | Aegisub、SubtitleEdit、obgnail、WhisperJAV |
| 多边界标点切分函数 | cleaning.py 分句逻辑 | spaCy Sentencizer、SubtitleEdit |
| 纯符号/纯标点残渣行丢弃 | rules 新增 | WhisperJAV、SubtitleEdit |
| `exceptions` 保护机制 | rules 加 `protect_patterns` | jfilter/clean-text |
| SRT/带时间戳输入解析 | `cleaner/asr_parser.py` + `formatters.py` | AsrTools、youtube-transcript-api |
| LLM 纠错 agent_loop（可选） | `cleaner/llm_correction.py` | VideoCaptioner、marker、docetl |

## 二、可融入方法

文块流保结构架构（Umi-OCR TBPU，问题1主解）、"段=原子"清洗纪律（VideoCaptioner/Aegisub/gnehs/OCRFlux）、合并判定/执行分离（OCRFlux）、覆盖式去重（OCRFlux/obgnail）、可审计清洗（WhisperJAV）、检查点续跑+指纹失效（gnehs）、n-gram 指纹去重范式（balance-joe/DeepSeek-OCR）、模糊对齐容忍词级错字（langextract LCS）、置信度门控信号（ddddocr/surya/PaddleOCR）、校验+失败重试（docetl/VideoCaptioner/zerox）

## 三、可作架构参考

Umi-OCR TBPU 算法（MIT）、SubtitleEdit Fix Common Errors 规则库（50+条）、OCRFlux 元素编号化+合并判定、spaCy 容错公式、jiwer 对齐工具、crawlee html_to_text、buxuku Ollama 配方、FunASR abbr_dispose（MIT）

## 四、我们项目没有的优点

置信度贯穿全链路、可审计改动台账、合并判定/执行分离、增量续跑、LLM 兜底、领域白名单、输出 Formatter 多态

## 五、我们项目已有的缺点

先拼长段再清洗（8+仓库共同判定"根本性错误方向"）、去重粒度只在文件级、rules 无 video_asr 分组、无词级纠错阶段、无置信度信号、clean-text 全局 fix_unicode=False、校验层无修复重试

## 六、该避免的错误

为 2-3 思路引 GPU/VLM 重栈（DeepSeek-OCR/PaddleOCR/marker/MinerU/OCRFlux）、GPL 传染（VideoCaptioner/AsrTools）、死水/无协议仓库（fastPunct/zerox/AlvinIsonomia）、破坏性归一化（texthero）、非商用模型协议（HanLP CC-BY-NC）、去重误删教学强调内容、LLM 纠错全量无成本控制

## 七、可借鉴技术栈

`datasketch`/自写 MinHash、`rapidfuzz`、`symspellpy`/`hunspell`、`wordsegment`、`json-repair`、`difflib`（零依赖）、`litellm`/现有 GLM 桥接、Ollama 本地通道

## 八、冲突需重构

clean_text 字符串签名→段列表签名（冲突最大）、_dedup_check 文件级→段级、rules 需新增 video_asr 分组+多规则段、clean-text 参数按 form 分叉、校验层→校验+修复重试、输出层 Formatter 基类

## 九、关键注意（补丁前提）

**问题3 的 Umi-OCR 几何算法依赖帧 OCR 的 box 坐标**——需确认 media-to-notes 输出是否保留包围盒/置信度。若不保留，问题3 降级走"上下文语义合并"路线（OCRFlux 元素合并判定，纯文本侧，最有落地价值）。
