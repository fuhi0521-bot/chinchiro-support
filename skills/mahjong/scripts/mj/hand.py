"""和了形の分解 — 面子・雀頭・待ちの形を列挙する。"""

from __future__ import annotations

from dataclasses import dataclass

from .tiles import HONOR, NUM_TILES, TileError, parse_tiles, tile_str

SHUNTSU, KOUTSU, KANTSU = "shuntsu", "koutsu", "kantsu"


@dataclass(frozen=True)
class Meld:
    """副露した面子（暗槓を含む）。"""

    kind: str  # chi / pon / minkan / ankan
    tile: int  # 順子は開始牌、刻子・槓子はその牌

    @property
    def is_open(self) -> bool:
        """門前を崩すか。暗槓は崩さない。"""
        return self.kind != "ankan"

    @property
    def is_kan(self) -> bool:
        return self.kind in ("minkan", "ankan")

    @property
    def block_type(self) -> str:
        if self.kind == "chi":
            return SHUNTSU
        return KANTSU if self.is_kan else KOUTSU

    @property
    def concealed(self) -> bool:
        return self.kind == "ankan"

    @property
    def tiles(self) -> list[int]:
        if self.kind == "chi":
            return [self.tile, self.tile + 1, self.tile + 2]
        return [self.tile] * (4 if self.is_kan else 3)

    def __str__(self) -> str:
        label = {"chi": "チー", "pon": "ポン", "minkan": "明槓", "ankan": "暗槓"}[self.kind]
        if self.kind == "chi":
            return f"{label}{tile_str(self.tile)}{tile_str(self.tile + 1)}{tile_str(self.tile + 2)}"
        return f"{label}{tile_str(self.tile)}"


@dataclass(frozen=True)
class Block:
    """和了形を構成する1ブロック。"""

    type: str
    tile: int  # 順子は開始牌
    concealed: bool  # 暗刻・暗槓なら True（ロンで完成した刻子は False）
    from_meld: bool = False

    @property
    def tiles(self) -> list[int]:
        if self.type == SHUNTSU:
            return [self.tile, self.tile + 1, self.tile + 2]
        return [self.tile] * (4 if self.type == KANTSU else 3)

    def __str__(self) -> str:
        if self.type == SHUNTSU:
            return f"{tile_str(self.tile)}{tile_str(self.tile + 1)}{tile_str(self.tile + 2)}"
        mark = {"koutsu": "", "kantsu": "槓"}[self.type]
        return tile_str(self.tile) * 3 + mark


def parse_melds(text: str | None) -> list[Meld]:
    """`chi=234p,pon=白,ankan=5s` 形式を Meld のリストにする。"""
    if not text:
        return []
    melds: list[Meld] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        for sep in ("=", ":"):
            if sep in part:
                kind, body = part.split(sep, 1)
                break
        else:
            raise TileError(f"副露の書式は kind=牌 です: {part!r}")
        kind = kind.strip().lower()
        aliases = {
            "chi": "chi", "チー": "chi", "chii": "chi",
            "pon": "pon", "ポン": "pon",
            "minkan": "minkan", "明槓": "minkan", "kan": "minkan", "daiminkan": "minkan",
            "ankan": "ankan", "暗槓": "ankan",
        }
        if kind not in aliases:
            raise TileError(f"副露の種類が不明です: {kind!r} (chi/pon/minkan/ankan)")
        kind = aliases[kind]
        tiles, _ = parse_tiles(body)
        if kind == "chi":
            if len(tiles) != 3:
                raise TileError(f"チーは3枚で指定してください: {part!r}")
            tiles.sort()
            if tiles[0] >= HONOR or tiles[1] != tiles[0] + 1 or tiles[2] != tiles[0] + 2:
                raise TileError(f"チーは連続した数牌にしてください: {part!r}")
            melds.append(Meld("chi", tiles[0]))
        else:
            if len(set(tiles)) != 1:
                raise TileError(f"{kind} は同じ牌で指定してください: {part!r}")
            melds.append(Meld(kind, tiles[0]))
    return melds


def meld_blocks(melds) -> list[Block]:
    return [Block(m.block_type, m.tile, m.concealed, from_meld=True) for m in melds]


def _all_set_splits(counts) -> set[tuple]:
    """雀頭を除いた枚数配列を、面子だけに分解する全通りを返す。"""
    out: set[tuple] = set()
    work = list(counts)

    def rec(i: int, acc: list) -> None:
        while i < NUM_TILES and work[i] == 0:
            i += 1
        if i >= NUM_TILES:
            out.add(tuple(sorted(acc)))
            return
        if work[i] >= 3:
            work[i] -= 3
            acc.append((KOUTSU, i))
            rec(i, acc)
            acc.pop()
            work[i] += 3
        if i < HONOR and i % 9 <= 6 and work[i + 1] and work[i + 2]:
            work[i] -= 1
            work[i + 1] -= 1
            work[i + 2] -= 1
            acc.append((SHUNTSU, i))
            rec(i, acc)
            acc.pop()
            work[i] += 1
            work[i + 1] += 1
            work[i + 2] += 1

    rec(0, [])
    return out


def standard_parses(counts) -> list[tuple[int, tuple]]:
    """一般形の和了形を (雀頭, 面子タプル) のリストで返す。和了形でなければ空。"""
    results = []
    work = list(counts)
    for p in range(NUM_TILES):
        if work[p] >= 2:
            work[p] -= 2
            for sets in _all_set_splits(work):
                results.append((p, sets))
            work[p] += 2
    return results


def is_chiitoitsu(counts) -> bool:
    return sum(counts) == 14 and sum(1 for n in counts if n == 2) == 7


def is_kokushi(counts) -> bool:
    from .tiles import YAOCHU

    if sum(counts) != 14:
        return False
    if any(counts[t] for t in range(NUM_TILES) if t not in YAOCHU):
        return False
    return all(counts[t] >= 1 for t in YAOCHU) and any(counts[t] == 2 for t in YAOCHU)


def wait_type(pair: int, sets, win_tile: int, block_index) -> str:
    """待ちの形を返す: tanki / shanpon / kanchan / penchan / ryanmen。"""
    if block_index is None:
        return "tanki" if win_tile == pair else "unknown"
    kind, start = sets[block_index]
    if kind == KOUTSU:
        return "shanpon"
    offset = win_tile - start
    if offset == 1:
        return "kanchan"
    if offset == 0 and start % 9 == 6:  # 789 の 7 待ち
        return "penchan"
    if offset == 2 and start % 9 == 0:  # 123 の 3 待ち
        return "penchan"
    return "ryanmen"
