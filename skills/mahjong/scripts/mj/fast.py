"""高速シャンテン計算。

`shanten.py` の全探索は読みやすいが遅く、シミュレーションには使えない。
ここでは色ごとに独立して分解し、(面子, 搭子, 雀頭の有無) のパレート最適集合だけを
メモ化して持ち、最後に4グループを畳み込む。

色ごとの分解が独立なのは、面子も搭子も色をまたがないため。
結果は `shanten.py` と完全に一致することを検証済み（`tests/test_engine.py`）。
"""

from __future__ import annotations

from functools import lru_cache

from .tiles import NUM_TILES, YAOCHU


def _pareto(points) -> tuple:
    """(melds, partials, has_pair) のうち、他に支配されないものだけ残す。"""
    out = []
    for p in points:
        if not any(q != p and q[0] >= p[0] and q[1] >= p[1] and q[2] >= p[2] for q in points):
            out.append(p)
    return tuple(sorted(set(out)))


@lru_cache(maxsize=200_000)
def _profiles(counts: tuple, sequences: bool) -> tuple:
    """1グループ（1色、または字牌7種）の分解プロファイル。"""
    n = len(counts)
    c = list(counts)
    found = set()

    def rec(i: int, melds: int, partials: int, pair: int) -> None:
        while i < n and c[i] == 0:
            i += 1
        if i >= n:
            found.add((melds, partials, pair))
            return
        if c[i] >= 3:
            c[i] -= 3
            rec(i, melds + 1, partials, pair)
            c[i] += 3
        if sequences and i <= n - 3 and c[i + 1] and c[i + 2]:
            c[i] -= 1
            c[i + 1] -= 1
            c[i + 2] -= 1
            rec(i, melds + 1, partials, pair)
            c[i] += 1
            c[i + 1] += 1
            c[i + 2] += 1
        if c[i] >= 2:
            c[i] -= 2
            rec(i, melds, partials + 1, 1)
            c[i] += 2
        if sequences and i <= n - 2 and c[i + 1]:
            c[i] -= 1
            c[i + 1] -= 1
            rec(i, melds, partials + 1, pair)
            c[i] += 1
            c[i + 1] += 1
        if sequences and i <= n - 3 and c[i + 2]:
            c[i] -= 1
            c[i + 2] -= 1
            rec(i, melds, partials + 1, pair)
            c[i] += 1
            c[i + 2] += 1
        c[i] -= 1
        rec(i, melds, partials, pair)
        c[i] += 1

    rec(0, 0, 0, 0)
    return _pareto(found)


def _combine(a, b) -> tuple:
    return _pareto({(x[0] + y[0], x[1] + y[1], max(x[2], y[2])) for x in a for y in b})


def _hand_profiles(counts) -> tuple:
    """4グループを畳み込む。キャッシュは色ごとの `_profiles` だけに置く。

    手牌全体をキーにするとキーの種類が多すぎてメモリを使い切る。
    重いのは色ごとの分解なので、そこだけ覚えておけば足りる。
    """
    acc = _profiles(tuple(counts[0:9]), True)
    acc = _combine(acc, _profiles(tuple(counts[9:18]), True))
    acc = _combine(acc, _profiles(tuple(counts[18:27]), True))
    return _combine(acc, _profiles(tuple(counts[27:34]), False))


def shanten_standard(counts, called: int = 0) -> int:
    """一般形のシャンテン数。`shanten.shanten_standard` と同じ値を返す。"""
    best = 8
    for melds, partials, pair in _hand_profiles(counts):
        total = called + melds
        room = 5 - total
        if room < 0:
            room = 0
        keep = partials if partials < room else room
        s = 8 - 2 * total - keep
        if total + keep == 5 and not (pair and keep >= 1):
            s += 1
        if s < best:
            best = s
    return best


def shanten_chiitoi(counts) -> int:
    pairs = kinds = 0
    for n in counts:
        if n >= 1:
            kinds += 1
            if n >= 2:
                pairs += 1
    s = 6 - pairs
    if kinds < 7:
        s += 7 - kinds
    return s


def shanten_kokushi(counts) -> int:
    kinds = 0
    pair = 0
    for t in YAOCHU:
        n = counts[t]
        if n:
            kinds += 1
            if n >= 2:
                pair = 1
    return 13 - kinds - pair


def shanten(counts, called: int = 0) -> int:
    s = shanten_standard(counts, called)
    if called == 0:
        c = shanten_chiitoi(counts)
        if c < s:
            s = c
        k = shanten_kokushi(counts)
        if k < s:
            s = k
    return s


def _relevant(counts) -> list:
    """シャンテンを進めうる牌だけに絞る。

    孤立した牌を1枚引いてもブロックにならないので、手牌の牌そのものと
    その ±1・±2（同色内）だけを見ればよい。国士の受けだけ例外なので足す。
    """
    hit = set()
    for t in range(NUM_TILES):
        if not counts[t]:
            continue
        hit.add(t)
        if t < 27:
            r = t % 9
            base = t - r
            for d in (-2, -1, 1, 2):
                if 0 <= r + d <= 8:
                    hit.add(base + r + d)
    hit.update(YAOCHU)
    return sorted(hit)


def ukeire(counts, called: int = 0, visible=None):
    """(現在のシャンテン, [(牌, 残り枚数), ...])。"""
    cur = shanten(counts, called)
    accept = []
    for t in _relevant(counts):
        if counts[t] >= 4:
            continue
        counts[t] += 1
        better = shanten(counts, called) < cur
        counts[t] -= 1
        if better:
            left = 4 - counts[t] - (visible[t] if visible else 0)
            if left > 0:
                accept.append((t, left))
    return cur, accept
