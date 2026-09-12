"""オーラスの局面だけを大量に作って、着順条件の判断を直接測る。

半荘を回すとオーラスは11局に1局しか来ない。オーラス限定の直しは
そこで薄まって見えなくなる。ここではオーラスだけを並べる。

  python3 mj/oorasu_lab.py --hands 4000

測るもの:
  判断の食い違い  同じ局面で、旧ロジックと新ロジックのリーチ判断が変わった率
                  （率の直接カウントなのでノイズが無い）
  平均順位        2人ずつ座らせ、席と点棒状況を均等に回して比べる
"""
from __future__ import annotations

import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mj import players as pl  # noqa: E402
from mj.game import Game  # noqa: E402


def make_pair():
    """dama_exact だけが違う2種類。他は全部同じ。"""
    base = dict(
        awareness="allast", allast_conditions=True, low_aggression=0.25,
        top_caution=0.0, riichi_bad_wait_cheap=True, last_place_desperation=0.18,
        reading="tedashi", river_read=True, honitsu_min=11, safety_weight=0.5,
        call_min_value=1500, call_max_shanten=3, push=0.30, value_weight=1.4,
        deep_shape=True, damaten_value=5200,
    )
    old = pl.Player("旧", pl.Style(**base, dama_exact=False))
    new = pl.Player("新", pl.Style(**base, dama_exact=True))
    return old, new


def scores_for(rng):
    """オーラスらしい点棒状況。差がつくように散らす。"""
    raw = [max(1000, int(rng.gauss(25000, 13000))) for _ in range(4)]
    total = sum(raw)
    out = [int(x * 100000 / total / 100) * 100 for x in raw]
    out[0] += 100000 - sum(out)
    return out


def ranks(scores):
    order = sorted(range(4), key=lambda i: (-scores[i], i))
    r = [0] * 4
    for pos, seat in enumerate(order):
        r[seat] = pos + 1
    return r


def run(hands: int, seed: int):
    old, new = make_pair()
    rng = random.Random(seed)

    # 同じ局面で判断が変わる率を数える（率なのでノイズが無い）
    flips = {"n": 0, "diff": 0}
    orig = pl.Player._want_riichi

    def probe(self, view, discard):
        want_new = self.dama_ron_value(view, discard)
        want_old = self.estimate_value(view, dama=True)
        st = self.style
        a = want_old >= st.damaten_value
        b = want_new >= st.damaten_value
        flips["n"] += 1
        if a != b:
            flips["diff"] += 1
        return orig(self, view, discard)

    pl.Player._want_riichi = probe
    agg = {"旧": [0, 0], "新": [0, 0]}   # [順位合計, 局数]
    # 1局ごとの「旧の順位和 − 新の順位和」。同じ局を2人ずつで分けているので
    # 完全なペア比較になり、局ごとの手牌のばらつきが打ち消える
    pair = []
    try:
        for k in range(hands):
            sc = scores_for(rng)
            # 2人ずつ。席と点棒の並びを1局ずつずらして均等にする
            seats = [old, new, old, new] if k % 2 == 0 else [new, old, new, old]
            if (k // 2) % 2:
                seats = seats[2:] + seats[:2]
            g = Game(seats, sc, 28, 3, 0, 0, rng)
            res = g.play()
            after = [p.score for p in g.players]
            if getattr(res, "deltas", None):
                after = [sc[i] + res.deltas[i] for i in range(4)]
            rk = ranks(after)
            sub = {"旧": 0, "新": 0}
            for i, ply in enumerate(seats):
                agg[ply.name][0] += rk[i]
                agg[ply.name][1] += 1
                sub[ply.name] += rk[i]
            pair.append(sub["旧"] - sub["新"])
            if (k + 1) % 1000 == 0:
                print(f"  {k+1}/{hands}", flush=True)
    finally:
        pl.Player._want_riichi = orig
    return agg, flips, pair


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hands", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=17)
    a = ap.parse_args()
    print(f"オーラス {a.hands} 局")
    agg, flips, pair = run(a.hands, a.seed)
    print()
    print(f"リーチ判断 {flips['n']} 回のうち、旧と新で判定が変わったのは "
          f"{flips['diff']} 回 ({flips['diff']/max(1,flips['n'])*100:.1f}%)")
    print()
    for name, (tot, n) in agg.items():
        print(f"  {name}  平均順位 {tot/max(1,n):.4f}   ({n}席)")
    if pair:
        m = sum(pair) / len(pair)
        var = sum((x - m) ** 2 for x in pair) / max(1, len(pair) - 1)
        se = (var / len(pair)) ** 0.5
        print()
        print(f"  1人あたりの差（旧 − 新）: {m/2:+.4f} ± {se/2:.4f}"
              f"   → {abs(m)/se:.1f}SE" if se else "")
        print("  正なら新のほうが着順が良い")


if __name__ == "__main__":
    main()
