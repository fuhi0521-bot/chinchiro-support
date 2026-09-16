"""牌の表記と内部表現。

内部表現は 34 種のインデックス:

    0-8   : 1m-9m (萬子)
    9-17  : 1p-9p (筒子)
    18-26 : 1s-9s (索子)
    27-30 : 東 南 西 北
    31-33 : 白 發 中

手牌は長さ 34 の枚数配列 (counts) で保持する。赤ドラは種類としては 5 と
同じなので、枚数配列とは別に「赤の枚数」として数える。
"""

from __future__ import annotations

MAN, PIN, SOU, HONOR = 0, 9, 18, 27
NUM_TILES = 34

SUIT_BASE = {"m": MAN, "p": PIN, "s": SOU, "z": HONOR}
HONOR_CHARS = "東南西北白發中"

WINDS = {"東": 27, "南": 28, "西": 29, "北": 30}
DRAGONS = (31, 32, 33)

# 么九牌（老頭牌 + 字牌）
TERMINALS = tuple(i for i in range(27) if i % 9 in (0, 8))
YAOCHU = tuple(list(TERMINALS) + list(range(27, 34)))
YAOCHU_SET = frozenset(YAOCHU)
SIMPLES = tuple(i for i in range(27) if i % 9 not in (0, 8))
GREEN = frozenset({19, 20, 21, 23, 25, 32})  # 2s3s4s6s8s發


class TileError(ValueError):
    """牌の表記が解釈できないときに送出する。"""


def is_honor(t: int) -> bool:
    return t >= HONOR


def is_number(t: int) -> bool:
    return t < HONOR


def suit_of(t: int) -> str:
    return "mpsz"[t // 9] if t < HONOR else "z"


def rank_of(t: int) -> int:
    """数牌なら 1-9、字牌なら 1-7 を返す。"""
    return (t % 9) + 1 if t < HONOR else (t - HONOR) + 1


def tile_str(t: int) -> str:
    if t >= HONOR:
        return HONOR_CHARS[t - HONOR]
    return f"{rank_of(t)}{suit_of(t)}"


def tiles_str(tiles) -> str:
    """牌のリストを 123m456p 形式にまとめる。"""
    out = []
    run: list[int] = []
    cur = None
    for t in sorted(tiles):
        s = suit_of(t)
        if s == "z":
            continue
        if cur is None or s == cur:
            cur = s
            run.append(rank_of(t))
        else:
            out.append("".join(map(str, run)) + cur)
            cur, run = s, [rank_of(t)]
    if run:
        out.append("".join(map(str, run)) + cur)
    honors = "".join(tile_str(t) for t in sorted(tiles) if t >= HONOR)
    return "".join(out) + honors


def counts_str(counts) -> str:
    tiles = []
    for i, n in enumerate(counts):
        tiles.extend([i] * n)
    return tiles_str(tiles)


def parse_tiles(text: str) -> tuple[list[int], int]:
    """`123m0p東東` のような表記を (牌リスト, 赤ドラ枚数) に変換する。

    - 数字 + 花色 (m/p/s/z) 。`0m/0p/0s` は赤5。
    - `東南西北白發中` はそのまま書ける。`発`/`发` も發として受け付ける。
      `1z`〜`7z` も同じ。
    - 空白 / カンマ / `-` は無視する。
    """
    tiles: list[int] = []
    aka = 0
    buf: list[int] = []
    for ch in text:
        if ch.isspace() or ch in ",、,-_|/":
            continue
        if ch in HONOR_CHARS:
            if buf:
                raise TileError(f"花色のない数字が残っています: {''.join(map(str, buf))}")
            tiles.append(HONOR + HONOR_CHARS.index(ch))
            continue
        if ch in "発发":  # 「發」の異体字・簡体字
            tiles.append(32)
            continue
        if ch.isdigit():
            buf.append(int(ch))
            continue
        if ch in SUIT_BASE:
            base = SUIT_BASE[ch]
            if not buf:
                raise TileError(f"'{ch}' の前に数字がありません")
            for n in buf:
                if ch == "z":
                    if not 1 <= n <= 7:
                        raise TileError(f"字牌は 1z〜7z です: {n}z")
                    tiles.append(HONOR + n - 1)
                elif n == 0:
                    tiles.append(base + 4)
                    aka += 1
                else:
                    tiles.append(base + n - 1)
            buf = []
            continue
        raise TileError(f"解釈できない文字です: {ch!r}")
    if buf:
        raise TileError(f"花色のない数字が残っています: {''.join(map(str, buf))}")
    return tiles, aka


def to_counts(tiles) -> list[int]:
    counts = [0] * NUM_TILES
    for t in tiles:
        counts[t] += 1
        if counts[t] > 4:
            raise TileError(f"{tile_str(t)} が5枚以上あります")
    return counts


def parse_counts(text: str) -> tuple[list[int], int]:
    tiles, aka = parse_tiles(text)
    return to_counts(tiles), aka


def parse_tile(text: str) -> int:
    """1枚だけの表記をインデックスに変換する。"""
    tiles, _ = parse_tiles(text)
    if len(tiles) != 1:
        raise TileError(f"1枚だけ指定してください: {text!r}")
    return tiles[0]


def dora_from_indicator(indicator: int) -> int:
    """ドラ表示牌から実際のドラを求める。"""
    if indicator < HONOR:
        base = (indicator // 9) * 9
        return base + (indicator - base + 1) % 9
    if indicator <= 30:  # 東南西北
        return 27 + (indicator - 27 + 1) % 4
    return 31 + (indicator - 31 + 1) % 3  # 白發中
