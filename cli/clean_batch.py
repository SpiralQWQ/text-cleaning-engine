"""知识库批量清洗 → 干净文本库。

扫描知识库中所有文本型文件，经 cleaner.cleaning.clean_text 全链清洗
(Stage0 trafilatura → Stage1 clean-text → Stage3 自研中文规则 → Stage4 jsonschema
 → Stage5 presidio 可选脱敏)，输出干净文本到 知识库_clean/ 镜像目录，并生成汇总报告。

输出结构(镜像知识库):
    知识库_clean/{词}/{类别}/{原标题}.txt         # 干净文本
    知识库_clean/{词}/{类别}/{原标题}.meta.json   # 清洗元数据

用法:
    python tools/clean_kb.py                # 全量清洗(默认 html)
    python tools/clean_kb.py --suffix md    # 只清洗 md
    python tools/clean_kb.py --dry-run      # 只统计不清洗
    python tools/clean_kb.py --anonymize    # 清洗+presidio PII 脱敏(发布用)
"""
import argparse
import hashlib
import json
import logging
import os
import sys
import time
from multiprocessing import Pool

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

KB = os.environ.get("CLEAN_KB", "")  # 输入源: 环境变量或 --input
from cleaner.cleaning import clean_text, scan_residual, check_content_integrity  # noqa: E402


def _setup_stdout():
    try:
        if not sys.stdout.isatty():
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if not sys.stderr.isatty():
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


def _kb_clean_root() -> str:
    """干净文本库根: 独立项目 output/知识库_clean。"""
    root = os.path.join(BASE, "output", "知识库_clean")
    os.makedirs(root, exist_ok=True)
    return root


def _walk_text_files(root: str, suffix: str):
    """递归收集指定后缀文本文件。"""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in ("_tmp_dl", "node_modules", ".git")]
        for f in filenames:
            if f.lower().endswith("." + suffix.lower()):
                yield os.path.join(dirpath, f)


def _rel_without_ext(abs_path: str) -> str:
    """绝对路径 → 相对知识库根、去扩展名的镜像相对路径。"""
    rel = os.path.relpath(abs_path, KB)
    return os.path.splitext(rel)[0]


def _rules_fingerprint() -> str:
    """cleaning_rules.yaml 内容指纹(md5); 规则变了 → 增量失效, 全量重洗。"""
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "rules", "cleaning_rules.yaml")
    try:
        return hashlib.md5(open(p, "rb").read()).hexdigest()
    except OSError:
        return "no-rules"


def _setup_logger() -> logging.Logger:
    """清洗日志(E3): 写 logs/clean_kb.log, 记录运行/失败/摘要可排查。"""
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger("clean_kb")
    if not logger.handlers:
        handler = logging.FileHandler(os.path.join(log_dir, "clean_kb.log"), encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


_LOGGER = _setup_logger()


def _dedup_check(clean_root: str) -> dict:
    """清洗后去重检查(E5, 借鉴 dupeguru 内容哈希): 精确(md5) + 近似(长度接近且前300字相似>0.75)。

    Returns: {"exact": [[重复组]], "approx": [(相似度, p1, p2)]}
    """
    from difflib import SequenceMatcher
    txts = []
    for root, _, names in os.walk(clean_root):
        for n in names:
            if n.endswith(".txt") and not n.startswith("_"):
                p = os.path.join(root, n)
                try:
                    t = open(p, encoding="utf-8", errors="ignore").read()
                except OSError:
                    continue
                if t.strip():
                    txts.append((p, t))
    # 精确去重(内容哈希)
    exact = {}
    for p, t in txts:
        exact.setdefault(hashlib.md5(t.encode("utf-8")).hexdigest(), []).append(p)
    exact_dups = [v for v in exact.values() if len(v) > 1]
    # 近似: 长度差<15% + 前300字相似>0.75(按长度接近才比, 降 O(n²))
    approx = []
    for i in range(len(txts)):
        pi, ti = txts[i]
        for j in range(i + 1, len(txts)):
            pj, tj = txts[j]
            li, lj = len(ti), len(tj)
            if li == 0 or abs(li - lj) / max(li, lj) > 0.15:
                continue
            s = SequenceMatcher(None, ti[:300], tj[:300]).ratio()
            if s > 0.75:
                approx.append((round(s, 2), pi, pj))
    return {"exact": exact_dups, "approx": approx}


def _clean_one(args):
    """并行 worker(E4): 读文件 + 清洗, 失败重试3次(E11, 借鉴 prefect 重试思想)。"""
    fp, anonymize = args
    for attempt in range(3):
        try:
            raw = open(fp, encoding="utf-8", errors="replace").read()
            res = clean_text(raw, anonymize=anonymize)
            return fp, raw, res
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                return fp, None, {"ok": False, "error": str(e)}
    return fp, None, {"ok": False, "error": "重试耗尽"}


def clean_kb(suffix: str = "html", anonymize: bool = False,
             dry_run: bool = False, parallel: int = 1) -> dict:
    """清洗知识库全部指定类型文本。返回汇总统计。"""
    clean_root = _kb_clean_root()
    files = list(_walk_text_files(KB, suffix))
    rules_fp = _rules_fingerprint()
    _LOGGER.info(f"运行开始: {len(files)} 文件, rules_fp={rules_fp[:8]}, anonymize={anonymize}")
    # 增量状态(E1): 文件哈希 + 规则指纹, 都未变 → 跳过
    state_file = os.path.join(clean_root, "_clean_state.json")
    state = {}
    if os.path.exists(state_file):
        try:
            state = json.load(open(state_file, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            state = {}
    stats = {"total": len(files), "ok": 0, "valid": 0, "engine": {"plain": 0, "trafilatura": 0},
             "skipped_empty": 0, "skipped_incr": 0, "pii_total": 0, "residual": 0,
             "content_issue": 0, "total_raw": 0, "total_clean": 0}
    results = []
    # 阶段1: 收集待洗文件(增量判断, 只算哈希)
    todo = []
    for fp in files:
        try:
            fh = hashlib.md5(open(fp, "rb").read()).hexdigest()
        except OSError:
            fh = ""
        prev = state.get(fp, {})
        out_txt = os.path.join(clean_root, _rel_without_ext(fp) + ".txt")
        # 断点续洗(E9): 输出文件不存在(中断/手动删除丢失) → 必须重洗恢复
        if not os.path.exists(out_txt):
            todo.append((fp, fh))
            continue
        # 增量(E1): 输出已存在 + hash + 规则指纹 都未变 → 跳过
        if prev.get("hash") == fh and prev.get("rules_fp") == rules_fp:
            stats["skipped_incr"] += 1
            continue
        # 断点续洗: 输出存在且比源新(中断后恢复) → 视为已洗, 补记 state
        if os.path.getmtime(out_txt) >= os.path.getmtime(fp):
            stats["skipped_incr"] += 1
            state[fp] = {"hash": fh, "rules_fp": rules_fp,
                         "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
            continue
        todo.append((fp, fh))
    fh_map = dict(todo)
    # 阶段2: 清洗(并行 E4 / 串行)
    if parallel > 1 and todo:
        with Pool(parallel) as pool:
            cleaned = list(pool.imap_unordered(_clean_one, [(fp, anonymize) for fp, _ in todo]))
    else:
        cleaned = [_clean_one((fp, anonymize)) for fp, _ in todo]
    # 阶段3: 后处理(检测/写文件/state) 主进程串行
    for fp, raw, res in cleaned:
        if not res["ok"]:
            stats["skipped_empty"] += 1
            print(f"⚠ 清洗失败/空结果: {fp} {res.get('error', '')}")
            _LOGGER.warning(f"清洗失败 {fp}: {res.get('error', '')}")
            continue
        stats["ok"] += 1
        stats["valid"] += 1 if res.get("valid") else 0
        stats["engine"][res["engine"]] += 1
        stats["pii_total"] += res["stats"].get("pii_removed", 0)
        stats["total_raw"] += res["stats"]["raw_len"]
        stats["total_clean"] += res["stats"]["clean_len"]
        # 残留检测: 清洗后仍命中已知噪音 → 报出, 防漏网
        residual = scan_residual(res["text"])
        if residual:
            stats["residual"] += len(residual)
            print(f"⚠ 残留 {len(residual)} 处 [{os.path.basename(fp)}]:")
            for r in residual[:3]:
                print(f"    - {r}")
        # 正文完整性: 该保留的正文是否被误删(防误删)
        content_issues = check_content_integrity(raw, res["text"])
        if content_issues:
            stats["content_issue"] += len(content_issues)
            print(f"⚠ 正文问题 {len(content_issues)} 处 [{os.path.basename(fp)}]:")
            for issue in content_issues[:3]:
                print(f"    - {issue}")
        # R3 空输出回退(ffsubsync min_keep_ratio): 清洗后保留率<30% 判定误删 → 回退原文
        #   防"新规则误删 70%+ 正文/教学"时输出空壳(调研2 adrianmusante 空输出回退思想)
        ratio = res["stats"]["clean_len"] / max(1, res["stats"]["raw_len"])
        if res["stats"]["raw_len"] > 50 and ratio < 0.30:
            print(f"⚠ 保留率过低 {ratio:.0%}(<30%) 判定误删 → 回退原文 [{os.path.basename(fp)}]")
            res["_fallback"] = True
            res["text"] = raw
            res["stats"]["clean_len"] = res["stats"]["raw_len"]
        if dry_run:
            continue
        # 镜像输出: 知识库_clean/{词}/{类别}/{标题}.txt + .meta.json
        rel = _rel_without_ext(fp)
        out_txt = os.path.join(clean_root, rel + ".txt")
        out_meta = os.path.join(clean_root, rel + ".meta.json")
        os.makedirs(os.path.dirname(out_txt), exist_ok=True)
        with open(out_txt, "w", encoding="utf-8", newline="") as f:
            f.write(res["text"])
        meta = {
            "source": fp,
            "term": rel.split(os.sep)[0],
            "engine": res["engine"],
            "raw_len": res["stats"]["raw_len"],
            "clean_len": res["stats"]["clean_len"],
            "ratio": round(res["stats"]["clean_len"] / max(1, res["stats"]["raw_len"]), 4),
            "pii_removed": res["stats"].get("pii_removed", 0),
            "valid": res.get("valid", True),
            "audit": {  # R3 审计: 决策可追溯
                "fallback": res.get("_fallback", False),  # 是否触发空输出回退
                "residual": len(residual),
                "content_issue": len(content_issues),
            },
        }
        with open(out_meta, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        results.append((rel, meta))
        state[fp] = {"hash": fh_map[fp], "rules_fp": rules_fp, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
        print(f"  ✔ {rel}.txt ({meta['ratio']:.0%})")
    if not dry_run:
        os.makedirs(clean_root, exist_ok=True)
        json.dump(state, open(state_file, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        # 结构化索引(E2): 扫描输出目录全部 .meta.json(含增量跳过), 供下游消费
        metas = []
        for root, _, names in os.walk(clean_root):
            for n in names:
                if n.endswith(".meta.json"):
                    try:
                        metas.append(json.load(open(os.path.join(root, n), encoding="utf-8")))
                    except Exception:  # noqa: BLE001
                        pass
        index = {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "rules_fp": rules_fp,
                 "total": len(metas), "files": metas}
        json.dump(index, open(os.path.join(clean_root, "_clean_results.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        # 统计报告(E8): 每次运行汇总追加历史, 供监控/趋势
        report_file = os.path.join(clean_root, "_clean_report.json")
        report = {"runs": []}
        if os.path.exists(report_file):
            try:
                report = json.load(open(report_file, encoding="utf-8"))
            except Exception:  # noqa: BLE001
                report = {"runs": []}
        ratio = stats["total_clean"] / max(1, stats["total_raw"])
        report["runs"].append({
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "total": stats["total"],
            "ok": stats["ok"], "skipped_incr": stats["skipped_incr"],
            "residual": stats["residual"], "content_issue": stats["content_issue"],
            "ratio": round(ratio, 4)})
        json.dump(report, open(report_file, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    _LOGGER.info(f"运行完成: OK {stats['ok']}, 增量跳过 {stats['skipped_incr']}, "
                 f"残留 {stats['residual']}, 正文问题 {stats['content_issue']}")
    return stats


def main():
    parser = argparse.ArgumentParser(description="知识库批量清洗→干净文本库")
    parser.add_argument("--suffix", default="html", help="清洗的文件类型(默认 html)")
    parser.add_argument("--dry-run", action="store_true", help="只统计不清洗")
    parser.add_argument("--anonymize", action="store_true", help="presidio PII 脱敏(发布用)")
    parser.add_argument("--parallel", type=int, default=1, help="并行清洗进程数(E4, 默认1=串行)")
    parser.add_argument("--dedup", action="store_true", help="清洗后去重检查(E5)")
    parser.add_argument("--input", default=None, help="输入知识库目录(默认 CLEAN_KB 或当前目录)")
    args = parser.parse_args()
    global KB
    if args.input:
        KB = os.path.abspath(args.input)
    elif not KB:
        KB = os.environ.get("CLEAN_KB", "") or BASE

    print(f"📚 知识库: {KB}")
    print(f"🧹 清洗类型: .{args.suffix} | 脱敏: {'开' if args.anonymize else '关'}")
    print("=" * 55)
    stats = clean_kb(suffix=args.suffix, anonymize=args.anonymize, dry_run=args.dry_run,
                     parallel=args.parallel)

    print("=" * 55)
    if stats["total_raw"]:
        ratio = stats["total_clean"] / stats["total_raw"]
    else:
        ratio = 0
    print(f"✅ 完成: {stats['total']} 个文件 | OK {stats['ok']} | 体检合格 {stats['valid']} | 增量跳过 {stats['skipped_incr']}")
    print(f"  引擎: trafilatura {stats['engine']['trafilatura']} / plain {stats['engine']['plain']}")
    print(f"  保留比例: {ratio:.0%} | 空结果跳过: {stats['skipped_empty']}")
    if stats["residual"]:
        print(f"  ⚠ 残留噪音: {stats['residual']} 处 (检测器发现规则漏网, 需检查 YAML 规则)")
    else:
        print("  ✅ 残留噪音: 0 处 (检测器确认干净)")
    if stats["content_issue"]:
        print(f"  ⚠ 正文问题: {stats['content_issue']} 处 (疑似误删正文, 需检查)")
    else:
        print("  ✅ 正文完整性: 正常 (无误删)")
    if stats["pii_total"]:
        print(f"  PII 脱敏: {stats['pii_total']} 处")
    if not args.dry_run:
        print(f"  输出: {_kb_clean_root()}")
    if args.dedup and not args.dry_run:
        dups = _dedup_check(_kb_clean_root())
        print(f"  🔍 去重检查(E5): 精确重复组 {len(dups['exact'])} | 近似重复对 {len(dups['approx'])}")
        for g in dups['exact'][:3]:
            print(f"    精确重复: {os.path.basename(g[0])[:40]}")
        for s, p1, p2 in dups['approx'][:3]:
            print(f"    近似({s}): {os.path.basename(p1)[:25]} ~ {os.path.basename(p2)[:25]}")


_setup_stdout()

if __name__ == "__main__":
    main()
