# -*- coding: utf-8 -*-
"""清洗工作流 · 阶段0 接口适配 10 轮深度验证脚本

每轮一个攻击角度，含真实断言统计通过率。用法: python _verify_10rounds.py
"""
import sys, io, os, json, time, random, subprocess, hashlib, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根（_tools 的上级）
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

from cleaner.clean_asr_json import clean_asr_json, _dedup_segments, _clean_text_segment, _segment_key
from cleaner import cleaning as c

REPORT = []  # (轮名, 通过, 总数)
def round_report(name, ok, total):
    REPORT.append((name, ok, total))
    print(f"\n═══ {name}: {ok}/{total} 通过 ═══" + (" ✅" if ok==total else " ❌"))

# ══════════════════════ R1 功能正确性（真实示例） ══════════════════════
def r1():
    print("\n# R1 功能正确性（真实接口示例）")
    ok = total = 0
    def check(name, cond):
        nonlocal ok, total
        total += 1
        if cond: ok += 1; print(f"  ✅ {name}")
        else: print(f"  ❌ {name}")
    raw = json.load(open(r"docs\接口对接\示例文件\英文测试_示例.json", encoding="utf-8"))
    clean = clean_asr_json(raw)
    check("segments 6→5（去重重复记录）", len(clean["segments"])==5)
    check("sentences 6→6（句全保留）", len(clean["sentences"])==6)
    check("text 字段保留", "text" in clean)
    check("去重的是同文本同时间戳段", len([s for s in clean["segments"] if s["text"].startswith("Like, we usually")])==1)
    # 标点规范化
    check("?? → ?", "always more?" in clean["segments"][2]["text"] and "??" not in clean["segments"][2]["text"])
    check(",, → ,", ",," not in clean["text"])
    # review 段保留
    rev = [s for s in clean["segments"] if s["review"]]
    check("review=true 段保留", len(rev)==1 and "S tla r" in rev[0]["text"])
    # visual
    rawv = open(r"docs\接口对接\示例文件\英文测试_示例_visual.txt", encoding="utf-8").read()
    cleanv = c.clean_text(rawv, form="video_ocr")["text"]
    lines = [l for l in cleanv.split("\n") if l.strip()]
    wm = [l for l in lines if not l.startswith("画面") and not any(k in l for k in ["MILK","Dishuching","Lavndey","语的"])]
    check("visual 水印 0 残留", len(wm)==0)
    check("visual GLM 描述 4 帧保留", sum(1 for l in lines if l.startswith("画面"))==4)
    round_report("R1 功能正确性", ok, total)

# ══════════════════════ R2 边界条件 ══════════════════════
def r2():
    print("\n# R2 边界条件")
    ok = total = 0
    def check(name, cond):
        nonlocal ok, total
        total += 1
        if cond: ok += 1; print(f"  ✅ {name}")
        else: print(f"  ❌ {name}")
    check("空 dict", clean_asr_json({}) == {"text":"","segments":[],"sentences":[]})
    check("只有 text", clean_asr_json({"text":"hello"})["segments"]==[])
    check("单段", len(clean_asr_json({"segments":[{"text":"a","start_ms":0,"end_ms":1,"confidence":0.5}]})["segments"])==1)
    check("段全空 text", clean_asr_json({"segments":[{"text":"","start_ms":0,"end_ms":1,"confidence":0.5}]})["segments"][0]["text"]=="")
    check("段纯空白", clean_asr_json({"segments":[{"text":"   ","start_ms":0,"end_ms":1}]})["segments"][0]["text"]=="")
    check("段纯标点", clean_asr_json({"segments":[{"text":",,. . ??","start_ms":0,"end_ms":1}]})["segments"][0]["text"]=="")
    check("段纯符号", clean_asr_json({"segments":[{"text":"!!!###","start_ms":0,"end_ms":1}]})["segments"][0]["text"]=="")
    # 1 个段 10 次重复
    segs = [{"text":"same","start_ms":i,"end_ms":i+1,"confidence":0.5,"review":False} for i in range(10)]
    check("10个同文本不同时间全保留", len(_dedup_segments(segs))==10)
    # 同时间戳重复
    segs = [{"text":"same","start_ms":0,"end_ms":1,"confidence":0.5,"review":False} for _ in range(10)]
    check("10个同文本同时间删到1", len(_dedup_segments(segs))==1)
    round_report("R2 边界条件", ok, total)

# ══════════════════════ R3 畸形输入 fuzz ══════════════════════
def r3():
    print("\n# R3 畸形输入 fuzz（随机垃圾输入，不应崩溃）")
    ok = total = 0
    random.seed(42)
    junk_inputs = [
        None, 0, 1.5, "", "hello", [], [1,2], {"a":1}, (), True, False,
        {"segments": "notalist"}, {"segments": 123}, {"sentences": "x"},
        {"segments": [None]}, {"segments": [123, "str", None, {}]},
        {"segments": [{"text": None}]}, {"text": None},
        {"segments": [{"text": "x", "start_ms": None}]},
    ]
    # 随机 fuzz
    for _ in range(200):
        n = random.randint(0, 10)
        seg = []
        for _ in range(n):
            txt = random.choice(["a","中文","坚持打卡",",.,","S tla r",""] )
            seg.append({"text":txt,"start_ms":random.randint(0,999),"end_ms":random.randint(1000,9999),
                        "confidence":random.random(),"review":random.choice([True,False])})
        junk_inputs.append({"text":"","segments":seg,"sentences":[]})
    for i, inp in enumerate(junk_inputs):
        try:
            r = clean_asr_json(inp)
            # 结构必须完整
            assert isinstance(r, dict) and "segments" in r and "sentences" in r and "text" in r
            assert isinstance(r["segments"], list) and isinstance(r["sentences"], list)
            ok += 1
        except Exception as e:
            print(f"  ❌ 输入#{i} {type(inp).__name__} 崩溃: {e}")
        total += 1
    check_summary = f"  fuzz {total} 种输入，{ok} 不崩溃"
    print(f"  {'✅' if ok==total else '❌'} {check_summary}")
    round_report("R3 畸形输入 fuzz", ok, total)

# ══════════════════════ R4 Unicode / 编码极端 ══════════════════════
def r4():
    print("\n# R4 Unicode / 编码极端")
    ok = total = 0
    def check(name, cond):
        nonlocal ok, total
        total += 1
        if cond: ok += 1; print(f"  ✅ {name}")
        else: print(f"  ❌ {name}")
    # emoji
    r = clean_asr_json({"segments":[{"text":"Hello 😀 world","start_ms":0,"end_ms":1}]})
    check("emoji 保留", "😀" in r["segments"][0]["text"])
    # 零宽字符
    z = "a​b"
    r = clean_asr_json({"segments":[{"text":z,"start_ms":0,"end_ms":1}]})
    check("零宽字符不崩溃", r["segments"][0]["text"]==z)
    # 全角标点
    r = clean_asr_json({"segments":[{"text":"你好，世界。","start_ms":0,"end_ms":1}]})
    check("中文全角标点保留", "，" in r["segments"][0]["text"] and "。" in r["segments"][0]["text"])
    # 混合中英日韩
    r = clean_asr_json({"segments":[{"text":"你好 hello こんにちは 안녕","start_ms":0,"end_ms":1}]})
    check("中英日韩混合保留", "こんにちは" in r["segments"][0]["text"] and "안녕" in r["segments"][0]["text"])
    # 超长 Unicode 串
    long = "中"*5000
    r = clean_asr_json({"segments":[{"text":long,"start_ms":0,"end_ms":1}]})
    check("5000 中文字保留", r["segments"][0]["text"]==long)
    round_report("R4 Unicode 极端", ok, total)

# ══════════════════════ R5 重复稳定性（确定性） ══════════════════════
def r5():
    print("\n# R5 重复稳定性（同一输入多次结果一致）")
    ok = total = 0
    raw = json.load(open(r"docs\接口对接\示例文件\英文测试_示例.json", encoding="utf-8"))
    hashes = set()
    for i in range(10):
        r = clean_asr_json(json.loads(json.dumps(raw)))
        h = hashlib.md5(json.dumps(r, ensure_ascii=False).encode()).hexdigest()
        hashes.add(h)
        ok += 1; total += 1
        if len(hashes) > 1:
            print(f"  ❌ 第{i}次结果不一致!")
    check_ok = len(hashes)==1
    print(f"  {'✅' if check_ok else '❌'} 10 次运行 hash 唯一: {len(hashes)} 种")
    round_report("R5 重复稳定性", ok if check_ok else 0, total)

# ══════════════════════ R6 性能压测 ══════════════════════
def r6():
    print("\n# R6 性能压测（大数据量）")
    ok = total = 0
    # 构造 1000 段的大 json（模拟长视频）
    big_segs = []
    for i in range(1000):
        txt = "This is segment number %d. 这是第%d段教学讲解。" % (i, i)
        big_segs.append({"text":txt,"start_ms":i*100,"end_ms":i*100+99,"confidence":0.9,"review":False})
    big = {"text":"","segments":big_segs,"sentences":[]}
    t0 = time.time()
    r = clean_asr_json(big)
    dt = time.time() - t0
    check_ok = dt < 2.0 and len(r["segments"])==1000
    print(f"  {'✅' if check_ok else '❌'} 1000 段清洗 {dt:.2f}s, 段数 {len(r['segments'])}")
    ok += int(check_ok); total += 1
    # 1000 段全重复（去重性能）
    dup_segs = [{"text":"same phrase","start_ms":i,"end_ms":i+1,"confidence":0.9,"review":False} for i in range(1000)]
    t0 = time.time()
    r = clean_asr_json({"segments":dup_segs,"sentences":[]})
    dt2 = time.time() - t0
    check2 = dt2 < 1.0 and len(r["segments"])==1000
    print(f"  {'✅' if check2 else '❌'} 1000 同文本不同时间 去重 {dt2:.2f}s, 保留 {len(r['segments'])}")
    ok += int(check2); total += 1
    round_report("R6 性能压测", ok, total)

# ══════════════════════ R7 集成回归 ══════════════════════
def r7():
    print("\n# R7 集成回归（原 14 项验收 + 模块共存）")
    ok = total = 0
    r = subprocess.run([sys.executable, "tests/test_acceptance.py"], capture_output=True, text=True, encoding="utf-8")
    # 验收套件有 SKIP 机制（外部样本缺失时跳过依赖项）——断言"无 FAIL 且核心项全过"
    m = re.search(r"验收结果:\s*(\d+)/(\d+)\s*通过", r.stdout)
    passed, total_ok = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    check_ok = total_ok > 0 and passed == total_ok
    print(f"  {'✅' if check_ok else '❌'} 验收 {passed}/{total_ok} 通过")
    ok += int(check_ok); total += 1
    import cleaner.clean_asr_json, cleaner.cleaning
    print("  ✅ 两模块共存导入")
    ok += 1; total += 1
    # 规则加载（当前 YAML v4）
    rules = c._load_rules()
    ver = rules.get('version')
    print(f"  {'✅' if ver==4 else '❌'} YAML v{ver} 加载")
    ok += int(ver==4); total += 1
    round_report("R7 集成回归", ok, total)

# ══════════════════════ R8 红线完整 ══════════════════════
def r8():
    print("\n# R8 接口红线完整检查")
    ok = total = 0
    def check(name, cond):
        nonlocal ok, total
        total += 1
        if cond: ok += 1; print(f"  ✅ {name}")
        else: print(f"  ❌ {name}")
    raw = json.load(open(r"docs\接口对接\示例文件\英文测试_示例.json", encoding="utf-8"))
    clean = clean_asr_json(raw)
    def norm(t): return re.sub(r"[^a-z0-9一-鿿]", "", t.lower())
    # 每个保留段 时间戳/confidence/review 与原文一致
    for cs in clean["segments"]:
        match = next((rs for rs in raw["segments"] if norm(cs["text"])==norm(rs["text"])), None)
        if match:
            check(f"时间戳不变", cs["start_ms"]==match["start_ms"] and cs["end_ms"]==match["end_ms"])
            check(f"confidence不变", cs["confidence"]==match["confidence"])
            check(f"review不变", cs["review"]==match["review"])
    # 中文段全保留
    cn_in = [s for s in raw["segments"] if any("一"<=ch<="鿿" for ch in s["text"])]
    cn_out = [s for s in clean["segments"] if any("一"<=ch<="鿿" for ch in s["text"])]
    check(f"中文段全保留({len(cn_in)}→{len(cn_out)})", len(cn_in)==len(cn_out))
    # 结构字段完整
    for s in clean["segments"]:
        check("段字段齐全", all(k in s for k in ("text","start_ms","end_ms","confidence","review")))
    round_report("R8 红线完整", ok, total)

# ══════════════════════ R9 规则引擎一致性 ══════════════════════
def r9():
    print("\n# R9 规则引擎一致性（YAML 规则 vs 引擎行为）")
    ok = total = 0
    rules = c._load_rules()
    regexes = rules.get("noise_regex", [])
    # YAML 中所有水印正则，引擎都应能匹配对应行
    pairs = [
        ("^坚持打卡", "坚持打卡30天听九口语突飞猛进"),
        ("^片名[：:]", "片名：查莉成长日记"),
        ("^知识点\\d+", "知识点12345"),
        ("^高手盲听", "高手盲听"),
        ("^初学看字幕", "初学看字幕"),
        ("^纯英[文宇字]+幕$", "纯英文字幕"),
        ("^纯英[文宇字]+幕$", "纯英文宇幕"),
        ("^爱说英语的福安", "爱说英语的福安"),
    ]
    for pat, line in pairs:
        r = c.clean_text(line, form="video_ocr")
        kept = line in r["text"]
        print(f"  {'✅' if not kept else '❌'} 「{line}」被删 (规则 {pat})")
        ok += int(not kept); total += 1
    # 反向：教学短行不应被删
    for keep_line in ["MILK", "Dishuching", "Listen up.", "The Duncans"]:
        r = c.clean_text(keep_line, form="video_ocr")
        kept = keep_line in r["text"]
        print(f"  {'✅' if kept else '❌'} 「{keep_line}」保留（教学）")
        ok += int(kept); total += 1
    round_report("R9 规则一致性", ok, total)

# ══════════════════════ R10 综合压力（组合场景） ══════════════════════
def r10():
    print("\n# R10 综合压力（组合场景全链路）")
    ok = total = 0
    def check(name, cond, detail=""):
        nonlocal ok, total
        total += 1
        if cond: ok += 1; print(f"  ✅ {name}" + (f" | {detail}" if detail else ""))
        else: print(f"  ❌ {name}" + (f" | {detail}" if detail else ""))
    # 模拟完整视频：大 json（含中文讲解/重复段/低置信段）+ 大 visual
    segs = []
    english_phrases = ["Okay, everybody, listen up.", "The Duncans are going to be able to do it.", "S tla r 形容词一流的。", "So. The plan is to head up."]
    for i in range(500):
        if i % 3 == 0:
            txt = "这是第%d段中文教学讲解，强调 listen up 的用法。" % i
        else:
            txt = english_phrases[i % len(english_phrases)]
        segs.append({"text":txt,"start_ms":i*100,"end_ms":i*100+99,"confidence":0.4 if i%7==0 else 0.9,"review":i%7==0})
    big = {"text":"","segments":segs,"sentences":[]}
    t0 = time.time()
    r = clean_asr_json(big)
    dt = time.time() - t0
    check("500 段压测完成", dt < 2.0, f"{dt:.2f}s")
    # 中文段应全保留：含中文字符的段（含"S tla r 形容词一流的"这类中英混合段）
    def has_cn(t): return any("一"<=ch<="鿿" for ch in t)
    cn = [s for s in r["segments"] if has_cn(s["text"])]
    cn_expected = sum(1 for s in segs if has_cn(s["text"]))
    check(f"中文段全保留 ({len(cn)}/{cn_expected})", len(cn) == cn_expected)
    # review 段保留
    rev = [s for s in r["segments"] if s["review"]]
    check(f"review 段保留 ({len(rev)})", len(rev) == sum(1 for s in segs if s["review"]))
    # 输出可 JSON 序列化
    s = json.dumps(r, ensure_ascii=False)
    check("输出可 JSON 序列化", len(s) > 0)
    # 与真实示例再跑一遍（组合确认）
    raw = json.load(open(r"docs\接口对接\示例文件\英文测试_示例.json", encoding="utf-8"))
    check("真实示例最终可用", len(clean_asr_json(raw)["segments"])==5)
    round_report("R10 综合压力", ok, total)

if __name__ == "__main__":
    r1(); r2(); r3(); r4(); r5(); r6(); r7(); r8(); r9(); r10()
    print("\n" + "="*60)
    print("10 轮验证总汇:")
    tot_ok = sum(o for _, o, _ in REPORT)
    tot = sum(t for _, _, t in REPORT)
    for name, ok, t in REPORT:
        print(f"  {name}: {ok}/{t}" + (" ✅" if ok==t else " ❌"))
    print(f"\n总计: {tot_ok}/{tot} 通过" + (" 🎉" if tot_ok==tot else " ❌ 有失败"))
    sys.exit(0 if tot_ok==tot else 1)
