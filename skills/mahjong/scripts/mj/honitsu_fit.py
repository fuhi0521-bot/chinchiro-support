"""染め手の相手に対して、危険度の読みがどれだけ外れているかを測る。

以前 references/reading.md に

    「1色に寄った鳴きでも、テンパイ時の待ちの76〜80%は他の色だった」

と書いたが、これは **「鳴きがたまたま1色に寄っている」を染め手とみなしていた**
可能性がある。ふつうのタンヤオでも鳴きが1色に寄ることはある。

ここでは染め手の判定を厳しくして測り直す。

  ゆるい判定 : 副露2つ以上が「1色＋字牌」に収まっている
  厳しい判定 : ゆるい判定 ＋ 中盤以降に他の色を手出しで切っている
               （＝その色を集めていることが河に出ている）

    python3 skills/mahjong/scripts/mj/honitsu_fit.py --games 300
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

EARLY = 6   # 「中盤以降」の境目

# 手役読みを切ったモデル（比較用）
OFF = dict(HONITSU_IN=1.0, HONITSU_HONOR=1.0, HONITSU_OUT=1.0,
           TOITOI_SUJI=reading.SUJI_FACTOR, TOITOI_HONOR=1.0)


def _risk_off(p, t, seen, mine):
    saved = {k: getattr(reading, k) for k in OFF}
    for k, v in OFF.items():
        setattr(reading, k, v)
    try:
        return reading.wait_risk(p, t, seen, mine)
    finally:
        for k, v in saved.items():
            setattr(reading, k, v)


def meld_suit(p):
    """副露が『1色＋字牌』に収まっていれば、その色を返す。無ければ None。"""
    if not p.melds:
        return None
    suits = set()
    for m in p.melds:
        for t in m.tiles:
            if t < HONOR:
                suits.add(t // 9)
    if len(suits) != 1:
        return None
    return suits.pop()


def classify(p):
    """(ゆるい判定, 厳しい判定) を返す。値は色 or None。"""
    s = meld_suit(p)
    if s is None or len(p.melds) < 2:
        return None, None
    # 中盤以降に他の色を手出しで切っているか
    others = 0
    for i, t in enumerate(p.river):
        if i < EARLY or i >= len(p.tedashi) or not p.tedashi[i]:
            continue
        if t < HONOR and t // 9 != s:
            others += 1
    return s, (s if others >= 2 else None)


def winning_tiles(p):
    out = set()
    for t in range(NUM_TILES):
        if p.hand[t] >= 4:
            continue
        p.hand[t] += 1
        if fast.shanten(p.hand, p.called) < 0:
            out.add(t)
        p.hand[t] -= 1
    return out


def collect(games: int, seed: int, lineup: str = "named"):
    rows = []
    orig = pl.Player.discard

    def hook(self, view, forbidden=frozenset()):
        if view.turn >= 6:
            me = view.me
            seen = view.seen_all()
            for p in view.others:
                if fast.shanten(p.hand, p.called) != 0:
                    continue
                win = winning_tiles(p)
                if not win:
                    continue
                loose, strict = classify(p)
                # 待ちの内訳
                in_suit = sum(1 for t in win
                              if loose is not None and t < HONOR and t // 9 == loose)
                honor = sum(1 for t in win if t >= HONOR)
                rows.append({
                    "loose": loose, "strict": strict,
                    "waits": len(win), "in_suit": in_suit, "honor": honor,
                    "melds": p.open_melds,
                    # 危険度の読みが当たっているか（自分の手牌の候補で見る）
                    "risk": [(reading.wait_risk(p, t, seen, me.hand), t in win, t,
                              _risk_off(p, t, seen, me.hand))
                             for t in range(NUM_TILES) if me.hand[t]
                             and not p.river_counts[t]],
                })
        return orig(self, view, forbidden)

    pl.Player.discard = hook
    try:
        from mj.simulate import build_lineup
        ai = build_lineup(lineup)
        rng = random.Random(seed)
        for k in range(games):
            Game(ai, [25000] * 4, 27 + (k // 4) % 2, k % 4, 0, 0, rng).play()
            if (k + 1) % 100 == 0:
                print(f"  {k + 1}/{games} 局", flush=True)
    finally:
        pl.Player.discard = orig
    return rows


def auc(pairs):
    data = sorted(pairs)
    pos = sum(1 for _, y in pairs if y)
    neg = len(pairs) - pos
    if not pos or not neg:
        return 0.5
    rs = 0.0
    i = 0
    while i < len(data):
        j = i
        while j < len(data) and data[j][0] == data[i][0]:
            j += 1
        avg = (i + j + 1) / 2
        rs += avg * sum(1 for k in range(i, j) if data[k][1])
        i = j
    return (rs - pos * (pos + 1) / 2) / (pos * neg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=300)
    ap.add_argument("--seed", type=int, default=23)
    ap.add_argument("--lineup", default="named",
                    help="honitsu-field を指定すると染め手が頻繁に出る場で測る")
    a = ap.parse_args()
    rows = collect(a.games, a.seed, a.lineup)
    print(f"\nテンパイしている相手の局面 {len(rows)} 件\n")

    groups = {
        "染めでない（鳴きあり）": [r for r in rows if r["melds"] and r["loose"] is None],
        "ゆるい判定（副露2+が1色）": [r for r in rows if r["loose"] is not None],
        "厳しい判定（＋他色を手出し）": [r for r in rows if r["strict"] is not None],
    }
    print("■ テンパイ時の待ちの内訳")
    print(f"  {'条件':<26} {'標本':>7} {'その色':>8} {'字牌':>8} {'その色+字牌':>11}")
    for label, sub in groups.items():
        if len(sub) < 20:
            print(f"  {label:<26} {len(sub):>7}  （標本不足）")
            continue
        w = sum(r["waits"] for r in sub)
        s = sum(r["in_suit"] for r in sub)
        h = sum(r["honor"] for r in sub)
        if label == "染めでない（鳴きあり）":
            print(f"  {label:<26} {len(sub):>7} {'—':>8} {h / w * 100:>7.1f}% {'—':>11}")
        else:
            print(f"  {label:<26} {len(sub):>7} {s / w * 100:>7.1f}% {h / w * 100:>7.1f}%"
                  f" {(s + h) / w * 100:>10.1f}%")

    print("\n■ 危険度の読みが当たっているか（AUC / 五分=0.5）")
    print(f"  {'条件':<26} {'標本':>8} {'当たり牌率':>10} {'手役読みあり':>12} {'なし':>8}")
    allrows = [("全体", rows)] + list(groups.items())
    for label, sub in allrows:
        pairs = [(x[0], x[1]) for r in sub for x in r["risk"]]
        off = [(x[3], x[1]) for r in sub for x in r["risk"]]
        if len(pairs) < 200:
            continue
        hit = sum(1 for _, y in pairs if y)
        print(f"  {label:<26} {len(pairs):>8} {hit / len(pairs) * 100:>9.2f}%"
              f" {auc(pairs):>11.4f} {auc(off):>8.4f}")

    print("\n■ 染め手の相手に対する、牌の種類ごとの当たり牌率と予測")
    sub = groups["ゆるい判定（副露2+が1色）"]
    if len(sub) >= 20:
        cats = {"その色": [], "他の色": [], "字牌": []}
        for r in sub:
            s = r["loose"]
            for risk, hit, t, off in r["risk"]:
                if t >= HONOR:
                    cats["字牌"].append((risk, hit, off))
                elif t // 9 == s:
                    cats["その色"].append((risk, hit, off))
                else:
                    cats["他の色"].append((risk, hit, off))
        print(f"  {'種類':<8} {'標本':>8} {'実測':>8} {'手役読みあり':>12} "
              f"{'なし(素)':>10} {'必要な倍率':>11}")
        for k, v in cats.items():
            if len(v) < 40:
                continue
            act = sum(1 for _, y, _o in v if y) / len(v) * 100
            on = sum(r for r, _, _o in v) / len(v)
            off = sum(o for _, _, o in v) / len(v)
            need = act / off if off else float("nan")
            print(f"  {k:<8} {len(v):>8} {act:>7.2f}% {on:>11.2f}%"
                  f" {off:>9.2f}% {need:>10.2f}x")


if __name__ == "__main__":
    main()
