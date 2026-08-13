<p align="center">
  <!-- 封面占位：可放 assets/cover.png（推荐 1280×640）并取消下行注释 -->
  <!-- <img src="assets/cover.png" alt="text-cleaning-engine" width="800"> -->
</p>

<h1 align="center">text-cleaning-engine</h1>

<p align="center">
  <b>规则驱动的「脏文本 → 干净、可直接入 RAG 的文本」清洗引擎。</b>
</p>

<p align="center">
  网页 HTML · 纯文本 · ASR 转写 JSON（保结构）· 视频 OCR/视觉转写
</p>

<p align="center">
  <a href="README.md"><kbd>English</kbd></a> · <kbd>简体中文</kbd>
</p>

<p align="center">
  <a href="https://github.com/SpiralQWQ/text-cleaning-engine/actions/workflows/ci.yml"><img src="https://github.com/SpiralQWQ/text-cleaning-engine/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/SpiralQWQ/text-cleaning-engine/releases"><img src="https://img.shields.io/badge/version-0.6.0-blue" alt="Version"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-3776AB" alt="Python 3.10+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL%203.0%20%7C%20Commercial-blue" alt="License"></a>
  <a href="#"><img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey" alt="Platform"></a>
  <img src="https://img.shields.io/github/stars/SpiralQWQ/text-cleaning-engine" alt="GitHub Stars">
  <img src="https://img.shields.io/github/last-commit/SpiralQWQ/text-cleaning-engine" alt="最近提交">
</p>

---

## 目录

- [为什么需要它](#为什么需要它)
- [功能特性](#功能特性)
- [安装](#安装)
- [配置](#配置)
- [快速上手](#快速上手)
- [用法](#用法)
- [架构](#架构)
- [转写内容保护（A-E）](#转写内容保护a-e)
- [集成联动](#集成联动)
- [运行测试](#运行测试)
- [文档](#文档)
- [贡献](#贡献)
- [常见问题](#常见问题)
- [支持](#支持)
- [许可证](#许可证)

---

## 为什么需要它

爬虫和转写管线产出的文本充满**噪音**：导航栏、水印、界面残留、重复字幕、OCR 乱码、拆行。手写清洗代码是维护噩梦——每来一个新站点或转写形态就要改一次代码。

`text-cleaning-engine` 把清洗规则**数据化**到 `cleaning_rules.yaml`：

- **加噪音不改代码**——改 YAML，重跑即可
- **多动作规则**，不止"删"：`delete` / `compress` / `protect` / `merge`
- **教学内容永不误删**——字幕、音标、中文翻译、单词卡白名单保护（见《转写内容保护 A-E》）
- **输出可验证**——保留率门禁、残留检测、误删超阈值自动回退原文

## 功能特性

| 输入形态 | 处理的噪音 | 输出 |
|----------|-----------|------|
| 网页 HTML | 导航、广告、评论、热搜、界面残留 | 干净正文 |
| 纯文本（如知乎快照） | 水印、提示文本、推荐区 | 干净文本 |
| ASR 转写 JSON（`text`+`segments`+`sentences`） | 标点乱码、重复记录、空段 | 保结构 `_clean.json` |
| 视频 OCR / 视觉转写 | 帧标记、OCR 标签、界面水印、拆行、重复字幕 | 干净转写（教学保留） |

核心能力：

- **多动作规则引擎**（YAML v4）：`delete` · `compress_repeat` · `protect_teaching` · `merge_broken_lines`
- **转写内容保护（A-E）**：字幕压缩（`原文…[出现N次]`）、水印删除、乱码检测、拆行合并、教学白名单
- **保结构 ASR 清洗**：`start_ms`/`end_ms`/`confidence`/`review` 不改值；中文讲解段永不删
- **保留率门禁**：教学保留率 ≥ 95%（基准测试）；误删 >70% 自动回退原文
- **残留检测 + 内容完整性检查**：每次批量清洗后自动扫描
- **PII 脱敏**：可选 presidio（手机/邮箱/身份证 → `***`）
- **增量 + 并行批量清洗**：文件哈希 + 规则指纹，断点续洗

## 安装

**要求**：Python 3.10+

```bash
git clone https://github.com/SpiralQWQ/text-cleaning-engine.git
cd text-cleaning-engine
pip install -r requirements.txt
```

`requirements.txt` 覆盖主环境（`clean-text`、`snownlp`、`jsonschema`、`sentencex`、`PyYAML`）。可选的 HTML 正文提取（`trafilatura`）和 PII 脱敏（`presidio`）在独立 venv 中运行——见 [`.env.example`](.env.example)。

## 配置

```bash
cp .env.example .env
# 可选：填写 trafilatura / presidio 的 venv python 路径、知识库目录
```

引擎所有工具路径都从环境读取——**代码零硬编码绝对路径**。用到什么配什么。

| 环境变量 | 用途 | 是否必需 |
|---------|------|---------|
| `TRAFILATURA_PY` | trafilatura venv 的 python（HTML 正文提取） | 仅真 HTML 输入时 |
| `PRESIDIO_PY` | presidio venv 的 python（PII 脱敏） | 仅 `--anonymize` 时 |
| `CLEAN_KB` | 批量清洗的输入知识库目录 | 或用 `--input` 指定 |

## 快速上手

清洗一段转写的最快路径——3 条命令，无需额外配置：

```bash
# 1. 清洗 ASR 转写 JSON（保结构）
python -m cleaner.clean_asr_json transcript.json        # → transcript_clean.json

# 2. 预览脏文件清洗前后的对比（不写文件）
python -m cleaner.cleaning --preview dirty.txt

# 3. 批量清洗一个文本目录
python cli/clean_batch.py --input ./texts --dry-run    # 先看统计
python cli/clean_batch.py --input ./texts --parallel 4 # → output/知识库_clean/
```

## 用法

```bash
# 清洗单个文件（前后对比预览）
python -m cleaner.cleaning --preview <文件>

# 清洗单个文件（批量模式，打印汇总）
python -m cleaner.cleaning --file <文件>

# 清洗 ASR 转写 JSON（保结构）
python -m cleaner.clean_asr_json transcript.json           # → transcript_clean.json

# 批量清洗目录（增量 + 并行 + 残留检测）
python cli/clean_batch.py --input <目录> --parallel 4      # → output/知识库_clean/

# 仅统计（dry-run，不写文件）
python cli/clean_batch.py --input <目录> --dry-run

# 批量清洗时可选 PII 脱敏（需配置 PRESIDIO_PY）
python cli/clean_batch.py --input <目录> --anonymize

# 清洗后去重检查（精确 md5 + 近似相似度）
python cli/clean_batch.py --input <目录> --dedup
```

## 架构

```
脏文本
 └─ cleaner/                 规则引擎
     ├─ cleaning.py          多动作引擎（delete/compress/protect/merge）+ 残留检测
     ├─ clean_asr_json.py    ASR JSON → 保结构 _clean.json
     ├─ clean_md.py          标准 Markdown 清洗入口（供外部工具集成）
     └─ sentence_normalize.py 句子级归一化（合并 OCR 拆行，保护帧标记）
 ├─ cli/clean_batch.py       批量管线（增量 · 并行 · 回退 · 审计元数据）
 ├─ rules/cleaning_rules.yaml 规则数据（按形态分组，多动作 v4）
 ├─ tests/                   保留率门禁（≥95%）+ 验收套件
 └─ docs/                    方案、验收、接口契约报告
```

规则按输入形态分组（`common` / `zhihu` / `video_ocr` / `video_asr`），自动选择。加新站点 = YAML 加一组，重跑。

## 转写内容保护（A-E）

视频转写特有的问题及解法：

| # | 问题 | 解法 |
|---|------|------|
| A | 重复字幕（视频重播） | **压缩**为 `原文…[出现N次]`——信号保留，不删除 |
| B | OCR 帧里的界面水印 | **删除**（行首锚定正则），教学行先行豁免 |
| C | OCR 乱码（`garblec`→`garbage`） | **检测**（词典 + 模糊匹配），教学行豁免 |
| D | OCR 拆行（一句字幕被拆 2 行） | **合并**（句子归一化 + 时间相邻判断） |
| E | 教学短行（音标 / 中文翻译 / 单词卡） | **保护**（白名单 + 模糊匹配），先于一切删除 |

## 集成联动

把 `text-cleaning-engine` 与 [**document-to-markdown**](https://github.com/SpiralQWQ/document-to-markdown)
（基于 MinerU 的 PDF / Word / PPT → Markdown 转换器）配合，形成完整文档管线：

```
PDF / Word / PPT →（document-to-markdown）→ Markdown →（text-cleaning-engine）→ 干净文本 → LLM
```

标准清洗入口可被任何外部工具调用：

```bash
python -m cleaner.clean_md full.md [--anonymize]           # → JSON {ok, cleaned_text, stats}
python -m cleaner.clean_md full.md --output full_clean.md  # → 同时写入清洗后文件
```

`document-to-markdown` 通过其 `--clean` 钩子在转换后自动调用本接口，把水印/导航/
乱码碎片在进入 LLM 前清洗掉。

## 运行测试

```bash
# 验收套件（依赖可选外部样本的项自动 SKIP）
python tests/test_acceptance.py

# 教学保留率门禁——防规则误删教学（≥95%）
python tests/test_teaching_retention.py

# 10 轮深度验证（fuzz / Unicode / 性能 / 红线合规）
python _tools/_verify_10rounds.py
```

> 可选外部样本：设置 `CLEAN_TEST_ZHI_HU`（知乎文本目录）与 `CLEAN_TEST_VIDEO_FILE`
> （视频转写文件）可在本地跑完整套件。缺失时依赖项自动跳过——克隆即跑，开箱即用。

## 文档

| 文档 | 内容 |
|------|------|
| [`docs/视频转写清洗方案_v1.0.md`](docs/视频转写清洗方案_v1.0.md) | 转写（OCR/ASR）清洗规则设计 |
| [`docs/接口对接/接口对接报告.md`](docs/接口对接/接口对接报告.md) | 输入契约：转写 JSON → 干净 JSON（格式 / 红线 / 接口 + 示例） |
| [`docs/开源许可合规_v1.0.md`](docs/开源许可合规_v1.0.md) | 依赖许可证合规（AGPL-3.0 可行性） |

## 贡献

欢迎任何形式的贡献——新规则分组、噪音词条、bug 反馈、文档、测试。请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 常见问题

**Q: 清洗需要 GPU / 重型 ML 依赖吗？**
不需要。核心引擎是纯 Python（正则 + 词典 + 规则数据）。可选的 `trafilatura` / `presidio` venv 很轻量，仅在配置后启用。

**Q: 会误删教学内容（字幕 / 翻译）吗？**
不会——这是核心设计保证。教学行（音标、翻译、单词卡、教学英文）在任何删除规则运行前先保护，另有保留率门禁（≥95%）与 >70% 误删自动回退兜底。

**Q: 如何新增一种噪音？**
编辑 `rules/cleaning_rules.yaml`——在对应形态分组加子串/正则（或新增分组），重跑即可，无需改代码。JSON-schema 校验会拦截写错。

**Q: 为什么批量输出路径里含 `知识库_clean`？**
这是默认镜像目录（见 `cli/clean_batch.py`）；每个清洗文件保持相对路径，清洗后的知识库仍可导航。

**Q: `--preview` 输出看起来比预期短？**
预览只截取清洗前后文本的前 300 字符。需要完整输出请用 `--file` 或批量模式。

## 支持

如果这个项目对你有帮助，欢迎请我喝杯咖啡。完全自愿——项目始终免费开源。对于独立开发者，每一份小小的心意都意义重大。

<p align="center">
  <img src="assets/donate_wechat.jpg" alt="微信支付" width="200">
  <img src="assets/donate_alipay.jpg" alt="支付宝" width="200">
</p>

<p align="center"><i>感谢你读到这里。🙏</i></p>

## 许可证

`text-cleaning-engine` 采用**双许可**：

1. **开源** — [GNU Affero General Public License v3（AGPL-3.0）](LICENSE)
2. **商业** — 无法接受 AGPL-3.0 义务的场景，见 [COMMERCIAL.md](COMMERCIAL.md)

Copyright (c) 2026 Spiral QWQ. All rights reserved.
