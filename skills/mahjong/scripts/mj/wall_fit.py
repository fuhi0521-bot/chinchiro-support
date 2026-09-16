"""山読みの当たり具合を、シミュレータの正解に対して測る。

対局を回し、打牌を決める瞬間ごとに
「その牌が実際に山＋王牌に何枚あるか」を記録して、
mj/wall.py の見積もりと比べる。

    python3 skills/mahjong/scripts/mj/wall_fit.py --games 400

比較の相手は「均等割り」— 見えていない枚数を、相手の手と山に
牌の種類に関係なく同じ比率で割り振るやり方。受け入れ計算が
暗黙にやっているのがこれなので、これを超えられなければ意味がない。
"""

from __future__ import annotations

import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mj import players as pl  # noqa: E402
from mj import wall as W  # noqa: E402
from mj.game import Game  # noqa: E402
from mj.tiles import NUM_TILES  # noqa: E402


def collect(games: int, seed: int, sample_every: int = 3):
    """(予測, 均等割り, 正解) の三つ組を集める。"""
    rows = []
    orig = pl.Player.discard
    counter = [0]

    def hook(self, view, forbidden=frozenset()):
        counter[0] += 1
        if counter[0] % sample_every == 0 and view.turn >= 3:
            g = view.game
            actual = [0] * NUM_TILES
            for t, _ in g.live:
                actual[t] += 1
            for t, _ in g.dead[g.rinshan_taken:]:
                actual[t] += 1
            for i in g.dora_indicators:
                actual[i] -= 1        # ドラ表示牌は見えているので山から除く
            seen = view.seen_all()
            unseen = [4 - seen[t] for t in range(NUM_TILES)]
            total = sum(unseen)
            hidden = min(sum(sum(p.hand) for p in view.others), total)
            flat = (1 - hidden / total) if total else 0.0
            pred = W.wall_counts(view, seen)
            for t in range(NUM_TILES):
                if unseen[t] <= 0:
                    continue
                rows.append((pred[t], unseen[t] * flat, float(actual[t]), unseen[t], t))
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


def rmse(pairs):
    return (sum((a - b) ** 2 for a, b in pairs) / len(pairs)) ** 0.5


def pair_accuracy(rows, sample=400_000, seed=7):
    """「同じ見た目の残り枚数」の2牌を比べて、山に多いほうを当てられるか。

    受け入れ計算では区別が付かない組だけを取り出す。ここで五分より
    上なら、山読みは「枚数だけでは見えない差」を掴んでいることになる。
    """
    rng = random.Random(seed)
    by_unseen = {}
    for pred, flat, actual, unseen, _t in rows:
        by_unseen.setdefault(unseen, []).append((pred, actual))
    hit = tie = n = 0
    keys = [k for k, v in by_unseen.items() if len(v) > 1]
    if not keys:
        return 0.0, 0
    for _ in range(sample):
        v = by_unseen[rng.choice(keys)]
        a = rng.choice(v)
        b = rng.choice(v)
        if a[1] == b[1]:
            continue
        n += 1
        if (a[0] - b[0]) * (a[1] - b[1]) > 0:
            hit += 1
        elif a[0] == b[0]:
            tie += 1
    return (hit + tie / 2) / n if n else 0.0, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=400)
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()

    rows = collect(a.games, a.seed)
    print(f"\n標本 {len(rows)} 件（{a.games} 局）\n")
    model = rmse([(r[0], r[2]) for r in rows])
    flat = rmse([(r[1], r[2]) for r in rows])
    print(f"  誤差(RMSE)  山読み {model:.4f}  /  均等割り {flat:.4f}  "
          f"（{(flat - model) / flat * 100:+.1f}%）")
    acc, n = pair_accuracy(rows)
    print(f"  同枚数の2牌でどちらが山に濃いか: {acc * 100:.1f}%  （{n} 組, 五分=50%）")

    # 牌の種類ごと: 「見えていない1枚が、実際に山にある確率」
    from mj.tiles import HONOR
    print("\n  牌の種類ごと（見えていない1枚が山にある確率）")
    print(f"  {'種類':<6} {'標本':>8} {'実際':>7} {'山読み':>8} {'均等割り':>9}")
    buckets = {}
    for pred, flat, actual, unseen, t in rows:
        if t >= HONOR:
            k = "字牌"
        else:
            r = t % 9 + 1
            k = str(min(r, 10 - r))
        b = buckets.setdefault(k, [0.0, 0.0, 0, 0.0])
        b[0] += actual
        b[1] += flat
        b[2] += unseen
        b[3] += pred
    for k in ["1", "2", "3", "4", "5", "字牌"]:
        if k not in buckets:
            continue
        a, f, u, pr = buckets[k]
        label = {"1": "1・9", "2": "2・8", "3": "3・7", "4": "4・6", "5": "5"}.get(k, k)
        print(f"  {label:<6} {int(u):>8} {a / u * 100:>6.1f}% {pr / u * 100:>7.1f}%"
              f" {f / u * 100:>8.1f}%")

    # 見えている枚数ごとの内訳
    print("\n  見えている枚数ごと")
    print(f"  {'残り':>4} {'標本':>8} {'実際の平均':>10} {'山読み':>8} {'均等割り':>9}")
    for u in (1, 2, 3, 4):
        sub = [r for r in rows if r[3] == u]
        if not sub:
            continue
        print(f"  {u:>4} {len(sub):>8} {sum(r[2] for r in sub) / len(sub):>10.2f}"
              f" {sum(r[0] for r in sub) / len(sub):>8.2f}"
              f" {sum(r[1] for r in sub) / len(sub):>9.2f}")


if __name__ == "__main__":
    main()
