"""着順と、オーラスの条件計算。

「あと何点あれば着順が上がるか」を、ロン（直撃／他家）・ツモ・流局テンパイに
分けて厳密に出す。点数は `score.py` の点数表から生成するので、
実際に存在する点数しか候補に出てこない。

同点は起家（席0）に近いほうが上位。
"""

from __future__ import annotations

from functools import lru_cache

from .score import base_points, noten_penalty, payments

FU_CANDIDATES = (20, 25, 30, 40, 50, 60, 70, 80, 90, 100, 110)


def ranking(scores) -> list[int]:
    """上位から並べた席のリスト。同点は起家に近いほうが上。"""
    return sorted(range(4), key=lambda i: (-scores[i], i))


def rank_of(scores, seat: int) -> int:
    """0 = トップ, 3 = ラス。"""
    return ranking(scores).index(seat)


@lru_cache(maxsize=256)
def candidate_payments(is_dealer: bool, is_tsumo: bool, honba: int):
    """実際に存在する点数を、小さい順に (翻, 符, Payment) で返す。"""
    out = []
    seen = set()
    for han in range(1, 14):
        for fu in FU_CANDIDATES:
            if fu in (20, 25) and han < 2:
                continue
            base, _ = base_points(han, fu)
            p = payments(base, is_dealer=is_dealer, is_tsumo=is_tsumo, honba=honba, riichi_sticks=0)
            key = (p.ron, p.from_dealer, p.from_each_child)
            if key in seen:
                continue
            seen.add(key)
            out.append((han, fu, p))
    out.sort(key=lambda x: x[2].total)
    return tuple(out)


def win_deltas(payment, me: int, dealer: int, is_tsumo: bool, loser=None, sticks: int = 0):
    """和了したときの点数移動。供託は和了者が総取り。"""
    d = [0, 0, 0, 0]
    if is_tsumo:
        for i in range(4):
            if i == me:
                continue
            amount = payment.from_each_child if (me == dealer or i != dealer) else payment.from_dealer
            d[i] -= amount
            d[me] += amount
    else:
        d[loser] -= payment.ron
        d[me] += payment.ron
    d[me] += sticks * 1000
    return d


def scores_after_win(scores, payment, me, dealer, is_tsumo, loser=None, sticks=0):
    d = win_deltas(payment, me, dealer, is_tsumo, loser, sticks)
    return [scores[i] + d[i] for i in range(4)]


def rank_after_win(scores, payment, me, dealer, is_tsumo, loser=None, sticks=0) -> int:
    return rank_of(scores_after_win(scores, payment, me, dealer, is_tsumo, loser, sticks), me)


def rank_after_draw(scores, me: int, tenpai_seats) -> int:
    """流局したときの着順。tenpai_seats はテンパイしている席の集合。"""
    gain, pay = noten_penalty(len(tenpai_seats))
    new = [scores[i] + (gain if i in tenpai_seats else -pay) for i in range(4)]
    return rank_of(new, me)


def requirements(scores, me: int, dealer: int, honba: int = 0, sticks: int = 0, target_rank: int | None = None):
    """目標着順に届く最小の手を返す。

    戻り値:
        {
          "rank": 今の着順(0-3),
          "target": 目標着順,
          "tsumo": (翻, 符, 収入) or None,
          "ron": {放銃者の席: (翻, 符, 点数)},   # 直撃を含む
          "ron_any": 直撃でない相手からのロンで必要な最小点 or None,
          "direct": 一番下の相手を直撃する場合の最小点 or None,
        }
    """
    cur = rank_of(scores, me)
    target = target_rank if target_rank is not None else max(0, cur - 1)
    is_dealer = me == dealer
    out = {"rank": cur, "target": target, "tsumo": None, "ron": {}, "ron_any": None, "direct": None}
    if cur <= target:
        out["already"] = True
        return out

    for han, fu, p in candidate_payments(is_dealer, True, honba):
        if rank_after_win(scores, p, me, dealer, True, sticks=sticks) <= target:
            out["tsumo"] = (han, fu, p.total + sticks * 1000, p.text)
            break

    order = ranking(scores)
    just_above = order[cur - 1]
    for loser in range(4):
        if loser == me:
            continue
        for han, fu, p in candidate_payments(is_dealer, False, honba):
            if rank_after_win(scores, p, me, dealer, False, loser=loser, sticks=sticks) <= target:
                out["ron"][loser] = (han, fu, p.ron)
                break
    # 直撃＝すぐ上の相手から取る（点差が2倍縮まるので必要打点が下がる）
    if just_above in out["ron"]:
        out["direct"] = out["ron"][just_above]
    others = [v[2] for k, v in out["ron"].items() if k != just_above]
    if others:
        out["ron_any"] = max(others)
    return out


def gap_to(scores, me: int, other: int) -> int:
    """相手との点差（正なら相手が上）。"""
    return scores[other] - scores[me]


def describe(scores, me, dealer, honba=0, sticks=0) -> str:
    """人間が読む形にする。"""
    req = requirements(scores, me, dealer, honba, sticks)
    cur = req["rank"]
    if req.get("already"):
        return f"現在 {cur + 1}着。条件を満たしている"
    order = ranking(scores)
    target_seat = order[cur - 1]
    lines = [
        f"現在 {cur + 1}着（{scores[me]}点）。{cur}着 は席{target_seat}（{scores[target_seat]}点、{scores[target_seat] - scores[me]}点差）"
    ]
    if req["tsumo"]:
        han, fu, total, text = req["tsumo"]
        lines.append(f"  ツモ: {han}翻{fu}符（{text}）以上")
    else:
        lines.append("  ツモ: 役満でも届かない")
    if req["direct"]:
        lines.append(f"  直撃: {req['direct'][2]}点以上")
    if req["ron_any"]:
        lines.append(f"  他家からロン: {req['ron_any']}点以上")
    return "\n".join(lines)
