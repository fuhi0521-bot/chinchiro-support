"""判断のコードで、一度も通っていない行を出す。

局数を重ねても、そこを通るエージェントがいなければバグは見つからない。
実際、ダマ判定の欠陥は damaten_value=5200 のゆみこがいたから見えた。
かなめ（12000）だけならリーチ判断665回のうち2回しか通らない分岐だった。

  python3 mj/coverage_probe.py --hands 400 --lineup named
  python3 mj/coverage_probe.py --hands 400 --lineup probe   # 極端な4人

通っていない行が、次にバグが潜んでいる場所。
"""
from __future__ import annotations

import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TARGETS = ["mj/players.py", "mj/reading.py", "mj/wall.py", "mj/safety.py"]


def run(hands: int, lineup: str, seed: int, awareness: str):
    import coverage

    cov = coverage.Coverage(include=[f"*/{t}" for t in TARGETS], branch=True)
    cov.start()
    from mj.game import Game
    from mj.simulate import build_lineup

    ai = build_lineup(lineup, awareness)
    rng = random.Random(seed)
    for k in range(hands):
        Game(ai, [25000] * 4, 27 + (k // 4) % 2, k % 4, 0, 0, rng).play()
    cov.stop()
    return cov


def report(cov, src_root: str):
    import io

    out = {}
    data = cov.get_data()
    for path in data.measured_files():
        rel = os.path.relpath(path, src_root)
        if rel.replace(os.sep, "/") not in TARGETS:
            continue
        an = cov.analysis2(path)
        _, statements, _, missing, _ = an
        out[rel] = (len(statements), sorted(missing))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hands", type=int, default=400)
    ap.add_argument("--lineup", default="named")
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--awareness", default="allast")
    ap.add_argument("--show", type=int, default=18, help="未実行行を何行まで出すか")
    a = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cov = run(a.hands, a.lineup, a.seed, a.awareness)
    res = report(cov, root)
    print(f"{a.hands}局 / lineup={a.lineup}\n")
    for rel, (n, missing) in sorted(res.items()):
        hit = n - len(missing)
        print(f"{rel}: {hit}/{n} 行を実行 ({hit/n*100:.1f}%)  未実行 {len(missing)}行")
    print()
    src = {}
    for rel, (n, missing) in sorted(res.items()):
        if not missing:
            continue
        lines = open(os.path.join(root, rel), encoding="utf-8").read().splitlines()
        print(f"■ {rel} の未実行行（先頭{a.show}件）")
        for ln in missing[: a.show]:
            text = lines[ln - 1].strip() if ln - 1 < len(lines) else ""
            print(f"   {ln:>5}: {text[:96]}")
        print()


if __name__ == "__main__":
    main()
