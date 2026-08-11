# ASR/语音转写类仓库分析（26 份报告）

> **版本**: v1.0 · **状态**: 调研分析材料 · 2026-08-11
> **内容**: 4 份分类分析之一，供《补丁重构计划_v1.0》使用；完整版见该报告第五节。

---

## 一、全局核心结论

问题 1/4 的根因在 ASR 输出格式（取错字段 `text` 而非 `segments`），问题 2/3 需要"时间戳 + 词级置信度"作判据。我们 cleaner 最缺的不是更多正则，而是 **"片段列表数据模型 + 置信度字段消费 + 段级近重复去重"** 三层能力。

## 二、可直接打补丁的

### 问题1 结构化丢失
- **新增 `cleaner/asr_parser.py`**：把 ASR JSON 反解成 `[(text, start_ms, end_ms)]` 句段列表，支持 json/srt/vtt。依据：AsrTools §8-1、wscribe §8-①
- **改 `clean_text()`**：新增 `clean_text_segments(raw_json, form="video_asr")`，逐段过 Stage1~5，按段 `\n` 输出。依据：whisperX §8-1、whisper.cpp、coqui-STT §8-1
- **`clean_batch.py` 增加输入类型分支**：.json 与 .txt 走不同入口。依据：FunASR §8-1

### 问题4 词级错误
- `rules/cleaning_rules.yaml` 新增：typo_map 正则表（YaoFANGUK）、词内空格合并 `\b([a-z])\s([a-z]{2,})\b`（WhisperJAV/coqui-STT）、单字母碎片合并（FunASR abbr_dispose）、`\b` 整词匹配（jiwer）
- 新增 `cleaner/word_repair.py`：wordsegment 粘连词切分（YaoFANGUK reformat.py）

### 问题2 段落重复
- 新增 `cleaner/repetition_dedup.py`：WhisperJAV 三层（规则/子串/截断）+ 第四层跨段近重复
- `cleaner/dedup.py`：字符5-gram → MinHash → 阈值0.85+ → 回原文 difflib 复检（ChenghaoMou）
- rules 新增 `video_replay` 分组：相同文本 + 时间戳不重叠 = 重播（whisperX）

### 问题3 碎片判别
- 纯符号/无实质字符行丢弃（WhisperJAV `_HAS_LINGUISTIC_CONTENT`）、短行+低置信度标记

## 三、可融入方法

片段列表数据模型（AsrTools/VideoCaptioner）、时间戳感知分句（vosk gap>0.4s/FunASR VAD）、置信度驱动校验（<0.6 → low_conf）、LLM 纠错循环+anchored 回显（VideoCaptioner/SmartSub）、可审计清洗器（WhisperJAV modifications）、Map-Reduce 长文本（AudioNotes）、NFKC 前置（YaoFANGUK）、hotwords 术语表（openai whisper/sherpa）

## 四、我们项目没有的优点

段/词两级结构化载体、词级置信度字段、重复/幻觉专项清洗器、可审计改动台账、LLM 纠错 stage、按语言配置归一化表、热词偏置、模糊近重复去重

## 五、我们项目已有的缺点

取错字段（拼 text 而非 segments）、整段处理而非逐段映射、重复检测粒度太粗、无词级错误候选机制、去重规则不看时间、碎片判别纯启发式

## 六、该避免的错误

AGPL 传染（whisper-timestamped）、GPL 不直接复制（VideoCaptioner/AsrTools/transcriptionstream）、无协议+缺权重（AlvinIsonomia）、模型权重入库（whisper-flow）、WER 归一化当清洗（openai whisper）、为单点引重依赖（semhash）、重复循环幻觉（condition_on_previous_text）、替换不设词边界、纠错过度伤原文

## 七、可借鉴技术栈

`rapidfuzz`（词级对齐）、`wordsegment`（粘连切分）、`datasketch`（MinHash）、`regex`（Unicode 属性）、`json-repair`+`diskcache`（LLM 层）。**不引入** torch/GPU 系。

## 八、冲突需重构

whisperX/faster-whisper 等转写引擎（只借 JSON 契约）、whisper-timestamped（AGPL 换 BSD）、VideoCaptioner 等（GPL 重写实现）、semhash（stdlib MinHash）、ctc-forced-aligner（CC-BY-NC 非商用）

## 九、落地优先级

P0 问题1（asr_parser）→ P1 问题4规则层 + 问题2 → P2 问题3 → P3 LLM/换引擎
