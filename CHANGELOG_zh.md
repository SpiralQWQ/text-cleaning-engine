# 变更日志
所有对 text-cleaning-engine 的重大变更记录于此，遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。版本遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.5.0] — 2026-08-11 · 转写内容保护（A–E 五类问题修复）

**新增：教学 vs 噪音分类（核心）**
- 教学白名单保护（E）：`_is_teaching_line` 识别音标/中文翻译/单词卡/教学英文（词表 + 模糊匹配），放所有删除前
- 乱码检测（C）：`_is_garbled` 词典零命中 + 无元音 + 字符熵，教学行豁免，默认保守
- 续句合并（D）：`merge_broken_lines` 无终止标点 + 下行小写 + 时间相邻 → 拼接，教学行不参与
- 台词压缩（A）：`compress_repetition` 教学重复台词压缩为 `原文…[出现N次]`（不删除，保留教学强调信号）

**修复：A 问题元凶**
- 移除 `cleaning.py` 的"整行重复≥3次删"（high_freq）——它把教学台词/中文翻译（视频反复播放）当水印误删；改为压缩保留

**规则升级（R1，YAML v3→v4）**
- 规则引擎从"布尔删"升级为"多动作"：`protect_teaching` / `compress_repeat` / `watermark` / `garbled` 四个可配置区块，参数外置

**句粒度前置（R2）**
- 新增 `cleaner/sentence_normalize.py` + `sentencex` 依赖：视频转写先句子归一化（合并 OCR 拆行台词），帧标记/OCR 文本块独立保护，修复"拆行台词匹配不上重复"根因

**工程加固（R3/R4）**
- `clean_batch.py` 空输出回退：保留率 <30% 判定误删 → 回退原文（防删 70%+ 教学）
- 审计字段：输出 meta 记录 `fallback` / `residual` / `content_issue` 可追溯
- 教学保留率门禁：`tests/teaching_benchmark.json`（30 条标注）+ `test_teaching_retention.py`（≥95%）

**验收**：T1–T12 逐个本体审核通过；真实 179 帧验证（台词压缩保留/乱码清除/拆行合并/教学保留/水印删除）；教学保留率 100%；原 14 项验收零回归；详见 `docs/验收报告_v3.0.md`

---

## [0.4.0] — 2026-08-11 · 接口适配（阶段0，对接转写产出）

**新增：ASR json 逐段清洗原型（保结构 `_clean.json`）**
- `cleaner/clean_asr_json.py`：ASR json（text + segments + sentences）逐段/逐句清洗，**保 json 结构**输出 `_clean.json`（原 json 保留溯源）
- 遵守接口红线：结构不拼平 / 中文讲解不删 / 时间戳·confidence·review 不改值 / srt 不清洗
- 段级去重：同文本 + 同时间戳 = 数据重复记录删后留前；同文本 + 不同时间戳 = 视频重播保留；中文段永不删
- 标点乱码规范化（`??`→`?`、`,,`→`,` 等）+ 纯标点段清空 + 空输入安全降级

**修复**
- F3 规则指纹路径 bug：`clean_batch.py` 引用 `config/`（不存在）→ `rules/`，恢复"规则变更触发增量重洗"机制

**规则扩展**
- `cleaning_rules.yaml` 新增 8 条 video 界面水印正则（`^坚持打卡`/`^片名：`/`^知识点\d+`/`^高手盲听`/`^初学看字幕`/`^纯英[文宇字]+幕$`/`^爱说英语的福安`/`^爱悦英烫`），行首锚定不误删 GLM 描述；修复短样本水印漏删

**文档**
- `docs/接口对接/`：接口对接报告 + 示例文件（格式契约/红线/接口）
- `docs/补丁重构计划_v1.1.md`：接入接口契约 + 开放问题定案
- `docs/验收报告_v2.0.md`：阶段0 接口适配验收

**验收**：T1–T7 逐个本体审核通过；接口红线 15/15 遵守；`_clean.json` 原型保结构输出；原 14 项验收测试全过（零回归）

---

## [0.3.0] — 2026-08-10 · 独立化

**结构独立**：
- 从爬虫项目 `_crawl` 内抽离为独立模块（与 `_crawl` 平级）
- 目录分层：`cleaner/`（引擎）`cli/`（命令）`rules/`（规则数据）`tests/`（验收）`docs/`（文档）`output/`（运行时输出）
- 解耦 `upstream.config` 依赖（工具路径读 `.env`、KB 参数化、输出到 `output/`）
- `.env.example` 工具路径模板（开源用）；`requirements.txt` 独立依赖

**验收**：`tests/test_acceptance.py` 14/14 通过；40 篇知乎全量清洗（残留 0、正文完整）输出到独立项目；`_crawl` 原文件已删（独立项目为唯一来源）

---

## [0.2.0] — 2026-08-10 · 视频转写形态 + 工程完善

**新增：视频转写清洗（V）**
- `video_ocr` 规则分组：帧标记（`=====`）/ OCR 标签（`[画面文字OCR]`）/ GLM 标签清除，每帧重复水印由"高频重复行"规则自动删（GLM 画面描述保留）
- `video_asr` 规则分组：ASR 标点乱码规范化（`,,`→`,`、`..`→`.`、`??`→`?`、`,.`→`.`，通用归一化）
- 引擎按形态选规则（`clean_text(form=...)`），video/json/zhihu 各自用对应分组
- MD 代码块保护（``` 围栏内内容不误删）
- 视频转写清洗方案文档（`视频转写清洗方案.md`）

**工程完善（E）**
- E1/E9 增量清洗 + 断点续洗：文件哈希 + 规则指纹，未变跳过、规则变重洗、中断恢复不丢
- E2 结构化索引（`_clean_results.json`）
- E3 清洗日志（`logs/clean_kb.log`）
- E4 并行批量清洗（`--parallel N`）
- E5 清洗后去重检查（`--dedup`，精确 md5 + 近似相似度）
- E6 质量断言扩展（英文视频不误报"中文少"）
- E7 规则版本管理（YAML version + `规则变更日志.md`）
- E8 清洗统计报告（`_clean_report.json` 历史累积）
- E11 worker 失败重试 3 次

**验收**：验收脚本扩展至 14 项全通过（含 video_ocr/video_asr/MD/规则校验）；40 篇知乎增量跳过、残留 0、正文完整、去重 0。

---

## [0.1.0] — 2026-08-10 · 工作流建立

**核心流水线**：Stage0-5（trafilatura 正文提取 / clean-text 归一化 / snownlp 中文分析 / jsonschema 体检 / presidio 脱敏）+ 自研中文规则（导航/水印/AI标记/评论/热搜/广告清除）

**规则数据化**：`cleaning_rules.yaml`（noise_substr/noise_regex/keep_headings/lanmu_buttons/question_title，common+zhihu 分组），jsonschema 校验防写错

**检测与质量**：`scan_residual` 残留检测器（6 类覆盖防漏删）+ `check_content_integrity` 正文完整性（防误删）

**数据分流**：`is_html_like` 纯文本/HTML 自适应；结构算法储备（trafilatura→jusText→dragnet 降级链）

**工程**：`clean_kb.py` 批量清洗 → `知识库_clean/`；40 篇知乎清洗入 RAG（bge-m3，准确率 100%）

**验收**：18 最小单元 task 逐个本体审核 + 验收报告

[0.5.0]: https://github.com/SpiralQWQ/text-cleaning-engine/releases/tag/v0.5.0
[0.4.0]: https://github.com/SpiralQWQ/text-cleaning-engine/releases/tag/v0.4.0
[0.3.0]: https://github.com/SpiralQWQ/text-cleaning-engine/releases/tag/v0.3.0
[0.2.0]: https://github.com/SpiralQWQ/text-cleaning-engine/releases/tag/v0.2.0
[0.1.0]: https://github.com/SpiralQWQ/text-cleaning-engine/releases/tag/v0.1.0
