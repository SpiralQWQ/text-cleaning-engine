# -*- coding: utf-8 -*-
"""D2.2 验证 — 知乎方法论是否已入 RAG 索引。

重建后跑: 验证
  1. 索引含"知乎/" source 的块
  2. 简历方法论查询能命中知乎块
用法: python 本地样本/清洗调研/_verify_zhihu_rag.py
"""
import json
import os
import sys

import numpy as np

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE, 'rag')
K = 5

# 知乎方法论查询: query → 期望命中 source 含"知乎/"
ZHIHU_QUERIES = [
    "简历工作经历如何量化成果",
    "STAR法则怎么写简历经历",
    "简历排版一页纸技巧",
    "HR筛选简历关注什么",
    "简历自我评价怎么写",
    "应届生零经验简历怎么写",
]


def load_index():
    data = np.load(os.path.join(OUT_DIR, 'index.npz'))
    vectors = data['vectors']
    with open(os.path.join(OUT_DIR, 'chunks.jsonl'), encoding='utf-8') as f:
        chunks = [json.loads(l) for l in f]
    return vectors, chunks


def search(query_vec, vectors, topk=K):
    scores = vectors @ query_vec
    top_idx = np.argsort(scores)[-topk:][::-1]
    return [(scores[i], i) for i in top_idx]


def main():
    sys.path.insert(0, BASE)
    import torch
    from transformers import AutoModel, AutoTokenizer
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    tokenizer = AutoTokenizer.from_pretrained('BAAI/bge-m3')
    model = AutoModel.from_pretrained('BAAI/bge-m3').to(device).eval()

    vectors, chunks = load_index()
    zhihu_count = sum(1 for c in chunks if c['source'].startswith('知乎/'))
    print(f'索引: {vectors.shape[0]} 块 | 知乎块: {zhihu_count}')
    print(f'知乎块占比: {zhihu_count/len(chunks)*100:.1f}%')
    print('=' * 50)
    hit = 0
    for q in ZHIHU_QUERIES:
        with torch.no_grad():
            inputs = tokenizer([q], padding=True, truncation=True, max_length=512, return_tensors='pt').to(device)
            out = model(**inputs)
            emb = torch.nn.functional.normalize(out.last_hidden_state[:, 0], p=2, dim=1).cpu().numpy()
        results = search(emb[0], vectors)
        top_sources = [chunks[i]['source'] for _, i in results]
        zhihu_hit = any(s.startswith('知乎/') for s in top_sources)
        hit += 1 if zhihu_hit else 0
        print(f'{"✓ 命中知乎" if zhihu_hit else "✗ 未命中"} [{q[:20]}] → top1: {top_sources[0][:50]}')
        if zhihu_hit:
            zs = [s for s in top_sources if s.startswith("知乎/")][0]
            print(f'    知乎source: {zs[:60]}')
    print('=' * 50)
    print(f'知乎命中: {hit}/{len(ZHIHU_QUERIES)}')
    return 0 if hit >= 3 else 1


if __name__ == '__main__':
    sys.exit(main())
