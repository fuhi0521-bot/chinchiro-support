#!/usr/bin/env python3
"""麻雀計算エンジンの実行入口。

    python3 mj.py discard 3456778m234p55s99s
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mj.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
