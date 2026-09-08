"""打牌1つずつを正解と突き合わせて、雀士の「精度」を測る。

成績表（和了率・放銃率）は**結果**しか見ない。同じ放銃でも
「他に切りようがなかった」のと「手の中に現物があったのに切った」のでは
意味がまったく違う。ここでは後者を数える。

シミュレータは相手の手牌が見えるので、こういう答え合わせができる。
実戦では絶対にできない種類の測定。

    python3 skills/mahjong/scripts/mj/audit.py --hands 400

測る項目:
  防げた放銃   放銃した局面で、手の中に**その相手の現物**があったか
  降り放銃     降りると決めたのに放銃した（安全牌の選び方が悪い）
  危険度の的中 放銃した牌を、自分でどれくらい危険と見積もっていたか
  牌効率ロス   脅威がないときに、受け入れ最大から何枚損したか
  待ち取りロス テンパイ時に、取れた中で一番広い待ちから何枚損したか
"""

from __future__ import annotations

import argparse
import collections
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mj import fast  # noqa: E402
from mj import players as pl  # noqa: E402
from mj.game import Game  # noqa: E402
from mj.tiles import NUM_TILES, tile_str  # noqa: E402


class Audit:
    def __init__(self, names):
        self.stat = {n: collections.Counter() for n in names}
        self.loss = {n: [] for n in names}      # 牌効率ロス
        self.wait_loss = {n: [] for n in names}  # 待ち取りロス
        self.last = {}                           # seat -> 直近の打牌の記録

    def record(self, name, seat, view, tile, threats, folding):
        me = view.me
        s = self.stat[name]
        s["打牌"] += 1
        hand = list(me.hand)

        if threats:
            s["脅威あり"] += 1
            if folding:
                s["降りた"] += 1
            # 手の中に、全部の脅威に通る牌があったか
            safe = [t for t in range(NUM_TILES) if hand[t] and all(
                p.river_counts[t] or t in p.passed for p, _ in threats)]
            seen = view.seen_all()
            risk = max(pl.reading.wait_risk(p, tile, seen, hand) for p, _ in threats)
            self.last[seat] = dict(name=name, tile=tile, hand=hand,
                                   safe=safe, risk=risk, folding=folding,
                                   shanten=fast.shanten(hand, me.called),
                                   threats=[p.seat for p, _ in threats])
        else:
            self.last[seat] = None
            # 脅威がないときだけ、純粋な牌効率を測る
            base = fast.shanten(hand, me.called)
            seen = view.visible()
            best = -1
            chosen = -1
            for t in range(NUM_TILES):
                if not hand[t]:
                    continue
                hand[t] -= 1
                if fast.shanten(hand, me.called) == base:
                    w = sum(n for _, n in fast.ukeire(hand, me.called, seen)[1])
                    if w > best:
                        best = w
                    if t == tile:
                        chosen = w
                hand[t] += 1
            if best >= 0 and chosen >= 0:
                self.loss[name].append(best - chosen)
                if best - chosen > 0:
                    s["受け入れを削った"] += 1
            # テンパイなら待ち取りも見る
            if base == 0:
                bw = cw = -1
                for t in range(NUM_TILES):
                    if not hand[t]:
                        continue
                    hand[t] -= 1
                    if fast.shanten(hand, me.called) == 0:
                        w = sum(n for _, n in fast.ukeire(hand, me.called, seen)[1])
                        if w > bw:
                            bw = w
                        if t == tile:
                            cw = w
                    hand[t] += 1
                if bw >= 0 and cw >= 0:
                    self.wait_loss[name].append(bw - cw)

    def deal_in(self, seat, winner):
        rec = self.last.get(seat)
        if not rec:
            return
        s = self.stat[rec["name"]]
        s["放銃"] += 1
        s["放銃時の危険度合計"] += int(rec["risk"] * 100)
        if rec["folding"]:
            s["降りたのに放銃"] += 1
        # 和了者に通る牌が手の中にあったか
        gen = [t for t in range(NUM_TILES) if rec["hand"][t] and (
            winner.river_counts[t] or t in winner.passed)]
        if gen:
            s["防げた放銃"] += 1
            sh = rec["shanten"]
            if rec["folding"]:
                s["└ 降りていた"] += 1
            elif sh <= 0:
                s["└ 押し・テンパイ"] += 1
            elif sh == 1:
                s["└ 押し・1シャンテン"] += 1
            else:
                s["└ 押し・2シャンテン以遠"] += 1


def run(hands: int, seed: int, lineup: str):
    from mj.simulate import build_lineup

    ai = build_lineup(lineup)
    audit = Audit([p.name for p in ai])
    orig = pl.Player.discard

    def hook(self, view, forbidden=frozenset()):
        threats = self._reads(view)
        level = max((l for _, l in threats), default=0.0)
        folding = False
        if level > 0:
            folding = not self._should_push(self.push_value(view, level))
        tile, declare = orig(self, view, forbidden)
        audit.record(self.name, view.seat, view, tile, threats, folding)
        return tile, declare

    pl.Player.discard = hook
    try:
        rng = random.Random(seed)
        for k in range(hands):
            g = Game(ai, [25000] * 4, 27 + (k // 4) % 2, k % 4, 0, 0, rng)
            res = g.play()
            if res.kind == "ron" and res.loser is not None:
                for seat, *_ in res.winners:
                    audit.deal_in(res.loser, g.players[seat])
                    break
            audit.last.clear()
            if (k + 1) % 100 == 0:
                print(f"  {k + 1}/{hands} 局", flush=True)
    finally:
        pl.Player.discard = orig
    return audit


def report(audit) -> str:
    out = []
    out.append(f"{'雀士':<10} {'放銃':>5} {'防げた':>7} {'割合':>7} "
               f"{'降り放銃':>8} {'放銃牌の自己評価':>16}")
    out.append("-" * 62)
    for name, s in audit.stat.items():
        n = s["放銃"] or 1
        out.append(
            f"{name:<10} {s['放銃']:>5} {s['防げた放銃']:>7} "
            f"{s['防げた放銃'] / n * 100:>6.1f}% {s['降りたのに放銃']:>8} "
            f"{s['放銃時の危険度合計'] / n / 100:>15.1f}%")
    out.append("")
    out.append("  「防げた放銃」＝ その相手の現物が手の中にあったのに、別の牌で放銃した")
    out.append("  「放銃牌の自己評価」＝ 切った時点で自分がその牌を何%危険と見ていたか")

    out.append(f"\n■ 「防げた放銃」の内訳（現物があったのに切らなかった理由）")
    keys = ["└ 降りていた", "└ 押し・テンパイ", "└ 押し・1シャンテン", "└ 押し・2シャンテン以遠"]
    labels = ["降りていた（明確な誤り）", "押し・テンパイ（正当）",
              "押し・1シャンテン（微妙）", "押し・2シャンテン以遠（ほぼ誤り）"]
    out.append(f"  {'雀士':<10}" + "".join(f"{l[:12]:>14}" for l in labels))
    out.append("-" * 68)
    for name, s2 in audit.stat.items():
        out.append(f"  {name:<10}" + "".join(f"{s2[k]:>14}" for k in keys))
    out.append("")
    out.append("  テンパイで押すのは正しい判断。問題は下の2列（降りていた／遠いのに押した）。")

    out.append(f"\n{'雀士':<10} {'牌効率ロス':>10} {'削った率':>9} {'待ち取りロス':>12}")
    out.append("-" * 46)
    for name in audit.stat:
        ls = audit.loss[name]
        ws = audit.wait_loss[name]
        s = audit.stat[name]
        avg = sum(ls) / len(ls) if ls else 0.0
        wav = sum(ws) / len(ws) if ws else 0.0
        rate = s["受け入れを削った"] / (len(ls) or 1) * 100
        out.append(f"{name:<10} {avg:>9.2f}枚 {rate:>8.1f}% {wav:>11.2f}枚")
    out.append("")
    out.append("  脅威がない（誰もテンパイに見えない）ときだけを対象にしている。")
    out.append("  ここでのロスは打点や手役のために意図的に削ったぶんも含む。")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hands", type=int, default=400)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--lineup", default="named")
    a = ap.parse_args()
    print(f"{a.hands} 局を打って、1打ずつ答え合わせします…")
    print(report(run(a.hands, a.seed, a.lineup)))


if __name__ == "__main__":
    main()
