"""test_watermark_text.py — 精准渠道水印清除（clean_watermark_text）测试。

只清渠道水印、不动全文其他：拼行水印剥除、独立行删除、代码块保护、空行保留、正文不受影响。
"""
from cleaner.cleaning import clean_watermark_text


def test_拼行水印剥除保正文():
    text = "## 欢迎加入非盈利Python学习交流编程QQ群783462347，群里免费提供500+本Python书籍！ 1.8 使用TensorFlow\n正文第二行\n"
    out = clean_watermark_text(text)["text"]
    assert "## 1.8 使用TensorFlow" in out
    assert "QQ群" not in out
    assert "正文第二行" in out


def test_独立广告行删除():
    text = "QQ群: 436746675\n这是正文\n"
    out = clean_watermark_text(text)["text"]
    assert "QQ群" not in out
    assert "这是正文" in out


def test_代码块保护():
    text = "```\n欢迎加入QQ群123456免费领书\n```\n正文\n"
    out = clean_watermark_text(text)["text"]
    # 代码块内容原样保留（watermark 精准模式保护代码）
    assert "欢迎加入QQ群123456免费领书" in out
    assert "正文" in out


def test_空行保留():
    text = "第一行\n\n第三行\n"
    out = clean_watermark_text(text)["text"]
    assert out == text  # 无渠道水印时全文完全不动（含空行）


def test_正文不受影响():
    text = "这是正常正文，讨论Python。\n9.5 使用代理爬取微信公众号文章 …… 364\n"
    out = clean_watermark_text(text)["text"]
    assert out == text  # 精准模式不动其他内容


def test_邮箱微信号清除():
    text = "邮箱：carrieforchen@gmail.com，微信号：陈小莉\n正文\n"
    out = clean_watermark_text(text)["text"]
    assert "微信号" not in out
    assert "正文" in out
