"""リーチとダマを、同じ物差し（この局の期待収支）で比べる。

いまの判断は「ダマの打点が閾値を超えるか」という二値だった。
それだと次の3つが表現できない:

  1. リーチすると降りられなくなる損失
     実戦の牌譜で、9巡目に曲げ、11巡目に待ちが枯れ、13巡目に
     ツモ切り強制で混一色に3900放銃した局があった。
  2. ダマなら手を変えられる価値
     同じ牌譜で、ダマにしたことで嵌張1種4枚が5面待ち15枚に伸びていた。
  3. どれくらい差があるか
     雀魂は「立直53 対 ダマ37」と点で出す。二値では並べて比べられない。

■ 係数を決め打ちしない

この題材では平均順位で係数の良し悪しを判定できない（同型2人が
6000半荘で0.018離れ、2SEの結果が3回とも裏切られた）。
なので **各項をシミュレータの実測から作る**。
`measure()` が表を作り、`score()` がそれを使う。

■ 規則で検査できるようにする

表ができたら `check()` で不変条件を確かめる。壊れた値を返していないか
は、勝率を測らなくても分かる。ダマ打点の44.7%の誤りを見逃したのは、
値の意味が曖昧で、こういう検査が書けなかったから。
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mj import fast  # noqa: E402
from mj import players as pl  # noqa: E402
from mj.game import Game  # noqa: E402

# 待ち枚数の区切り。0枚は「絶対に和了れない」ので必ず独立させる
LIVE_BINS = [0, 1, 2, 4, 6, 9, 99]
# 残り巡数の区切り
TURN_BINS = [0, 3, 6, 9, 12, 15, 99]


def _bin(v, bins):
    for i in range(len(bins) - 1):
        if bins[i] <= v < bins[i + 1]:
            return i
    return len(bins) - 2


def measure(hands: int, seed: int, lineup: str = "named", awareness: str = "allast"):
    """テンパイ状態から、その局がどう終わったかを数える。

    (待ち枚数, 残り巡数, リーチか) ごとに
      和了率 / 放銃率 / 平均和了点 / 平均放銃点
    を出す。これが期待収支の材料になる。
    """
    from mj.simulate import build_lineup

    ai = build_lineup(lineup, awareness)
    tab = collections.defaultdict(lambda: dict(n=0, win=0, deal=0, wp=0, dp=0))
    states = {}          # seat -> [(key, ...), ...] この局に通った状態
    orig = pl.Player.discard

    def hook(self, view, forbidden=frozenset()):
        tile, declare = orig(self, view, forbidden)
        me = view.me
        me.hand[tile] -= 1
        try:
            s, acc = fast.ukeire(me.hand, me.called, view.visible())
            if s == 0:
                live = sum(n for _, n in acc)
                key = (_bin(live, LIVE_BINS),
                       _bin(max(0, 18 - view.turn), TURN_BINS),
                       1 if me.riichi or declare else 0)
                states.setdefault(view.seat, set()).add(key)
        finally:
            me.hand[tile] += 1
        return tile, declare

    pl.Player.discard = hook
    try:
        rng = random.Random(seed)
        for k in range(hands):
            states.clear()
            g = Game(ai, [25000] * 4, 27 + (k // 4) % 2, k % 4, 0, 0, rng)
            res = g.play()
            won = {w[0]: w[1] for w in (res.winners or [])}
            loser = res.loser
            for seat, keys in states.items():
                for key in keys:
                    d = tab[key]
                    d["n"] += 1
                    if seat in won:
                        d["win"] += 1
                        d["wp"] += won[seat]
                    elif res.kind == "ron" and seat == loser:
                        d["deal"] += 1
                        d["dp"] += abs(res.deltas[seat]) if res.deltas else 0
            if (k + 1) % 200 == 0:
                print(f"  {k+1}/{hands}", flush=True)
    finally:
        pl.Player.discard = orig
    return {f"{a},{b},{c}": v for (a, b, c), v in tab.items()}


def check(tab) -> list[str]:
    """規則として成り立っていないといけないことを確かめる。

    順位を測らなくても、ここが破れていればその表は間違っている。
    """
    bad = []
    get = lambda a, b, c: tab.get(f"{a},{b},{c}")

    # 1. 待ち0枚では和了れない
    for b in range(len(TURN_BINS) - 1):
        for c in (0, 1):
            d = get(0, b, c)
            if d and d["n"] >= 20 and d["win"] > 0:
                bad.append(f"待ち0枚({b},{c}) なのに和了 {d['win']}/{d['n']}")

    # 2. リーチのほうが放銃しやすい（降りられないので）
    for a in range(len(LIVE_BINS) - 1):
        for b in range(len(TURN_BINS) - 1):
            x, y = get(a, b, 0), get(a, b, 1)
            if x and y and x["n"] >= 60 and y["n"] >= 60:
                rx, ry = x["deal"] / x["n"], y["deal"] / y["n"]
                if ry < rx - 0.05:
                    bad.append(
                        f"待ち{a}巡{b}: リーチの放銃率 {ry:.3f} が "
                        f"ダマ {rx:.3f} より 0.05 以上低い")

    # 3. リーチのほうが打点が高い（立直が1翻乗る）
    for a in range(len(LIVE_BINS) - 1):
        for b in range(len(TURN_BINS) - 1):
            x, y = get(a, b, 0), get(a, b, 1)
            if x and y and x["win"] >= 30 and y["win"] >= 30:
                vx, vy = x["wp"] / x["win"], y["wp"] / y["win"]
                if vy < vx:
                    bad.append(
                        f"待ち{a}巡{b}: リーチの平均和了 {vy:.0f} が "
                        f"ダマ {vx:.0f} より低い")

    # 4. 待ちが広いほど和了りやすい（同じ巡数・同じリーチ有無で単調）
    for b in range(len(TURN_BINS) - 1):
        for c in (0, 1):
            prev = None
            for a in range(len(LIVE_BINS) - 1):
                d = get(a, b, c)
                if not d or d["n"] < 60:
                    continue
                r = d["win"] / d["n"]
                if prev is not None and r < prev - 0.06:
                    bad.append(f"巡{b}リーチ{c}: 待ちを広げたのに和了率が下がる "
                               f"({prev:.3f} → {r:.3f})")
                prev = r
    return bad


def show(tab):
    out = []
    out.append(f"{'待ち':>8} {'残り巡':>8} {'':>4} {'件数':>7} {'和了率':>8} "
               f"{'放銃率':>8} {'平均和了':>9} {'平均放銃':>9}")
    out.append("-" * 70)
    for c in (0, 1):
        for a in range(len(LIVE_BINS) - 1):
            for b in range(len(TURN_BINS) - 1):
                d = tab.get(f"{a},{b},{c}")
                if not d or d["n"] < 30:
                    continue
                lv = f"{LIVE_BINS[a]}-{LIVE_BINS[a+1]-1}枚"
                tv = f"{TURN_BINS[b]}-{TURN_BINS[b+1]-1}巡"
                tag = "リーチ" if c else "ダマ"
                out.append(
                    f"{lv:>8} {tv:>8} {tag:>4} {d['n']:>7} "
                    f"{d['win']/d['n']*100:>7.1f}% {d['deal']/d['n']*100:>7.1f}% "
                    f"{(d['wp']/d['win'] if d['win'] else 0):>9.0f} "
                    f"{(d['dp']/d['deal'] if d['deal'] else 0):>9.0f}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hands", type=int, default=1500)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    print(f"{a.hands}局からテンパイ状態の表を作ります…")
    tab = measure(a.hands, a.seed)
    print()
    print(show(tab))
    print()
    bad = check(tab)
    if bad:
        print("■ 規則に反している箇所")
        for b in bad:
            print("   " + b)
    else:
        print("■ 規則の検査: すべて通過")
    if a.out:
        json.dump(tab, open(a.out, "w"))
        print(f"\n→ {a.out}")


if __name__ == "__main__":
    main()
