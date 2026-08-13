"""#95 全量验收测试 — 逐项检查清洗流水线装的内容全部生效。

开源版：外部样本数据（知乎 40 篇 / HTML / video）缺失时自动跳过依赖项（[SKIP]，不计入结果），
核心项始终运行（内置知乎样本兜底验证去导航/水印/广告能力）。
"""
import os, subprocess, sys, time
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))  # 项目根
# 知乎完整样本目录：经环境变量指定（本机完整验证时设），缺失自动 SKIP；不硬编码本机路径
ZHI_HU = os.environ.get("CLEAN_TEST_ZHI_HU", "")
sys.path.insert(0, PROJ)

from cleaner import cleaning as c

# --- 外部数据探测：缺失不崩溃，相关项自动 SKIP ---
_PATHS_TXT = os.path.join(ZHI_HU, "_zhihu_paths.txt")
_HTML_TEST = os.path.join(ZHI_HU, "_zhihu_real_html_test.html")
PATHS = [l.strip() for l in open(_PATHS_TXT, encoding="utf-8") if l.strip()] if os.path.exists(_PATHS_TXT) else []
# 视频转写样本：不硬编码绝对路径，用环境变量 CLEAN_TEST_VIDEO_FILE 指定（本机完整验证时设）
VFILE = os.environ.get("CLEAN_TEST_VIDEO_FILE", "")

# 内置知乎样本文本（无外部样本时，仍验证去导航/答主水印/AI标记/广告）
_BUILTIN_ZHIHU = (
    "如何写好简历？\n"
    "已关注 1,234 · 回答 56 · 被浏览 8,921,107\n"
    "综合用户论文AI 认可的回答\n"
    "完成回答，用时 12 秒\n"
    "好的简历，核心在于量化成果。\n"
    "内容由 AI 生成，请注意甄别\n"
    "下载同款App\n"
    "回答已赞同 1,234\n"
)

RESULTS = []
def check(no, name, ok, detail="", skipped=False):
    if not skipped:
        RESULTS.append(ok)
    tag = "SKIP" if skipped else ("PASS" if ok else "FAIL")
    print(f"  [{tag}] #{no} {name}" + (f" | {detail}" if detail else ""))

print("=" * 60)
print("#95 全量验收测试 — 清洗流水线")
print("=" * 60)

# ① trafilatura venv + HTML 提取（依赖 .env 配置 + 样本，缺失跳过）
tp = os.environ.get("TRAFILATURA_PY", "")
if tp and os.path.exists(_HTML_TEST):
    raw_html = open(_HTML_TEST, encoding="utf-8").read()
    r = c.clean_text(raw_html)
    check(1, "trafilatura venv + HTML 正文提取", os.path.exists(tp) and r["engine"] == "trafilatura"
          and "导航" not in r["text"] and "好的简历" in r["text"], f"engine={r['engine']}")
else:
    check(1, "trafilatura venv + HTML 正文提取", True, "跳过: 未配置 TRAFILATURA_PY 或样本缺失", skipped=True)

# ② clean-text 主环境 + URL/实体
r2 = c.clean_text("测试 https://example.com/x 及&nbsp;实体")
check(2, "clean-text 去 URL/还原实体", "example.com" not in r2["text"] and "实体" in r2["text"])

# ③ snownlp 主环境 + 中文分析
sn = c.analyze_snownlp("好的简历，核心在于量化。")
check(3, "snownlp 分句/词性可用", sn["available"] and len(sn["sentences"]) >= 1)

# ④ jsonschema 主环境 + 体检
v, errs = c.validate_schema({"ok": True, "text": "x", "engine": "bad", "stats": {}})
check(4, "jsonschema 体检拦截异常", v is False and len(errs) >= 1)

# ⑤ presidio venv + 脱敏（依赖 .env 配置，缺失跳过）
if os.environ.get("PRESIDIO_PY", ""):
    r5 = c.clean_text("电话 13800138000，邮箱 a@b.com", anonymize=True)
    check(5, "presidio PII 脱敏", r5["stats"].get("pii_removed", 0) == 2 and "***" in r5["text"])
else:
    check(5, "presidio PII 脱敏", True, "跳过: 未配置 PRESIDIO_PY", skipped=True)

# ⑥ 自研规则去水印/导航/广告（真实样本优先，无则内置样本兜底）
raw6 = open(PATHS[0], encoding="utf-8", errors="replace").read() if PATHS else _BUILTIN_ZHIHU
r6 = c.clean_text(raw6)
noise_left = any(w in r6["text"] for w in ["综合用户论文AI", "完成回答，用时", "下载同款"])
check(6, "自研规则去导航/水印/广告", not noise_left and "好的简历" in r6["text"])

# ⑦ 完整流水线 40 文件 OK + 体检（无外部样本跳过）
if PATHS:
    ok = valid = 0
    for p in PATHS:
        r7 = c.clean_text(open(p, encoding="utf-8", errors="replace").read())
        ok += r7["ok"]; valid += r7["valid"]
    check(7, "完整流水线 40 文件", ok == 40 and valid == 40, f"OK {ok}/40, 体检 {valid}/40")
else:
    check(7, "完整流水线 40 文件", True, "跳过: 无外部样本", skipped=True)

# ⑧ clean_batch.py 批量入口（dry-run 数据无关，恒跑）
out = subprocess.run([sys.executable, os.path.join(PROJ, "cli", "clean_batch.py"), "--dry-run"],
                     capture_output=True, text=True, encoding="utf-8", errors="replace")
check(8, "clean_batch 批量入口", out.returncode == 0, "dry-run 退出码 OK")

# ⑨ 降级路径(库缺失不阻断)
c2 = c
orig_ns = c.normalize_stage1
def fake(text):  # 模拟 clean-text 缺失
    return text
c.normalize_stage1 = fake
try:
    r9 = c.clean_text("测试 无库也能跑")
    ok9 = r9["ok"]
finally:
    c.normalize_stage1 = orig_ns
check(9, "库缺失降级不阻断", ok9)

# ⑩ 性能 40 文件（无外部样本跳过）
if PATHS:
    t0 = time.time()
    for p in PATHS:
        c.clean_text(open(p, encoding="utf-8", errors="replace").read())
    dt = time.time() - t0
    check(10, "性能 40 文件 <1s", dt < 1.0, f"{dt:.2f}s")
else:
    check(10, "性能 40 文件 <1s", True, "跳过: 无外部样本", skipped=True)

# ①① video_ocr 清洗（样本经环境变量 CLEAN_TEST_VIDEO_FILE 指定，缺失跳过）
if VFILE and os.path.exists(VFILE):
    VR = open(VFILE, encoding="utf-8", errors="replace").read()
    vr = c.clean_text(VR, form="video_ocr")
    check(11, "video_ocr 去帧标记/保留GLM描述", "=====" not in vr["text"] and "画面是" in vr["text"])
else:
    check(11, "video_ocr 去帧标记/保留GLM描述", True, "跳过: 未设 CLEAN_TEST_VIDEO_FILE", skipped=True)

# ①② video_asr 乱码规范化
if VFILE and os.path.exists(VFILE):
    JFILE = VFILE.replace("_visual.txt", ".json")
    if os.path.exists(JFILE):
        import json as _json
        VJ = _json.load(open(JFILE, encoding="utf-8"))
        vj = c.clean_text(VJ["text"], form="video_asr")
        check(12, "video_asr 乱码规范化", ",," not in vj["text"] and "??" not in vj["text"])
    else:
        check(12, "video_asr 乱码规范化", True, "跳过: 无对应 .json", skipped=True)
else:
    check(12, "video_asr 乱码规范化", True, "跳过: 未设 CLEAN_TEST_VIDEO_FILE", skipped=True)

# ①③ MD 代码块保护(E10): 代码块内容不被误删
r_md = c.clean_text("# 标题\n正文。\n```python\ndef f():\n    return 42\n```\n51 赞同")
check(13, "MD 代码块保留", "return 42" in r_md["text"] and "51 赞同" not in r_md["text"])

# ①④ 规则 YAML 校验(G): 当前 YAML 正常加载
try:
    c._load_rules()
    check(14, "规则 YAML 校验正常", True)
except Exception:
    check(14, "规则 YAML 校验正常", False)

print("=" * 60)
skips = 14 - len(RESULTS)
passed = sum(RESULTS)
print(f"验收结果: {passed}/{len(RESULTS)} 通过" + (f" ({skips} 项跳过: 外部样本缺失)" if skips else "")
      + (" 🎉" if passed == len(RESULTS) else " ❌ 有失败项"))
sys.exit(0 if passed == len(RESULTS) else 1)
