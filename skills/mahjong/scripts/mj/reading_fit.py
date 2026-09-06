"""読みのテーブルを作り直すスクリプト。

対局を回して「相手の実際のシャンテン」を記録し、
(副露数 × 巡目 × 直近3打のツモ切り数) ごとのテンパイ率を測って
`reading.py` のテーブルを書き出す。

    python3 skills/mahjong/scripts/mj/reading_fit.py --games 700

AIの打ち方を変えたらテーブルも変わる。ベース戦術をいじったら回し直すこと。
"""

from __future__ import annotations

import argparse
import collections
import os
import pprint
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mj import fast  # noqa: E402
from mj import players as pl  # noqa: E402
from mj.game import Game  # noqa: E402
from mj.reading import turn_bucket  # noqa: E402

SMOOTH = 40  # 事前分布の重み。標本の少ないセルを全体平均に寄せる
MIN_N = 25


def collect(games: int, seed: int):
    rows = []
    orig = pl.Player.discard

    def hook(self, view, forbidden=frozenset()):
        for p in view.game.players:
            if p.riichi:
                continue
            rec = p.tedashi[-3:]
            rows.append(
                (
                    min(p.open_melds, 2),
                    turn_bucket(view.turn),
                    (3 - sum(rec)) if len(rec) == 3 else -1,
                    fast.shanten(p.hand, p.called) == 0,
                )
            )
        return orig(self, view, forbidden)

    pl.Player.discard = hook
    try:
        ai = pl.make_players()
        rng = random.Random(seed)
        scores = [25000] * 4
        for k in range(games):
            Game(ai, scores, 27 + (k // 4) % 2, k % 4, 0, 0, rng).play()
            if (k + 1) % 100 == 0:
                print(f"  {k + 1}/{games} 局", flush=True)
    finally:
        pl.Player.discard = orig
    return rows


def fit(rows):
    prior = sum(r[3] for r in rows) / len(rows)

    def build(keyfn):
        c = collections.defaultdict(lambda: [0, 0])
        for r in rows:
            k = keyfn(r)
            c[k][0] += r[3]
            c[k][1] += 1
        return {
            k: round((h + SMOOTH * prior) / (n + SMOOTH), 3)
            for k, (h, n) in c.items()
            if n >= MIN_N
        }

    return (
        prior,
        build(lambda r: (r[0], r[1], r[2])),
        build(lambda r: (r[0], r[1])),
        build(lambda r: r[0]),
    )


def main():
    ap = argparse.ArgumentParser(description="読みのテーブルを作り直す")
    ap.add_argument("--games", type=int, default=700)
    ap.add_argument("--seed", type=int, default=4649)
    ap.add_argument("--out", default=None, help="書き出し先（省略時は標準出力）")
    args = ap.parse_args()

    rows = collect(args.games, args.seed)
    prior, full, mt, m = fit(rows)
    body = (
        f"PRIOR = {prior:.3f}\n\n"
        f"TENPAI_FULL = {pprint.pformat(full, width=96)}\n\n"
        f"TENPAI_MT = {pprint.pformat(mt, width=96)}\n\n"
        f"TENPAI_M = {pprint.pformat(m, width=96)}\n"
    )
    print(f"\n標本 {len(rows):,} 点 / 全体テンパイ率 {prior:.3f} / セル数 {len(full)}")
    if args.out:
        with open(args.out, "w") as f:
            f.write(body)
        print(f"書き出し: {args.out}")
    else:
        print(body)


if __name__ == "__main__":
    main()
