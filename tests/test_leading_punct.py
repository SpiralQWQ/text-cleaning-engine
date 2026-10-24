"""test_leading_punct.py — 句首孤立标点剥离（ASR 断句残留，回灌清单 B-7）。

覆盖：句首逗号/句号剥离、连续标点整段剥离、句中与句尾标点不误伤、
纯标点段仍清空。与 media-to-markdown 的 `TestLeadingPunct` 是同一条规则
（`_PUNCT_PAIRS` 同源副本），两边行为必须一致。
"""
import pytest

from cleaner.clean_asr_json import _clean_text_segment, _strip_leading_punct


@pytest.mark.parametrize("text,expected", [
    # 句首逗号：ASR 在「。」后断句，上一句的「，」落到下一句开头
    ("，把相关当成因果。", "把相关当成因果。"),
    ("，我要给你个参与点陈强的车挂。", "我要给你个参与点陈强的车挂。"),
    # 连续标点：_PUNCT_PAIRS 先把「。，」压成「。」，两个标记都要走
    ("。，把相关当成因果。", "把相关当成因果。"),
    ("，。；把相关当成因果。", "把相关当成因果。"),
    # 英文标点同样处理
    (", leading comma stays.", "leading comma stays."),
])
def test_句首标点被剥掉(text, expected):
    assert _clean_text_segment(text) == expected


@pytest.mark.parametrize("text,expected", [
    # 句中、句尾的标点不归这里管
    ("正常句子，中间有逗号。", "正常句子，中间有逗号。"),
    ("结尾有逗号，", "结尾有逗号，"),
    ("请问问题中的意思？", "请问问题中的意思？"),
])
def test_句中句尾标点不误伤(text, expected):
    assert _clean_text_segment(text) == expected


def test_strip_leading_punct_只动串首():
    assert _strip_leading_punct("，句中还有，句尾也有，") == "句中还有，句尾也有，"
    assert _strip_leading_punct("没有前导标点") == "没有前导标点"


@pytest.mark.parametrize("text", ["，，，", "。", ",,,", "。。。，"])
def test_纯标点段仍清空(text):
    # 剥掉串首后若什么都不剩，必须返回空串，不能留半个标点
    assert _clean_text_segment(text) == ""
