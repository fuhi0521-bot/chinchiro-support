"""相手の手を読む。

数字は手書きの推測ではなく、このエンジンで 133,994 局面ぶんの
「相手の実際のシャンテン」を記録して作った実測値。

  収集: python3 skills/mahjong/scripts/mj/reading_fit.py

いちばん効くのは **手出し／ツモ切り** で、副露数より強い信号だった。
1副露でツモ切り3連続（テンパイ率 0.69）は、2副露で手出しが続いている相手（0.25）より危険。

注意: これは「このシミュレータのAI」を読むための表であって、
人間の統計ではない。人間相手の数字は references/reading.md を見ること。
"""

from __future__ import annotations

# 全体のテンパイ率（リーチ者を除く）。表に無いときの最後の受け皿
PRIOR = 0.085

# (副露数0-2, 巡目バケツ0-4, 直近3打のツモ切り数0-3) → テンパイ確率
TENPAI_FULL = {(0, 0, -1): 0.001,
 (0, 0, 0): 0.007,
 (0, 0, 1): 0.009,
 (0, 0, 2): 0.011,
 (0, 0, 3): 0.015,
 (0, 1, 0): 0.016,
 (0, 1, 1): 0.022,
 (0, 1, 2): 0.034,
 (0, 1, 3): 0.035,
 (0, 2, 0): 0.011,
 (0, 2, 1): 0.033,
 (0, 2, 2): 0.059,
 (0, 2, 3): 0.052,
 (0, 3, 0): 0.016,
 (0, 3, 1): 0.03,
 (0, 3, 2): 0.069,
 (0, 3, 3): 0.116,
 (0, 4, 0): 0.036,
 (0, 4, 1): 0.042,
 (0, 4, 2): 0.04,
 (0, 4, 3): 0.062,
 (1, 0, -1): 0.06,
 (1, 0, 0): 0.131,
 (1, 0, 1): 0.174,
 (1, 0, 2): 0.178,
 (1, 0, 3): 0.263,
 (1, 1, 0): 0.251,
 (1, 1, 1): 0.307,
 (1, 1, 2): 0.361,
 (1, 1, 3): 0.461,
 (1, 2, 0): 0.155,
 (1, 2, 1): 0.257,
 (1, 2, 2): 0.439,
 (1, 2, 3): 0.627,
 (1, 3, 0): 0.095,
 (1, 3, 1): 0.2,
 (1, 3, 2): 0.424,
 (1, 3, 3): 0.693,
 (1, 4, 0): 0.077,
 (1, 4, 1): 0.157,
 (1, 4, 2): 0.304,
 (1, 4, 3): 0.713,
 (2, 0, 0): 0.302,
 (2, 0, 1): 0.262,
 (2, 0, 2): 0.351,
 (2, 1, 0): 0.353,
 (2, 1, 1): 0.384,
 (2, 1, 2): 0.5,
 (2, 1, 3): 0.552,
 (2, 2, 0): 0.252,
 (2, 2, 1): 0.515,
 (2, 2, 2): 0.647,
 (2, 2, 3): 0.654,
 (2, 3, 0): 0.187,
 (2, 3, 1): 0.322,
 (2, 3, 2): 0.615,
 (2, 3, 3): 0.663,
 (2, 4, 0): 0.159,
 (2, 4, 1): 0.273,
 (2, 4, 2): 0.347,
 (2, 4, 3): 0.628}

# 手出し情報が無いとき用（副露数 × 巡目）
TENPAI_MT = {(0, 0): 0.005,
 (0, 1): 0.024,
 (0, 2): 0.038,
 (0, 3): 0.044,
 (0, 4): 0.04,
 (1, 0): 0.15,
 (1, 1): 0.335,
 (1, 2): 0.379,
 (1, 3): 0.353,
 (1, 4): 0.307,
 (2, 0): 0.411,
 (2, 1): 0.537,
 (2, 2): 0.641,
 (2, 3): 0.513,
 (2, 4): 0.425}

# さらに情報が無いとき用（副露数だけ）
TENPAI_M = {0: 0.016, 1: 0.31, 2: 0.555}


def turn_bucket(turn: int) -> int:
    if turn <= 6:
        return 0
    if turn <= 9:
        return 1
    if turn <= 12:
        return 2
    if turn <= 15:
        return 3
    return 4


def recent_tsumogiri(player, n: int = 3) -> int:
    """直近n打のうちツモ切りが何回か。打数が足りなければ -1。"""
    if len(player.tedashi) < n:
        return -1
    return n - sum(player.tedashi[-n:])


def tenpai_probability(player, turn: int, *, use_tedashi: bool = True) -> float:
    """その相手がテンパイしている確率。

    use_tedashi=False にすると副露数と巡目だけで読む（手出しを見ない打ち手用）。
    """
    if player.riichi:
        return 1.0
    m = min(player.open_melds, 2)
    t = turn_bucket(turn)
    if use_tedashi:
        g = recent_tsumogiri(player)
        v = TENPAI_FULL.get((m, t, g))
        if v is not None:
            return v
    v = TENPAI_MT.get((m, t))
    if v is not None:
        return v
    return TENPAI_M.get(m, PRIOR)


def heuristic_probability(player, turn: int, round_wind: int, seat_wind_of) -> float:
    """手書きの読み（副露数と巡目だけを見る、references/reading.md の表）。

    実測テーブルと比べるための対照。
    """
    from .tiles import DRAGONS

    if player.riichi:
        return 1.0
    opens = player.open_melds
    level = 0.0
    if opens >= 3:
        level = 0.9
    elif opens == 2:
        level = 0.5 if turn < 12 else 0.85
    elif opens == 1 and turn >= 13:
        level = 0.25
    if opens and any(
        m.tile in DRAGONS or m.tile == seat_wind_of(player.seat) or m.tile == round_wind
        for m in player.melds
        if m.kind != "chi"
    ):
        level = min(1.0, level + 0.15)
    return level


def oracle_probability(player, called_shanten) -> float:
    """相手の手牌を見て答える。読みの上限を測るための反則手。"""
    return 1.0 if called_shanten == 0 else 0.0
