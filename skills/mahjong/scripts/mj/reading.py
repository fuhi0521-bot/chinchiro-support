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


# --- 河から当たり牌を推定する ------------------------------------------------
#
# 下の数値は 48,692 局面の実測（テンパイしている相手について、候補牌が実際に
# 当たり牌だったかを記録した）。単位は「その牌が当たり牌である確率(%)」。
# 放銃率ではないので、テンパイ確率を掛けて使う。
#
#   全体の当たり牌率 7.73%
#   現物 0.58% / 字牌(非現物) 1.14% / スジ 5.24% / 片スジ 8.97% / 無スジ 10.45%

# 牌の位置ごとの基準値（非現物・数牌）
RANK_RISK = {1: 4.62, 2: 7.98, 3: 11.45, 4: 10.41, 5: 11.08}
HONOR_RISK = 1.14
GENBUTSU_RISK = 0.0

# スジの効き方（無スジを1.0としたときの倍率）
SUJI_FACTOR = 0.50   # 両側が切れている
HALF_SUJI_FACTOR = 0.86

# 早切り（1〜6巡目の打牌）からの距離。近いほど安全
#   実測: 1離れ 7.21% / 2離れ 9.25% / 近くに無い 11.73%
EARLY_FACTOR = {1: 0.61, 2: 0.79}

EARLY_TURNS = 6  # 「早切り」とみなす巡目


def _rank_class(t: int) -> int:
    r = t % 9 + 1
    return min(r, 10 - r)


def wait_risk(player, tile: int, seen=None) -> float:
    """その牌が相手の当たり牌である確率(%)を、河から見積る。

    放銃率ではない。放銃率 ≈ wait_risk × テンパイ確率。
    """
    from .tiles import HONOR

    if player.river_counts[tile]:
        return GENBUTSU_RISK
    if tile >= HONOR:
        # 字牌は切れている枚数で下がる
        gone = player.river_counts[tile] + (seen[tile] if seen else 0)
        return HONOR_RISK * (0.5 if gone >= 1 else 1.0)

    r = tile % 9 + 1
    base_idx = tile - (r - 1)
    risk = RANK_RISK[_rank_class(tile)]

    lo = player.river_counts[base_idx + r - 4] if r >= 4 else 0
    hi = player.river_counts[base_idx + r + 2] if r <= 6 else 0
    if 1 <= r <= 3:
        both = bool(hi)
        half = False
    elif 7 <= r <= 9:
        both = bool(lo)
        half = False
    else:
        both = bool(lo) and bool(hi)
        half = bool(lo) != bool(hi)
    if both:
        risk *= SUJI_FACTOR
    elif half:
        risk *= HALF_SUJI_FACTOR

    # 早切りの周辺は、無スジでも安全寄り
    dist = 9
    for i, d in enumerate(player.river):
        if i >= EARLY_TURNS or d >= HONOR or d // 9 != tile // 9:
            continue
        gap = abs((d % 9) - (tile % 9))
        if 1 <= gap <= 2:
            dist = min(dist, gap)
    risk *= EARLY_FACTOR.get(dist, 1.0)
    return risk
