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

from .tiles import HONOR as HONOR_IDX

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

# 早切り（1〜6巡目の【手出し】）からの距離。近いほど安全。
#
# なぜ効くのか: 「河にその牌がある」からではなく「手牌から選んで捨てた」から。
# 序盤に手から3mを切るのは、2m4m や 4m5m といったブロックを持っていない証拠になる。
# 持っていれば切らない。だからその周辺で待つ形が成立しにくい。弱い現物のようなもの。
#
# 実測で裏付けた（テンパイしている相手・8巡目以降・無スジのみ）:
#   手出しの早切りが1離れ    → 当たり牌率 6.24%
#   手出しの早切りが2離れ    → 7.35%
#   手出しの早切りが近くに無い → 11.07%
#   （ツモ切りの早切りは 8.81% / 6.75% / 9.92% でほぼ効かない。
#     引いた牌をそのまま捨てただけなので、手の中身の情報にならないため）
#
# メカニズムの直接確認:
#   手出しの早切りが隣にある  → 相手がその周辺にブロックを持っている率 51.6%
#   早切りが近くに無い       → 77.2%
EARLY_FACTOR = {1: 0.56, 2: 0.66}

# バケットで見ると、この効果は門前の相手に強く、副露している相手には弱い。
#   門前   1離れ 5.21% / 近くに無い 9.65%  → -46%
#   1副露  1離れ 8.51% / 近くに無い 9.15%  → -7%
#
# それで「副露者には適用しない」「弱く適用する」を試したが、
# **未学習データでは全部が悪化した**（AUC 0.6527 → 0.6464〜0.6496）。
# バケットの差は標本のばらつきの範囲だったとみて、全員に同じ係数を掛ける。
#
# 「中盤以降の手出しの隣は危険（またぎスジ）」も試したが AUC +0.0002 で無意味だった。
# 実装しない。

# 【検討して見送ったもの】鳴いた直後に何を打ったか
#
# 生の信号は本物で、未学習データでもはっきり出る:
#   鳴き直後に中張牌を打った → テンパイ率 48.4% (n=773)
#   鳴き直後に么九牌を打った → テンパイ率 23.2% (n=849)   2.1倍の差
#
# 理屈も通っている。鳴いた人は手牌が 13-3k 枚に減っているうえ、
# 鳴いた直後に切る牌は「要らないと決めたもの」なので情報量が大きい。
# 中張牌を切れるということは、その周辺が要らないと決まった＝形ができている。
#
# それでも **上のテーブルへの上乗せとしては改善しなかった**。
#   補正なし                          AUC 0.9334 / Brier 0.04977
#   常に 中張×1.38 么九×0.80            AUC 0.9324 / Brier 0.05183
#   予測<0.30 のときだけ 中張×1.7 么九×0.8  AUC 0.9331 / Brier 0.04971
#
# テーブルが (副露数 × 巡目 × 直近3打のツモ切り数) で引いており、
# **同じ情報を手出し／ツモ切りのパターンから既に拾っている**ため。
# 上乗せすると較正だけ壊れる。
#
# 鳴いた直後の打牌は `PlayerState.after_call_discards` に記録してあるので、
# テーブルを4つ目のキーで作り直すなら、そこから使える。

EARLY_TURNS = 6  # 「早切り」とみなす巡目

# ---------------------------------------------------------------- 手役読み
#
# 染め手と対々和の相手は、危険度の並びが **根本から** 変わる。
# ここは統計ではなく構造で決まる。
#
#   混一色の相手は、その色と字牌でしか待てない。他の色で待つと役が消える。
#   対々和の相手の待ちはシャンポンか単騎。両面が無いのでスジが意味を持たない。
#
# だから測って決めるのではなく、まず「そう打っている相手か」を見分ける。
# 見分けが正しければ、あとは論理的に決まる。

# 係数は「検出器が反応した局面」の実測から決めた（染め場・200局）。
#   その色 23.93% / 他の色 12.35% / 場の平均 8.5%
#
# 【重要】理屈のうえでは「染め手は他の色で待てない」ので他の色は当たらないはず。
# 実際、**検出器の精度が100%でない以上そうはならない**。反応した局面のうち
# 本物の染め手は半分ほどで、残りはふつうの手。だから他の色も普通に危険なまま。
# 最初は他の色を 0.30倍（＝ほぼ安全）にしていたが、これは危険な誤りだった。
#
# 読みを危険度に反映するときの一般則:
#   **「その読みが当たっている確率」で薄めること。** 理屈が正しくても、
#   見分けが半分しか当たらないなら、効果も半分にしかならない。
HONITSU_IN = 2.0       # 染めている色の牌（実測 23.93% ÷ 素の約12% ≒ 2.0）
HONITSU_HONOR = 1.0    # 字牌（この場では待ちが観測されず、根拠が無いので触らない）
HONITSU_OUT = 1.05     # 他の色（**安全にはならない**）

TOITOI_SUJI = 1.0      # 対々和にスジは効かない（両面待ちが無い）
TOITOI_HONOR = 1.6     # 字牌のシャンポン・単騎が増える


def suit_lean(player):
    """その相手が染めている色を推定する。無ければ None。

    **証拠は厳しく取る。** 弱い証拠で染め手と決めつけると、
    危険度の並びを丸ごとひっくり返してしまうので、外したときの損が大きい。

    シミュレータの正解（相手の手牌が1色＋字牌か）と突き合わせて選んだ:

    | ルール | 適合率 | 再現率 |
    |---|---|---|
    | 2副露が1色（弱い） | 10.2% | 40.8% |
    | 2副露が1色 + その色を1枚も切っていない | 54.5% | 19.7% |
    | **3副露が1色** | **100.0%** | 24.3% |
    | **採用: 3副露 or (2副露 + その色不切 + 他色6枚以上)** | **77.4%** | 27.0% |

    「その色を1枚も切っていない」がいちばん効く条件。
    染めている人はその色を絶対に手放さない。

    逆に「中盤以降に他の色の中張牌を手出しする」は **効かなかった**（適合率0%）。
    染め手の人は序盤のうちに他の色を切り終えているので、
    中盤以降に切る他色はもう残っていない。
    """
    if len(player.melds) < 2:
        return None
    suits = set()
    n_suit = 0
    for m in player.melds:
        for t in m.tiles:
            if t < HONOR_IDX:
                suits.add(t // 9)
                n_suit += 1
    if len(suits) != 1 or n_suit < 3:
        return None
    s = suits.pop()
    if len(player.melds) >= 3:
        return s                      # 3副露が1色なら、この場では例外なく染め手だった
    in_disc = off_any = 0
    for t in player.river:
        if t >= HONOR_IDX:
            continue
        if t // 9 == s:
            in_disc += 1
        else:
            off_any += 1
    return s if in_disc == 0 and off_any >= 6 else None


def toitoi_lean(player) -> bool:
    """対々和に向かっていそうか。ポン・カンだけで2つ以上鳴いていること。"""
    if len(player.melds) < 2:
        return False
    return all(m.kind != "chi" for m in player.melds)

# その牌が **自分の手牌と本人の河を除いて** 何枚見えているか。
# 実測（400局・82418標本・テンパイしている相手のみ）:
#   数牌  0枚見え 10.04% / 1枚 6.09% / 2枚 4.87% / 3枚 2.30%
#   字牌  0枚見え  1.19% / 1枚 0.17% / 2枚 0.00% / 3枚 0.00%
#
# 理由は2つある。
#   1. シャンポン・単騎はその牌そのものを抱えている必要がある。
#      3枚見えていればシャンポンは不可能
#   2. **他家の河に切れている牌は、相手がテンパイしていたなら通っている**。
#      通っていれば相手はフリテンで、その牌では和了れない
#
# 2つ目のほうが効きが大きい。リーチ後に通った牌は `PlayerState.passed` で
# 別に処理しているので、ここに残るのは「ダマの相手」「リーチ前に通った牌」の分。
#
# 一度入れると **その牌を選んで切るようになる**ので、条件付きの当たり率は上がる。
# 入れた後の方策でもう一度測り直した値がこれ（300局・62130標本）:
#   数牌 0枚 9.84% / 1枚 7.42% / 2枚 5.52% / 3枚 4.34%
# 最初の測定（枚数を見ない方策のもと）より効果は小さい。選択の効果ぶん。
#
# 係数は平均が変わらないように正規化してある（押し引きの閾値を動かさないため）。
SEEN_FACTOR = (1.12, 0.84, 0.63, 0.49)

# 「リーチ後に他家が切って通った牌」を現物として扱うか。
# 実装漏れを直したときに入れた。切れるのは検証（risk_fit.py --ablate）のときだけ。
USE_PASSED = True
HONOR_SEEN_FACTOR = (1.00, 0.20, 0.10, 0.10)


def _rank_class(t: int) -> int:
    r = t % 9 + 1
    return min(r, 10 - r)


def wait_risk(player, tile: int, seen=None, mine=None) -> float:
    """その牌が相手の当たり牌である確率(%)を、河から見積る。

    放銃率ではない。放銃率 ≈ wait_risk × テンパイ確率。

    seen は自分の手牌も含めた既知の枚数、mine は自分の手牌の枚数。
    mine を渡すと「場に何枚切れているか」を正しく数えられる。
    """
    from .tiles import HONOR

    if player.river_counts[tile] or (USE_PASSED and tile in player.passed):
        # 本人が切った牌（現物）と、リーチ後に他家が切って通った牌。
        # どちらも当たらない。後者は見落とされやすいが、局が進むほど枚数が増える
        return GENBUTSU_RISK

    # 場に何枚切れているか（自分の手牌と、本人の河は除く）
    gone = 0
    if seen is not None:
        gone = seen[tile] - player.river_counts[tile]
        if mine is not None:
            gone -= mine[tile]
        gone = min(3, max(0, gone))

    lean = suit_lean(player)
    toitoi = toitoi_lean(player)

    if tile >= HONOR:
        r = HONOR_RISK * HONOR_SEEN_FACTOR[gone]
        if lean is not None:
            r *= HONITSU_HONOR
        elif toitoi:
            r *= TOITOI_HONOR
        return r

    if lean is not None and tile // 9 != lean:
        # 染めている色でない数牌。役が消えるので当たらない
        return RANK_RISK[_rank_class(tile)] * HONITSU_OUT * SEEN_FACTOR[gone]

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
    if toitoi:
        # 対々和の待ちはシャンポンか単騎。両面が無いのでスジは意味を持たない
        risk *= TOITOI_SUJI
    elif both:
        risk *= SUJI_FACTOR
    elif half:
        risk *= HALF_SUJI_FACTOR
    if lean is not None:
        risk *= HONITSU_IN

    # 早切りの周辺は、無スジでも安全寄り。ただし【手出し】に限る
    dist = 9
    for i, d in enumerate(player.river[:EARLY_TURNS]):
        if d >= HONOR or d // 9 != tile // 9:
            continue
        if i >= len(player.tedashi) or not player.tedashi[i]:
            continue  # ツモ切りは手の中身の情報にならない
        gap = abs((d % 9) - (tile % 9))
        if 1 <= gap <= 2:
            dist = min(dist, gap)
    risk *= EARLY_FACTOR.get(dist, 1.0)
    risk *= SEEN_FACTOR[gone]
    return risk
