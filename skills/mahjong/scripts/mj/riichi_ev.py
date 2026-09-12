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
                if me.riichi or declare:
                    c = 2                      # リーチ
                else:
                    # ダマは「役があるか」で全く別物。役なしはロンできない。
                    # 混ぜて数えると、待ちを広げたのに和了率が下がるという
                    # 一見おかしな表になる（実際そうなった）
                    try:
                        c = 1 if self.dama_ron_value(view, tile) > 0 else 0
                    except Exception:
                        c = 1
                key = (_bin(live, LIVE_BINS),
                       _bin(max(0, 18 - view.turn), TURN_BINS), c)
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

    **最初に書いた検査のうち2つは、私の思い込みだった**:

      「リーチのほうが放銃しやすい（降りられないので）」
        → 実測は逆。待ち6-8枚だと リーチ2.8% / ダマ8.3%。
          リーチは(1)早く和了って局が終わる (2)相手を降ろす
          の2つで、放銃の機会そのものを減らす。検査から外した。

      「待ちが広いほど和了りやすい」
        → ダマを一括りにすると破れた（2-3枚35.3% → 4-5枚29.1%）。
          役あり/役なしに分けたが、役なし側は今度は選択の偏りで
          単調にならない。系統ごとに見るだけでは足りない。

      「役なしダマの和了率は役ありダマより低い」
        → 実測は逆（31.2% 対 22.1%）。役なしダマの局面の90.5%は
          副露手で、その29.0%が和了していた。その時点では和了れない
          はずの手が和了るのは、あとで手が変わって役がついたから。
          状態は終端ではないので、検査として成り立たない。

    **3つのうち2つが、私の思い込みだった。** 不変条件は、それ自体を
    データで検証しないと、間違った前提を固定するだけになる。
    """
    bad = []
    get = lambda a, b, c: tab.get(f"{a},{b},{c}")

    # 1. 待ち0枚では和了れない（どの系統でも）
    for b in range(len(TURN_BINS) - 1):
        for c in (0, 1, 2):
            d = get(0, b, c)
            if d and d["n"] >= 20 and d["win"] > 0:
                bad.append(f"待ち0枚({b},{c}) なのに和了 {d['win']}/{d['n']}")

    # （かつて 2 として「役なしダマの和了率は役ありダマより必ず低い」を
    #  置いていたが、これは誤りだった。実測では逆に出る:
    #    待ち2-3枚 残り6-8巡  役なし 31.2% / 役あり 22.1%
    #  800局で確かめたところ、役なしダマの局面の 90.5% は副露手で、
    #  そのうち 29.0% が和了していた。副露で役なしなら、その時点では
    #  ツモでもロンでも和了れない。それが和了っているのは、
    #  **そのあと手が変わって役がついた** から（鳴きを重ねて対々和・
    #  混一色・役牌が確定する経路）。「あとで曲げたから」ではない
    #  （曲げたのは 1.1% だけ）。
    #
    #  つまり「役なし」はその時点の手の性質でしかなく、状態は終端ではない。
    #  この29%は、そのまま **ダマにしておくと手が変わる価値** の実測値になる。
    #  検査としては成り立たないので外した。）

    # 3. リーチのほうが平均和了点が高い（立直が1翻乗る）
    for a in range(len(LIVE_BINS) - 1):
        for b in range(len(TURN_BINS) - 1):
            x, y = get(a, b, 1), get(a, b, 2)
            if x and y and x["win"] >= 30 and y["win"] >= 30:
                vx, vy = x["wp"] / x["win"], y["wp"] / y["win"]
                if vy < vx:
                    bad.append(
                        f"待ち{a}巡{b}: リーチの平均和了 {vy:.0f} が "
                        f"ダマ役あり {vx:.0f} より低い")

    # 4. 待ちが広いほど和了りやすい（系統ごとに見る）
    for b in range(len(TURN_BINS) - 1):
        for c in (0, 1, 2):
            prev = None
            for a in range(len(LIVE_BINS) - 1):
                d = get(a, b, c)
                if not d or d["n"] < 60:
                    continue
                r = d["win"] / d["n"]
                if prev is not None and r < prev - 0.06:
                    bad.append(f"巡{b}系統{c}: 待ちを広げたのに和了率が下がる "
                               f"({prev:.3f} → {r:.3f})")
                prev = r
    return bad


def show(tab):
    out = []
    out.append(f"{'待ち':>8} {'残り巡':>8} {'':>9} {'件数':>7} {'和了率':>8} "
               f"{'放銃率':>8} {'平均和了':>9} {'平均放銃':>9}")
    out.append("-" * 70)
    for c in (0, 1, 2):
        for a in range(len(LIVE_BINS) - 1):
            for b in range(len(TURN_BINS) - 1):
                d = tab.get(f"{a},{b},{c}")
                if not d or d["n"] < 30:
                    continue
                lv = f"{LIVE_BINS[a]}-{LIVE_BINS[a+1]-1}枚"
                tv = f"{TURN_BINS[b]}-{TURN_BINS[b+1]-1}巡"
                tag = ("ダマ役なし", "ダマ役あり", "リーチ")[c]
                out.append(
                    f"{lv:>8} {tv:>8} {tag:>9} {d['n']:>7} "
                    f"{d['win']/d['n']*100:>7.1f}% {d['deal']/d['n']*100:>7.1f}% "
                    f"{(d['wp']/d['win'] if d['win'] else 0):>9.0f} "
                    f"{(d['dp']/d['deal'] if d['deal'] else 0):>9.0f}")
    return "\n".join(out)


DEFAULT_TABLE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "data", "tenpai_table.json")
_cache = {}


def table(path: str | None = None):
    """同梱の表を読む。measure() で作り直せる。"""
    path = path or DEFAULT_TABLE
    if path not in _cache:
        with open(path, encoding="utf-8") as f:
            _cache[path] = json.load(f)
    return _cache[path]


def advise(live: int, turns_left: int, has_yaku: bool, path: str | None = None):
    """この局面でリーチとダマ、どちらがどれだけ得か。単位は点。

    live       … 待ち牌のうち、**自分から見えていない枚数**
                 （4枚 − 河・副露・自分の手にある枚数）

                 注意: 雀魂の牌譜再生が出す「待ち◯◯ N」の N は
                 **山に残っている枚数**で、相手の手牌にある分は
                 含まない。全知の情報であり、卓上では分からない。
                 別の量なので、そのまま入れてはいけない。
                 実際、この取り違えで実戦の局面を誤って判定した。
    turns_left … 残り巡数（18 − 巡目）
    has_yaku   … ダマのままロンで和了れるか

    役が無ければ、ダマ側は「ロンで取れない手」の実測を使う。
    その系統の和了率には、あとで手が変わって役がついた分が入っている
    （実測で 29%）。それが手変わりの価値にあたる。
    """
    tab = table(path)
    a, b = _bin(live, LIVE_BINS), _bin(max(0, turns_left), TURN_BINS)
    r = _cell(tab, a, b, 2)
    d = _cell(tab, a, b, 1 if has_yaku else 0)

    def _ev(cell, riichi):
        if cell is None:
            return None
        n = cell["n"]
        win = cell["win"] / n * (cell["wp"] / cell["win"] if cell["win"] else 0)
        deal = cell["deal"] / n * (cell["dp"] / cell["deal"] if cell["deal"] else 0)
        return win - deal - (1000 if riichi else 0)

    ev_r, ev_d = _ev(r, True), _ev(d, False)
    if ev_r is None or ev_d is None:
        return None
    return {
        "リーチ": round(ev_r),
        "ダマ": round(ev_d),
        "差": round(ev_r - ev_d),
        "薦め": "リーチ" if ev_r > ev_d else "ダマ",
        "件数": {"リーチ": r["n"], "ダマ": d["n"]},
    }


# ------------------------------------------------------------------ 使う側

def load(path):
    return json.load(open(path))


def _cell(tab, a, b, c, need=40):
    """(待ち, 残り巡, リーチ) の升。薄ければ隣の巡目の升と足す。

    足りない升を勝手な値で埋めない。足りなければ None を返し、
    呼び出し側が「判断材料が無い」と分かるようにする。
    """
    acc = dict(n=0, win=0, deal=0, wp=0, dp=0)
    for bb in (b, b - 1, b + 1):
        d = tab.get(f"{a},{bb},{c}")
        if d:
            for k in acc:
                acc[k] += d[k]
        if acc["n"] >= need:
            break
    return acc if acc["n"] >= need else None


def ev(tab, live: int, turns_left: int, riichi: bool):
    """その状態から局が終わるまでの期待収支（点）。材料が無ければ None。

    和了率 × 平均和了点 − 放銃率 × 平均放銃点 （− リーチ棒）
    """
    a, b = _bin(live, LIVE_BINS), _bin(max(0, turns_left), TURN_BINS)
    d = _cell(tab, a, b, 2 if riichi else 1)
    if d is None:
        return None
    n = d["n"]
    win = d["win"] / n * (d["wp"] / d["win"] if d["win"] else 0)
    deal = d["deal"] / n * (d["dp"] / d["deal"] if d["deal"] else 0)
    return win - deal - (1000 if riichi else 0)


def compare(tab, live: int, turns_left: int):
    """リーチとダマを並べて返す。雀魂の「立直◯◯ / 打牌◯◯」と見比べる用。

    まだ測っていない項は 0 のままにして、勝手な係数を置かない:
      手変わりの価値（ダマ側）… ダマなら待ちを変えられる。未測定
    """
    r = ev(tab, live, turns_left, True)
    d = ev(tab, live, turns_left, False)
    if r is None or d is None:
        return None
    return {
        "リーチ": round(r),
        "ダマ": round(d),
        "差": round(r - d),
        "手変わりの価値": 0,      # 未測定。0 のままにしてある
    }


def check_ev(tab) -> list[str]:
    """期待収支そのものが規則に反していないか。

    表の検査（check）とは別。ここは ev() の出力を見る。
    """
    bad = []
    for b in range(len(TURN_BINS) - 1):
        # 待ち0枚は和了れないので、リーチの期待収支は必ずマイナス
        # （リーチ棒1000点を出して、放銃の危険だけを負う）
        v = ev(tab, 0, TURN_BINS[b], True)
        if v is not None and v > 0:
            bad.append(f"待ち0枚・残り{TURN_BINS[b]}巡 のリーチの期待収支が {v:.0f} 点（正）")
        # 待ちが広いほうが期待収支が高い（同じ巡数・同じリーチ有無）
        for c in (True, False):
            prev = None
            for a in range(len(LIVE_BINS) - 1):
                v = ev(tab, LIVE_BINS[a], TURN_BINS[b], c)
                if v is None:
                    continue
                if prev is not None and v < prev - 800:
                    bad.append(
                        f"残り{TURN_BINS[b]}巡 リーチ{c}: 待ちを広げたのに "
                        f"期待収支が下がる ({prev:.0f} → {v:.0f})")
                prev = v
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hands", type=int, default=1500)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    print(f"{a.hands}局からテンパイ状態の表を作ります…")
    tab = measure(a.hands, a.seed)
    # 印字より先に保存する。前回、印字側の変数名の衝突で
    # 15分ぶんの計算を落とした
    if a.out:
        json.dump(tab, open(a.out, "w"))
        print(f"→ {a.out}")
    print()
    print(show(tab))
    print()
    bad = check(tab)
    if bad:
        print("■ 規則に反している箇所")
        for b in bad:
            print("   " + b)
    else:
        print("■ 表の検査: すべて通過")
    bad2 = check_ev(tab)
    print()
    if bad2:
        print("■ 期待収支の検査で引っかかった箇所")
        for b in bad2:
            print("   " + b)
    else:
        print("■ 期待収支の検査: すべて通過")
    print()
    print("■ リーチとダマの期待収支（点）")
    print(f"  {'待ち':>7} {'残り巡':>7} {'リーチ':>9} {'ダマ':>9} {'差':>9}")
    for i in range(len(LIVE_BINS) - 1):
        for j in range(len(TURN_BINS) - 1):
            cmp = compare(tab, LIVE_BINS[i], TURN_BINS[j])
            if cmp:
                print(f"  {LIVE_BINS[i]:>5}枚 {TURN_BINS[j]:>5}巡 "
                      f"{cmp['リーチ']:>9} {cmp['ダマ']:>9} {cmp['差']:>+9}")



if __name__ == "__main__":
    main()
