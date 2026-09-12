"""符計算と点数計算。"""

from __future__ import annotations

from dataclasses import dataclass

from .hand import KANTSU, KOUTSU, SHUNTSU
from .tiles import DRAGONS, YAOCHU_SET

LIMIT_NAMES = [
    (13, "役満"),
    (11, "三倍満"),
    (8, "倍満"),
    (6, "跳満"),
    (5, "満貫"),
]


def round_up_10(n: int) -> int:
    return -(-n // 10) * 10


def round_up_100(n: int) -> int:
    return -(-n // 100) * 100


def block_fu(block, yaku_winds=()) -> int:
    """1ブロックの符。"""
    if block.type == SHUNTSU:
        return 0
    yaochu = block.tile in YAOCHU_SET
    if block.type == KANTSU:
        base = 16 if block.concealed else 8
    else:
        base = 4 if block.concealed else 2
    return base * 2 if yaochu else base


def pair_fu(tile: int, seat_wind: int, round_wind: int, double_wind_fu: int = 2) -> int:
    """雀頭の符。役牌なら2符。連風牌の扱いはルール差があるので引数で切り替える。"""
    fu = 0
    if tile in DRAGONS:
        return 2
    if tile == seat_wind:
        fu += 2
    if tile == round_wind:
        fu += 2
    if fu == 4:
        return double_wind_fu
    return fu


WAIT_FU = {"tanki": 2, "kanchan": 2, "penchan": 2, "ryanmen": 0, "shanpon": 0, "unknown": 0}


def calc_fu(
    blocks,
    pair: int,
    wait: str,
    *,
    menzen: bool,
    is_tsumo: bool,
    seat_wind: int,
    round_wind: int,
    is_pinfu: bool,
    is_chiitoitsu: bool = False,
    double_wind_fu: int = 2,
) -> tuple[int, list[str]]:
    """符とその内訳を返す。"""
    if is_chiitoitsu:
        return 25, ["七対子 25符固定"]
    if is_pinfu:
        if is_tsumo:
            return 20, ["平和ツモ 20符固定"]
        if menzen:
            return 30, ["平和ロン 20符 + 門前ロン10符 = 30符"]

    detail = ["副底 20符"]
    fu = 20
    if menzen and not is_tsumo:
        fu += 10
        detail.append("門前ロン +10符")
    if is_tsumo:
        fu += 2
        detail.append("ツモ +2符")

    for b in blocks:
        f = block_fu(b)
        if f:
            fu += f
            detail.append(f"{b} +{f}符")

    pf = pair_fu(pair, seat_wind, round_wind, double_wind_fu)
    if pf:
        fu += pf
        detail.append(f"雀頭(役牌) +{pf}符")

    wf = WAIT_FU.get(wait, 0)
    if wf:
        fu += wf
        names = {"tanki": "単騎", "kanchan": "嵌張", "penchan": "辺張"}
        detail.append(f"{names[wait]}待ち +{wf}符")

    if not menzen and fu == 20:
        fu = 30
        detail.append("鳴き平和形のため 30符")

    rounded = round_up_10(fu)
    if rounded != fu:
        detail.append(f"切り上げ {fu} → {rounded}符")
    return rounded, detail


def limit_name(han: int) -> str | None:
    for threshold, name in LIMIT_NAMES:
        if han >= threshold:
            return name
    return None


def base_points(han: int, fu: int, *, kiriage: bool = False, yakuman: int = 0) -> tuple[int, str | None]:
    """基本点と満貫以上の呼び名を返す。"""
    if yakuman:
        names = {1: "役満", 2: "ダブル役満", 3: "トリプル役満", 4: "四倍役満", 5: "五倍役満", 6: "六倍役満"}
        return 8000 * yakuman, names.get(yakuman, f"{yakuman}倍役満")
    if han >= 13:
        return 8000, "数え役満"
    if han >= 11:
        return 6000, "三倍満"
    if han >= 8:
        return 4000, "倍満"
    if han >= 6:
        return 3000, "跳満"
    if han >= 5:
        return 2000, "満貫"
    base = fu * (2 ** (2 + han))
    if base >= 2000:
        return 2000, "満貫"
    if kiriage and ((han == 4 and fu == 30) or (han == 3 and fu == 60)):
        return 2000, "切り上げ満貫"
    return base, None


@dataclass
class Payment:
    total: int
    ron: int = 0
    from_dealer: int = 0
    from_each_child: int = 0
    text: str = ""


def payments(base: int, *, is_dealer: bool, is_tsumo: bool, honba: int = 0, riichi_sticks: int = 0) -> Payment:
    """支払いの内訳。本場・供託を含めた収入は total に入れる。"""
    bonus = honba * 300
    sticks = riichi_sticks * 1000
    if is_dealer:
        if is_tsumo:
            each = round_up_100(base * 2) + honba * 100
            return Payment(
                total=each * 3 + sticks,
                from_each_child=each,
                text=f"{each}オール",
            )
        got = round_up_100(base * 6) + bonus
        return Payment(total=got + sticks, ron=got, text=f"{got}点")
    if is_tsumo:
        ko = round_up_100(base) + honba * 100
        oya = round_up_100(base * 2) + honba * 100
        return Payment(
            total=ko * 2 + oya + sticks,
            from_dealer=oya,
            from_each_child=ko,
            text=f"{ko}/{oya}",
        )
    got = round_up_100(base * 4) + bonus
    return Payment(total=got + sticks, ron=got, text=f"{got}点")


def noten_penalty(tenpai: int) -> tuple[int, int]:
    """流局時のノーテン罰符 (テンパイ者1人あたりの収入, ノーテン者1人あたりの支払)。"""
    if tenpai in (0, 4):
        return 0, 0
    table = {1: (3000, 1000), 2: (1500, 1500), 3: (1000, 3000)}
    return table[tenpai]
