"""牌効率 — 受け入れ枚数・待ち牌・何切る。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .shanten import shanten as calc_shanten
from .tiles import NUM_TILES, TileError, counts_str, tile_str


def check_size(counts, called: int, expect: int) -> None:
    """手牌の枚数が正しいか確認する。expect は 1(=3n+1) か 2(=3n+2)。"""
    n = sum(counts) + called * 3
    if n % 3 != expect % 3 or not 0 < n <= 14:
        want = "13枚（3n+1）" if expect == 1 else "14枚（3n+2）"
        raise TileError(
            f"手牌の枚数が合いません: 手{sum(counts)}枚 + 副露{called}面子 = {n}枚。{want}にしてください"
        )


def _remaining(t: int, counts, visible=None) -> int:
    """その牌が場に何枚残っているか（自分の手牌と既知の見え牌を引く）。"""
    seen = counts[t]
    if visible:
        seen += visible[t]
    return max(0, 4 - seen)


def ukeire(counts, called: int = 0, visible=None) -> tuple[int, list[tuple[int, int]]]:
    """13枚（または 3n+1 枚）の手牌の受け入れを返す。

    戻り値は (現在のシャンテン数, [(牌, 残り枚数), ...])。
    シャンテンが進む牌だけを列挙する。
    """
    check_size(counts, called, 1)
    cur = calc_shanten(counts, called)
    accept: list[tuple[int, int]] = []
    work = list(counts)
    for t in range(NUM_TILES):
        if work[t] >= 4:
            continue
        work[t] += 1
        if calc_shanten(work, called) < cur:
            left = _remaining(t, counts, visible)
            if left > 0:
                accept.append((t, left))
        work[t] -= 1
    return cur, accept


def waits(counts, called: int = 0, visible=None) -> list[tuple[int, int]]:
    """テンパイしている手牌の待ち牌（＝アガリ牌）と残り枚数。

    テンパイしていなければ空リスト。
    """
    cur, acc = ukeire(counts, called, visible)
    return acc if cur == 0 else []


@dataclass
class DiscardOption:
    tile: int
    shanten: int
    accepts: list[tuple[int, int]] = field(default_factory=list)

    @property
    def width(self) -> int:
        return sum(n for _, n in self.accepts)

    @property
    def kinds(self) -> int:
        return len(self.accepts)

    def describe(self) -> str:
        tiles = " ".join(f"{tile_str(t)}({n})" for t, n in self.accepts)
        head = f"打{tile_str(self.tile)}  {self.shanten_label}  {self.kinds}種{self.width}枚"
        return f"{head}\n    {tiles}" if tiles else head

    @property
    def shanten_label(self) -> str:
        if self.shanten == -1:
            return "和了"
        if self.shanten == 0:
            return "テンパイ"
        return f"{self.shanten}シャンテン"


def discard_options(counts, called: int = 0, visible=None) -> list[DiscardOption]:
    """14枚（3n+2枚）の手牌について、切る牌ごとの結果を良い順に返す。"""
    check_size(counts, called, 2)
    options: list[DiscardOption] = []
    work = list(counts)
    for t in range(NUM_TILES):
        if work[t] == 0:
            continue
        work[t] -= 1
        s, acc = ukeire(work, called, visible)
        options.append(DiscardOption(t, s, acc))
        work[t] += 1
    options.sort(key=lambda o: (o.shanten, -o.width, -o.kinds, o.tile))
    return options


def block_report(counts) -> str:
    """5ブロック理論の観点で手牌をざっと言語化する（補助情報）。"""
    lines = [f"手牌: {counts_str(counts)}  ({sum(counts)}枚)"]
    pairs = [i for i, n in enumerate(counts) if n >= 2]
    triplets = [i for i, n in enumerate(counts) if n >= 3]
    if triplets:
        lines.append("暗刻: " + " ".join(tile_str(t) for t in triplets))
    if pairs:
        lines.append("対子: " + " ".join(tile_str(t) for t in pairs))
    return "\n".join(lines)
