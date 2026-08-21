"""test_noise_inline.py — 行内水印移除规则（渠道广告水印，PDF/文档转写产物）。

覆盖：拼行水印剥除（保留正文）、独立广告行删除、OCR 变体、不误删目录/教学/正文。
"""
import pytest

from cleaner.cleaning import clean_text


@pytest.mark.parametrize("text,expected", [
    # 拼行：渠道水印剥除、章节标题完整保留
    ("## 欢迎加入非盈利Python学习交流编程QQ群783462347，群里免费提供500+本Python书籍！ 1.8 使用TensorFlow",
     "## 1.8 使用TensorFlow"),
    # 独立 QQ群号行 → 删除
    ("QQ群: 436746675", ""),
    # OCR 变体水印 → 删除
    ("欢迎加入非盈利Python编学习交流程QQ群783462347，群里免费提供500+本Python书籍！", ""),
    # 公众号+微信号 → 删除
    ("微信公众号 华章电子书（微信号：hzebook）", ""),
])
def test_渠道水印清除(text, expected):
    out = clean_text(text, form="markdown")["text"]
    assert out == expected


@pytest.mark.parametrize("text", [
    # 目录含"微信公众号"但不带"（微信号"结构 → 不误删
    "9.5 使用代理爬取微信公众号文章 …… 364",
    # 教学内容里教用户关注公众号 → 不误删
    "建议你动手练习一次，然后在微信公众号中回复“循环”获得答案，微信公众号是：easypython",
    # 正常正文 → 不误删
    "这是正常的正文内容，讨论 Python 编程。",
    # 含"QQ群"字样但不带数字水印特征 → 不误删
    "文中提到的QQ群讨论区是社区交流的地方。",
])
def test_不误删正文(text):
    out = clean_text(text, form="markdown")["text"]
    assert text in out
