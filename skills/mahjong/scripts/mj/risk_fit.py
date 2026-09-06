"""危険度（wait_risk）の当たり具合を、シミュレータの正解に対して測る。

打牌のたびに、テンパイしている相手の**本当の待ち**を記録して、
`reading.wait_risk` の見積もりと突き合わせる。

    python3 skills/mahjong/scripts/mj/risk_fit.py --games 300

出るもの:
  AUC     … 「当たり牌のほうが危険と言えているか」の順位付け能力（0.5＝でたらめ）
  実測率  … 予測の帯ごとの本当の当たり牌率。較正が合っているか
  枚数別  … その牌が場に何枚見えているかで、当たり牌率がどう変わるか
"""

from __future__ import annotations

import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mj import fast  # noqa: E402
from mj import players as pl  # noqa: E402
from mj import reading  # noqa: E402
from mj.game import Game  # noqa: E402
from mj.tiles import HONOR, NUM_TILES  # noqa: E402


def winning_tiles(p) -> set:
    out = set()
    for t in range(NUM_TILES):
        if p.hand[t] >= 4:
            continue
        p.hand[t] += 1
        if fast.shanten(p.hand, p.called) < 0:
            out.add(t)
        p.hand[t] -= 1
    return out


# 「枚数を見ない」旧モデル。同じ局面で新旧を比べるために使う
OLD_SEEN = (1.0, 1.0, 1.0, 1.0)
OLD_HONOR_SEEN = (1.0, 0.5, 0.5, 0.5)


def _old_risk(p, t, seen, mine):
    sf, hf = reading.SEEN_FACTOR, reading.HONOR_SEEN_FACTOR
    reading.SEEN_FACTOR, reading.HONOR_SEEN_FACTOR = OLD_SEEN, OLD_HONOR_SEEN
    try:
        return reading.wait_risk(p, t, seen, mine)
    finally:
        reading.SEEN_FACTOR, reading.HONOR_SEEN_FACTOR = sf, hf


def collect(games: int, seed: int, min_turn: int = 6):
    rows = []
    orig = pl.Player.discard

    def hook(self, view, forbidden=frozenset()):
        if view.turn >= min_turn:
            me = view.me
            seen = view.seen_all()
            for p in view.others:
                if fast.shanten(p.hand, p.called) != 0:
                    continue
                win = winning_tiles(p)
                if not win:
                    continue
                for t in range(NUM_TILES):
                    if not me.hand[t]:
                        continue
                    risk = reading.wait_risk(p, t, seen, me.hand)
                    # その相手の河にある牌（現物）は判断が自明なので外す
                    if p.river_counts[t]:
                        continue
                    elsewhere = seen[t] - me.hand[t] - p.river_counts[t]
                    rows.append((risk, t in win, min(3, max(0, elsewhere)), t,
                                 _old_risk(p, t, seen, me.hand)))
        return orig(self, view, forbidden)

    pl.Player.discard = hook
    try:
        ai = pl.make_players()
        rng = random.Random(seed)
        for k in range(games):
            Game(ai, [25000] * 4, 27 + (k // 4) % 2, k % 4, 0, 0, rng).play()
            if (k + 1) % 100 == 0:
                print(f"  {k + 1}/{games} 局", flush=True)
    finally:
        pl.Player.discard = orig
    return rows


def auc(rows) -> float:
    """Mann-Whitney の U から。同点は0.5として数える。"""
    data = sorted((r[0], r[1]) for r in rows)
    pos = sum(1 for r in rows if r[1])
    neg = len(rows) - pos
    if not pos or not neg:
        return 0.5
    rank_sum = 0.0
    i = 0
    while i < len(data):
        j = i
        while j < len(data) and data[j][0] == data[i][0]:
            j += 1
        avg_rank = (i + j + 1) / 2  # 1始まりの平均順位
        rank_sum += avg_rank * sum(1 for k in range(i, j) if data[k][1])
        i = j
    return (rank_sum - pos * (pos + 1) / 2) / (pos * neg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=300)
    ap.add_argument("--seed", type=int, default=13)
    a = ap.parse_args()

    rows = collect(a.games, a.seed)
    hit = sum(1 for r in rows if r[1])
    print(f"\n標本 {len(rows)} 件 / 当たり牌 {hit} 件 ({hit / len(rows) * 100:.2f}%)")
    old = [(r[4], r[1]) for r in rows]
    print(f"AUC  枚数を見る {auc(rows):.4f}  /  見ない(旧) {auc(old):.4f}\n")

    print("  予測の帯ごとの実測")
    print(f"  {'予測(%)':>10} {'標本':>8} {'実測(%)':>9}")
    bands = [(0, 2), (2, 4), (4, 6), (6, 8), (8, 11), (11, 100)]
    for lo, hi in bands:
        sub = [r for r in rows if lo <= r[0] < hi]
        if not sub:
            continue
        print(f"  {lo:>4}-{hi:<5} {len(sub):>8} "
              f"{sum(1 for r in sub if r[1]) / len(sub) * 100:>8.2f}")

    print("\n  その牌が他で何枚見えているかで、当たり牌率がどう変わるか")
    print(f"  {'見えている':>10} {'標本':>8} {'実測(%)':>9} {'予測(%)':>9}")
    for n in range(4):
        sub = [r for r in rows if r[2] == n]
        if not sub:
            continue
        print(f"  {n:>10} {len(sub):>8} "
              f"{sum(1 for r in sub if r[1]) / len(sub) * 100:>8.2f} "
              f"{sum(r[0] for r in sub) / len(sub):>8.2f}")

    print("\n  数牌／字牌べつ（見えている枚数ごと）")
    for label, pred in (("数牌", lambda t: t < HONOR), ("字牌", lambda t: t >= HONOR)):
        for n in range(4):
            sub = [r for r in rows if r[2] == n and pred(r[3])]
            if len(sub) < 200:
                continue
            print(f"  {label} {n}枚見え {len(sub):>7} 件  "
                  f"実測 {sum(1 for r in sub if r[1]) / len(sub) * 100:>5.2f}%")


if __name__ == "__main__":
    main()
