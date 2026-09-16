"""待ちの価値を「ツモ」と「ロン」に分けて測る。

山読みを素直に入れたら和了率が下がった（`results/experiment-wall.md`）。
原因は **山に濃い牌は誰も持っていないので出てこない** こと。
つまり待ちの価値は2つの量の足し算で、片方だけ最大化すると損をする。

    待ちの価値 = ツモの見込み（山にある枚数）+ ロンの見込み（相手が持っていて、かつ切る）

ここでは実際の対局で
「テンパイした時点の待ち牌ごとの 山にある枚数 / 相手が持っている枚数」と
「その牌で実際にツモったか・ロンしたか」を突き合わせて、
2つの係数を測る。

    python3 skills/mahjong/scripts/mj/wait_fit.py --games 300
"""

from __future__ import annotations

import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mj import fast  # noqa: E402
from mj import players as pl  # noqa: E402
from mj import wall as W  # noqa: E402
from mj.game import Game  # noqa: E402
from mj.tiles import HONOR, NUM_TILES  # noqa: E402


def _waits(p):
    out = []
    for t in range(NUM_TILES):
        if p.hand[t] >= 4:
            continue
        p.hand[t] += 1
        if fast.shanten(p.hand, p.called) < 0:
            out.append(t)
        p.hand[t] -= 1
    return out


def _cls(t):
    if t >= HONOR:
        return "字牌"
    r = t % 9 + 1
    return {1: "1・9", 9: "1・9", 2: "2・8", 8: "2・8",
            3: "3・7", 7: "3・7", 4: "4・6", 6: "4・6", 5: "5"}[r]


def collect(games: int, seed: int, turn_at: int = 9):
    """各局・各プレイヤーについて、テンパイした最初の局面を1つだけ記録する。

    同じ局から何度も取ると相関してしまうので、1局1人1件に絞る。
    """
    rows = []
    orig = pl.Player.discard
    state = {}

    def hook(self, view, forbidden=frozenset()):
        g = view.game
        me = view.me
        key = (id(g), me.seat)
        if key not in state and view.turn >= 4:
            if fast.shanten(me.hand, me.called) == 0:
                w = _waits(me)
                if w:
                    seen = view.seen_all()
                    wc = W.wall_counts(view, seen)
                    unseen = [4 - seen[t] for t in range(NUM_TILES)]
                    state[key] = {
                        "seat": me.seat,
                        "waits": w,
                        "wall": {t: wc[t] for t in w},
                        "held": {t: max(0.0, unseen[t] - wc[t]) for t in w},
                        "turn": view.turn,
                        "menzen": me.menzen,
                    }
        return orig(self, view, forbidden)

    pl.Player.discard = hook
    try:
        ai = pl.make_players()
        rng = random.Random(seed)
        for k in range(games):
            g = Game(ai, [25000] * 4, 27 + (k // 4) % 2, k % 4, 0, 0, rng)
            res = g.play()
            won = {}
            for seat, _pts, _h, _f, _y in res.winners:
                # 和了牌は res には入っていないので、手牌から復元する
                won[seat] = res.kind  # "tsumo" / "ron"
            for (gid, seat), st in list(state.items()):
                if gid != id(g):
                    continue
                st["result"] = won.get(seat)
                rows.append(st)
                del state[(gid, seat)]
            state.clear()
            if (k + 1) % 100 == 0:
                print(f"  {k + 1}/{games} 局", flush=True)
    finally:
        pl.Player.discard = orig
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=300)
    ap.add_argument("--seed", type=int, default=17)
    a = ap.parse_args()

    rows = collect(a.games, a.seed)
    n = len(rows)
    tsumo = sum(1 for r in rows if r["result"] == "tsumo")
    ron = sum(1 for r in rows if r["result"] == "ron")
    print(f"\nテンパイ局面 {n} 件 / ツモ {tsumo} ({tsumo/n*100:.1f}%)"
          f" / ロン {ron} ({ron/n*100:.1f}%)")

    # 待ちの「山にある枚数」「相手が持っている枚数」で分けて和了率を見る
    def bucket(key, edges):
        out = {}
        for r in rows:
            v = sum(r[key].values())
            b = 0
            while b < len(edges) and v >= edges[b]:
                b += 1
            out.setdefault(b, []).append(r)
        return out

    for key, label, edges in (("wall", "山にある枚数", (1.0, 2.0, 3.0)),
                              ("held", "相手が持っている枚数", (1.0, 2.0, 3.0))):
        print(f"\n  待ちの{label}ごと")
        print(f"  {'帯':>10} {'標本':>7} {'ツモ率':>8} {'ロン率':>8} {'和了率':>8}")
        b = bucket(key, edges)
        names = ["〜1.0", "1.0〜2.0", "2.0〜3.0", "3.0〜"]
        for i in sorted(b):
            sub = b[i]
            if len(sub) < 30:
                continue
            t = sum(1 for r in sub if r["result"] == "tsumo")
            rr = sum(1 for r in sub if r["result"] == "ron")
            print(f"  {names[i]:>10} {len(sub):>7} {t/len(sub)*100:>7.1f}%"
                  f" {rr/len(sub)*100:>7.1f}% {(t+rr)/len(sub)*100:>7.1f}%")

    # 待ち牌の種類ごと
    print("\n  待ちに含まれる牌の種類ごと（その種類を含む待ちの和了内訳）")
    print(f"  {'種類':>6} {'標本':>7} {'ツモ率':>8} {'ロン率':>8}")
    for cname in ("1・9", "2・8", "3・7", "4・6", "5", "字牌"):
        sub = [r for r in rows if any(_cls(t) == cname for t in r["waits"])]
        if len(sub) < 30:
            continue
        t = sum(1 for r in sub if r["result"] == "tsumo")
        rr = sum(1 for r in sub if r["result"] == "ron")
        print(f"  {cname:>6} {len(sub):>7} {t/len(sub)*100:>7.1f}% {rr/len(sub)*100:>7.1f}%")


if __name__ == "__main__":
    main()
