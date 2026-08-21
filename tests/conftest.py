"""conftest — 把仓库根加进 sys.path，保证 pytest 能 import cleaner 包。"""
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
