"""シャンテン数の計算。

シャンテン数は「あと何枚入れ替えればテンパイするか」。
テンパイ = 0、和了形 = -1 とする。

一般形は  shanten = 8 - 2*(面子数) - (搭子数)  を、
面子 + 搭子 <= 5 ブロックの制約のもとで最小化して求める。
5ブロックそろっていて雀頭が無い場合だけ +1 の補正が入る。
"""

from __future__ import annotations

from .tiles import HONOR, NUM_TILES, YAOCHU


def shanten_standard(counts, called: int = 0) -> int:
    """一般形（4面子1雀頭）のシャンテン数。

    called は副露した面子の数（暗槓を含む）。
    """
    counts = list(counts)
    best = [8]

    def evaluate(melds: int, partials: int, pairs: int) -> None:
        total_melds = called + melds
        s = 8 - 2 * total_melds - partials
        if total_melds + partials == 5 and pairs == 0:
            s += 1
        if s < best[0]:
            best[0] = s

    def rec(i: int, melds: int, partials: int, pairs: int) -> None:
        if i >= NUM_TILES:
            evaluate(melds, partials, pairs)
            return
        if counts[i] == 0:
            rec(i + 1, melds, partials, pairs)
            return

        room = (called + melds + partials) < 5

        if room and counts[i] >= 3:
            counts[i] -= 3
            rec(i, melds + 1, partials, pairs)
            counts[i] += 3

        if room and i < HONOR and i % 9 <= 6 and counts[i + 1] and counts[i + 2]:
            counts[i] -= 1
            counts[i + 1] -= 1
            counts[i + 2] -= 1
            rec(i, melds + 1, partials, pairs)
            counts[i] += 1
            counts[i + 1] += 1
            counts[i + 2] += 1

        if room and counts[i] >= 2:
            counts[i] -= 2
            rec(i, melds, partials + 1, pairs + 1)
            counts[i] += 2

        if room and i < HONOR and i % 9 <= 7 and counts[i + 1]:
            counts[i] -= 1
            counts[i + 1] -= 1
            rec(i, melds, partials + 1, pairs)
            counts[i] += 1
            counts[i + 1] += 1

        if room and i < HONOR and i % 9 <= 6 and counts[i + 2]:
            counts[i] -= 1
            counts[i + 2] -= 1
            rec(i, melds, partials + 1, pairs)
            counts[i] += 1
            counts[i + 2] += 1

        # この牌を浮き牌として扱う
        counts[i] -= 1
        rec(i, melds, partials, pairs)
        counts[i] += 1

    rec(0, 0, 0, 0)
    return best[0]


def shanten_chiitoi(counts) -> int:
    """七対子のシャンテン数（門前限定）。"""
    pairs = sum(1 for n in counts if n >= 2)
    kinds = sum(1 for n in counts if n >= 1)
    s = 6 - pairs
    if kinds < 7:
        s += 7 - kinds
    return s


def shanten_kokushi(counts) -> int:
    """国士無双のシャンテン数（門前限定）。"""
    kinds = sum(1 for t in YAOCHU if counts[t] >= 1)
    has_pair = any(counts[t] >= 2 for t in YAOCHU)
    return 13 - kinds - (1 if has_pair else 0)


def shanten(counts, called: int = 0) -> int:
    """一般形・七対子・国士のうち最小のシャンテン数。"""
    s = shanten_standard(counts, called)
    if called == 0:
        s = min(s, shanten_chiitoi(counts), shanten_kokushi(counts))
    return s


def shanten_detail(counts, called: int = 0) -> dict:
    d = {"standard": shanten_standard(counts, called)}
    if called == 0:
        d["chiitoitsu"] = shanten_chiitoi(counts)
        d["kokushi"] = shanten_kokushi(counts)
    d["best"] = min(d.values())
    return d


def is_agari(counts, called: int = 0) -> bool:
    return shanten(counts, called) == -1
