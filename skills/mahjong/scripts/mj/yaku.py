"""役の判定と最終的な点数の確定（高点法）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .hand import (
    KANTSU,
    KOUTSU,
    SHUNTSU,
    Block,
    is_chiitoitsu,
    is_kokushi,
    meld_blocks,
    standard_parses,
    wait_type,
)
from .score import base_points, calc_fu, payments
from .tiles import (
    DRAGONS,
    GREEN,
    HONOR,
    NUM_TILES,
    YAOCHU_SET,
    TileError,
    tile_str,
)


@dataclass
class Context:
    """和了時の状況。"""

    is_tsumo: bool = False
    riichi: bool = False
    double_riichi: bool = False
    ippatsu: bool = False
    chankan: bool = False
    rinshan: bool = False
    haitei: bool = False
    houtei: bool = False
    tenhou: bool = False
    chiihou: bool = False
    seat_wind: int = 28  # 南（既定は子）
    round_wind: int = 27  # 東場
    dora: int = 0
    uradora: int = 0
    aka: int = 0
    honba: int = 0
    riichi_sticks: int = 0
    kuitan: bool = True  # 喰いタンあり
    kiriage: bool = False  # 切り上げ満貫（雀魂の段位戦は無し）
    double_wind_fu: int = 2

    @property
    def is_dealer(self) -> bool:
        return self.seat_wind == 27

    @property
    def dora_total(self) -> int:
        return self.dora + self.uradora + self.aka


@dataclass
class Result:
    yaku: list[tuple[str, int]] = field(default_factory=list)
    yakuman: list[tuple[str, int]] = field(default_factory=list)
    han: int = 0
    fu: int = 25
    fu_detail: list[str] = field(default_factory=list)
    base: int = 0
    limit: str | None = None
    payment = None
    blocks: list = field(default_factory=list)
    pair: int | None = None
    wait: str = "unknown"

    @property
    def total(self) -> int:
        return self.payment.total if self.payment else 0


def _tiles_of(blocks, pair) -> list[int]:
    tiles = [pair, pair]
    for b in blocks:
        tiles.extend(b.tiles)
    return tiles


def _has_yaochu(block) -> bool:
    if block.type == SHUNTSU:
        return block.tile % 9 == 0 or block.tile % 9 == 6
    return block.tile in YAOCHU_SET


def _suits_used(tiles) -> set[str]:
    return {"mpsz"[t // 9] if t < HONOR else "z" for t in tiles}


def _yakuman_for(blocks, pair, wait, ctx, menzen, counts) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    tiles = _tiles_of(blocks, pair)
    triplets = [b for b in blocks if b.type in (KOUTSU, KANTSU)]
    concealed_triplets = [b for b in triplets if b.concealed]
    winds = [b.tile for b in triplets if 27 <= b.tile <= 30]
    dragons = [b.tile for b in triplets if b.tile in DRAGONS]

    if ctx.tenhou:
        out.append(("天和", 1))
    if ctx.chiihou:
        out.append(("地和", 1))

    if menzen and len(concealed_triplets) == 4:
        out.append(("四暗刻単騎", 2) if wait == "tanki" else ("四暗刻", 1))
    if len(dragons) == 3:
        out.append(("大三元", 1))
    if all(t >= HONOR for t in tiles):
        out.append(("字一色", 1))
    if all(t in GREEN for t in tiles):
        out.append(("緑一色", 1))
    if all(t in YAOCHU_SET and t < HONOR for t in tiles):
        out.append(("清老頭", 1))
    if sum(1 for b in blocks if b.type == KANTSU) == 4:
        out.append(("四槓子", 1))
    if len(winds) == 4:
        out.append(("大四喜", 2))
    elif len(winds) == 3 and 27 <= pair <= 30:
        out.append(("小四喜", 1))

    if menzen and not any(b.from_meld for b in blocks):
        suits = _suits_used(tiles)
        if len(suits) == 1 and "z" not in suits:
            base = (tiles[0] // 9) * 9
            pattern = [3, 1, 1, 1, 1, 1, 1, 1, 3]
            extra = [counts[base + i] - pattern[i] for i in range(9)]
            if all(e >= 0 for e in extra) and sum(extra) == 1:
                out.append(("純正九蓮宝燈", 2) if _is_pure_kyuuren(counts, base, ctx) else ("九蓮宝燈", 1))
    return out


def _is_pure_kyuuren(counts, base, ctx) -> bool:
    """純正（九面待ち）かどうかは和了牌を抜いた形が 1112345678999 かで決まる。"""
    win = getattr(ctx, "_win_tile", None)
    if win is None:
        return False
    work = list(counts)
    work[win] -= 1
    pattern = [3, 1, 1, 1, 1, 1, 1, 1, 3]
    return all(work[base + i] == pattern[i] for i in range(9))


def _standard_yaku(blocks, pair, wait, ctx, menzen) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    tiles = _tiles_of(blocks, pair)
    shuntsu = [b for b in blocks if b.type == SHUNTSU]
    triplets = [b for b in blocks if b.type in (KOUTSU, KANTSU)]
    concealed_triplets = [b for b in triplets if b.concealed]
    suits = _suits_used(tiles)
    open_hand = not menzen

    # --- 状況役 ---
    if ctx.double_riichi:
        out.append(("ダブル立直", 2))
    elif ctx.riichi:
        out.append(("立直", 1))
    if ctx.ippatsu and (ctx.riichi or ctx.double_riichi):
        out.append(("一発", 1))
    if menzen and ctx.is_tsumo:
        out.append(("門前清自摸和", 1))
    if ctx.rinshan:
        out.append(("嶺上開花", 1))
    if ctx.chankan:
        out.append(("搶槓", 1))
    if ctx.haitei:
        out.append(("海底摸月", 1))
    if ctx.houtei:
        out.append(("河底撈魚", 1))

    # --- 役牌 ---
    for b in triplets:
        if b.tile in DRAGONS:
            out.append((f"役牌 {tile_str(b.tile)}", 1))
        else:
            if b.tile == ctx.round_wind:
                out.append((f"場風 {tile_str(b.tile)}", 1))
            if b.tile == ctx.seat_wind:
                out.append((f"自風 {tile_str(b.tile)}", 1))

    # --- 平和 ---
    is_pinfu = _is_pinfu(blocks, pair, wait, ctx, menzen)
    if is_pinfu:
        out.append(("平和", 1))

    # --- 断幺九 ---
    if all(t not in YAOCHU_SET for t in tiles):
        if menzen or ctx.kuitan:
            out.append(("断幺九", 1))

    # --- 一盃口 / 二盃口 ---
    if menzen:
        starts = sorted(b.tile for b in shuntsu)
        dup = 0
        i = 0
        while i < len(starts) - 1:
            if starts[i] == starts[i + 1]:
                dup += 1
                i += 2
            else:
                i += 1
        if dup == 2:
            out.append(("二盃口", 3))
        elif dup == 1:
            out.append(("一盃口", 1))

    # --- 三色同順 ---
    by_rank: dict[int, set[int]] = {}
    for b in shuntsu:
        by_rank.setdefault(b.tile % 9, set()).add(b.tile // 9)
    if any(len(v) == 3 for v in by_rank.values()):
        out.append(("三色同順", 1 if open_hand else 2))

    # --- 一気通貫 ---
    for suit in range(3):
        starts = {b.tile % 9 for b in shuntsu if b.tile // 9 == suit}
        if {0, 3, 6} <= starts:
            out.append(("一気通貫", 1 if open_hand else 2))
            break

    # --- 三色同刻 ---
    trank: dict[int, set[int]] = {}
    for b in triplets:
        if b.tile < HONOR:
            trank.setdefault(b.tile % 9, set()).add(b.tile // 9)
    if any(len(v) == 3 for v in trank.values()):
        out.append(("三色同刻", 2))

    # --- 対々和 / 三暗刻 / 三槓子 ---
    if len(triplets) == 4:
        out.append(("対々和", 2))
    if len(concealed_triplets) == 3:
        out.append(("三暗刻", 2))
    if sum(1 for b in blocks if b.type == KANTSU) == 3:
        out.append(("三槓子", 2))

    # --- 三元役 ---
    dragon_triplets = [b for b in triplets if b.tile in DRAGONS]
    if len(dragon_triplets) == 2 and pair in DRAGONS:
        out.append(("小三元", 2))

    # --- 老頭・帯幺 ---
    all_yaochu = all(t in YAOCHU_SET for t in tiles)
    if all_yaochu and "z" in suits:
        out.append(("混老頭", 2))
    elif all(_has_yaochu(b) for b in blocks) and pair in YAOCHU_SET:
        if "z" in suits:
            out.append(("混全帯幺九", 1 if open_hand else 2))
        else:
            out.append(("純全帯幺九", 2 if open_hand else 3))

    # --- 染め手 ---
    number_suits = suits - {"z"}
    if len(number_suits) == 1:
        if "z" in suits:
            out.append(("混一色", 2 if open_hand else 3))
        else:
            out.append(("清一色", 5 if open_hand else 6))

    return out


def _is_pinfu(blocks, pair, wait, ctx, menzen) -> bool:
    if not menzen:
        return False
    if any(b.type != SHUNTSU for b in blocks):
        return False
    if wait != "ryanmen":
        return False
    if pair in DRAGONS or pair == ctx.seat_wind or pair == ctx.round_wind:
        return False
    return True


def _evaluate_one(blocks, pair, wait, ctx, menzen, counts) -> Result:
    r = Result(blocks=list(blocks), pair=pair, wait=wait)
    yakuman = _yakuman_for(blocks, pair, wait, ctx, menzen, counts)
    if yakuman:
        r.yakuman = yakuman
        mult = sum(m for _, m in yakuman)
        r.base, r.limit = base_points(0, 0, yakuman=mult)
        r.fu = 0
        r.payment = payments(
            r.base,
            is_dealer=ctx.is_dealer,
            is_tsumo=ctx.is_tsumo,
            honba=ctx.honba,
            riichi_sticks=ctx.riichi_sticks,
        )
        return r

    yaku = _standard_yaku(blocks, pair, wait, ctx, menzen)
    if not yaku:
        r.han = 0
        return r

    is_pinfu = any(n == "平和" for n, _ in yaku)
    fu, detail = calc_fu(
        blocks,
        pair,
        wait,
        menzen=menzen,
        is_tsumo=ctx.is_tsumo,
        seat_wind=ctx.seat_wind,
        round_wind=ctx.round_wind,
        is_pinfu=is_pinfu,
        double_wind_fu=ctx.double_wind_fu,
    )
    han = sum(h for _, h in yaku)
    full = list(yaku)
    if ctx.dora:
        full.append((f"ドラ{ctx.dora}", ctx.dora))
    if ctx.aka:
        full.append((f"赤ドラ{ctx.aka}", ctx.aka))
    if ctx.uradora:
        full.append((f"裏ドラ{ctx.uradora}", ctx.uradora))
    han += ctx.dora_total

    r.yaku = full
    r.han = han
    r.fu = fu
    r.fu_detail = detail
    r.base, r.limit = base_points(han, fu, kiriage=ctx.kiriage)
    r.payment = payments(
        r.base,
        is_dealer=ctx.is_dealer,
        is_tsumo=ctx.is_tsumo,
        honba=ctx.honba,
        riichi_sticks=ctx.riichi_sticks,
    )
    return r


def _chiitoi_result(counts, ctx, win_tile) -> Result:
    blocks: list[Block] = []
    yaku = [("七対子", 2)]
    tiles = [t for t in range(NUM_TILES) for _ in range(counts[t])]
    if ctx.double_riichi:
        yaku.append(("ダブル立直", 2))
    elif ctx.riichi:
        yaku.append(("立直", 1))
    if ctx.ippatsu and (ctx.riichi or ctx.double_riichi):
        yaku.append(("一発", 1))
    if ctx.is_tsumo:
        yaku.append(("門前清自摸和", 1))
    if ctx.haitei:
        yaku.append(("海底摸月", 1))
    if ctx.houtei:
        yaku.append(("河底撈魚", 1))
    if all(t not in YAOCHU_SET for t in tiles):
        yaku.append(("断幺九", 1))
    suits = _suits_used(tiles)
    if all(t in YAOCHU_SET for t in tiles) and "z" in suits:
        yaku.append(("混老頭", 2))
    number_suits = suits - {"z"}
    if len(number_suits) == 1:
        yaku.append(("混一色", 3) if "z" in suits else ("清一色", 6))

    r = Result(blocks=blocks, pair=None, wait="tanki")
    han = sum(h for _, h in yaku)
    full = list(yaku)
    for label, n in (("ドラ", ctx.dora), ("赤ドラ", ctx.aka), ("裏ドラ", ctx.uradora)):
        if n:
            full.append((f"{label}{n}", n))
    han += ctx.dora_total
    r.yaku = full
    r.han = han
    r.fu = 25
    r.fu_detail = ["七対子 25符固定"]
    r.base, r.limit = base_points(han, 25, kiriage=ctx.kiriage)
    r.payment = payments(
        r.base, is_dealer=ctx.is_dealer, is_tsumo=ctx.is_tsumo, honba=ctx.honba, riichi_sticks=ctx.riichi_sticks
    )
    return r


def _kokushi_result(counts, ctx, win_tile) -> Result:
    pair_tile = next(t for t in range(NUM_TILES) if counts[t] == 2)
    thirteen = pair_tile == win_tile
    name = "国士無双十三面待ち" if thirteen else "国士無双"
    mult = 2 if thirteen else 1
    r = Result(yakuman=[(name, mult)], wait="tanki")
    r.base, r.limit = base_points(0, 0, yakuman=mult)
    r.fu = 0
    r.payment = payments(
        r.base, is_dealer=ctx.is_dealer, is_tsumo=ctx.is_tsumo, honba=ctx.honba, riichi_sticks=ctx.riichi_sticks
    )
    return r


def evaluate(counts, melds, win_tile: int, ctx: Context) -> Result:
    """和了形を評価し、最も高い解釈の結果を返す（高点法）。

    counts は手の内（和了牌を含む）の枚数配列。melds は副露のリスト。
    """
    counts = list(counts)
    if counts[win_tile] == 0:
        raise TileError(f"和了牌 {tile_str(win_tile)} が手牌に含まれていません")
    total = sum(counts) + 3 * len(melds)
    if total != 14:
        raise TileError(f"和了形は14枚（副露込み）です。いまは {total} 枚です")

    ctx._win_tile = win_tile
    menzen = not any(m.is_open for m in melds)
    mblocks = meld_blocks(melds)

    candidates: list[Result] = []

    if not melds and is_kokushi(counts):
        candidates.append(_kokushi_result(counts, ctx, win_tile))
    if not melds and is_chiitoitsu(counts):
        candidates.append(_chiitoi_result(counts, ctx, win_tile))

    for pair, sets in standard_parses(counts):
        positions: list[int | None] = []
        if pair == win_tile:
            positions.append(None)
        for idx, (kind, start) in enumerate(sets):
            if kind == KOUTSU and start == win_tile:
                positions.append(idx)
            elif kind == SHUNTSU and start <= win_tile <= start + 2:
                positions.append(idx)
        seen_waits = set()
        for pos in positions:
            wait = wait_type(pair, sets, win_tile, pos)
            key = (pair, sets, wait, pos if pos is None else sets[pos])
            if key in seen_waits:
                continue
            seen_waits.add(key)
            hand_blocks = []
            for idx, (kind, start) in enumerate(sets):
                concealed = kind == KOUTSU and not (idx == pos and not ctx.is_tsumo)
                hand_blocks.append(Block(kind, start, concealed))
            blocks = mblocks + hand_blocks
            candidates.append(_evaluate_one(blocks, pair, wait, ctx, menzen, counts))

    if not candidates:
        raise TileError("和了形になっていません")

    scored = [c for c in candidates if c.payment]
    if not scored:
        return candidates[0]  # 役なし
    return max(scored, key=lambda r: (r.total, r.han, r.fu))


def format_result(r: Result) -> str:
    lines = []
    if r.yakuman:
        for name, mult in r.yakuman:
            lines.append(f"  {name}" + ("（ダブル）" if mult == 2 else ""))
        lines.append(f"  {r.limit}")
    elif r.han == 0:
        return "役なし（アガれません）"
    else:
        for name, han in r.yaku:
            lines.append(f"  {name} {han}翻")
        head = f"{r.han}翻{r.fu}符"
        if r.limit:
            head += f"（{r.limit}）"
        lines.append(f"  {head}")
    lines.append(f"  → {r.payment.text}  合計 {r.payment.total}点")
    return "\n".join(lines)
