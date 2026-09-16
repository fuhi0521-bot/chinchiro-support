"""放銃危険度の見積り。

厳密なベイズ推定ではなく、実戦で使う「序列」を機械的に出すための道具。
数値は天鳳・雀魂の統計から広く知られている目安（リーチ1件に対する放銃率）で、
場況で動く。絶対値ではなく牌どうしの並び順として使うこと。
"""

from __future__ import annotations

from dataclasses import dataclass

from .tiles import HONOR, NUM_TILES, rank_of, suit_of, tile_str

GENBUTSU = "現物"
SUJI = "スジ"
NOCHANCE = "ノーチャンス"
ONECHANCE = "ワンチャンス"
MUSUJI = "無筋"
HONOR_LIVE = "生牌の字牌"


@dataclass
class Danger:
    tile: int
    label: str
    risk: float
    note: str = ""

    def __str__(self) -> str:
        n = f"  {self.note}" if self.note else ""
        return f"{tile_str(self.tile):<4} {self.label:<12} 約{self.risk:.1f}%{n}"


def _seen_counts(*groups) -> list[int]:
    seen = [0] * NUM_TILES
    for g in groups:
        if not g:
            continue
        for t, n in enumerate(g):
            seen[t] += n
    return seen


def _suji_state(t: int, river_counts) -> str:
    """両スジ / 片スジ / 無スジ を返す（数牌のみ）。"""
    n = rank_of(t)
    base = t - (n - 1)
    lower = river_counts[base + n - 4] if n >= 4 else None
    upper = river_counts[base + n + 2] if n <= 6 else None
    if 1 <= n <= 3:
        return "スジ" if upper else "無スジ"
    if 7 <= n <= 9:
        return "スジ" if lower else "無スジ"
    both = bool(lower) and bool(upper)
    if both:
        return "両スジ"
    if lower or upper:
        return "片スジ"
    return "無スジ"


def _wall_state(t: int, seen) -> str:
    """ノーチャンス / ワンチャンス / なし。両面待ちが物理的に成立するかで判定。"""
    if t >= HONOR:
        return ""
    n = rank_of(t)
    base = t - (n - 1)

    def remaining(rank: int) -> int:
        if not 1 <= rank <= 9:
            return 0
        return max(0, 4 - seen[base + rank - 1])

    low = min(remaining(n - 2), remaining(n - 1)) if n >= 3 else 0
    high = min(remaining(n + 1), remaining(n + 2)) if n <= 7 else 0
    best = max(low, high)
    if best == 0:
        return NOCHANCE
    if best == 1:
        return ONECHANCE
    return ""


# その牌が場に何枚切れているかによる倍率 ［実測］
#
# 700局・123,950標本。テンパイしていて **かつロンで和了れる**（フリテンでない）
# 相手に対する当たり牌率。「切れている枚数」は
# **自分の手牌と本人の河を除いた数**。
#
#   0枚(生牌) 9.79%  →  1.00
#   1枚       6.94%  →  0.71
#   2枚       3.48%  →  0.36
#   3枚       2.45%  →  0.25
#
# **2枚切れの無筋は中スジ（0.54倍）より安全。** 3枚切れならもっと安全。
# 効いている理由は2つ。
#   1. シャンポン・単騎はその牌そのものを抱えている必要がある
#   2. 他家の河に切れている牌は、相手がテンパイしていたなら通っている
#      （通っていればフリテンで和了れない）
#
# 字牌にはもともと入っていたのに、**数牌には入っていなかった**。
# 実測でいちばん効く要素なので、位置とスジだけの序列は並び順を外す。
#
# ［訂正］以前ここには 400局の測定から (1.0, 0.61, 0.49, 0.23) と書いてあった。
# その測定はフリテンの相手も当たりに数えていた（risk_fit.can_ron を参照）。
# ただし再測定で動いた主因はフリテンではなく、**方策がその後変わったこと**。
GONE_FACTOR = (1.0, 0.71, 0.36, 0.25)


def danger(candidates, river_counts, seen_counts=None, *, late: bool = True,
           mine=None) -> list[Danger]:
    """候補牌を安全な順に並べて返す。

    river_counts: その相手の捨て牌（リーチ後に通った牌を含む）の枚数配列
    seen_counts : 場に見えている全ての牌（自分の手牌・ドラ表示・全員の河）
    mine        : 自分の手牌の枚数配列。渡すと「切れている枚数」を正しく数える。
                  省略すると、いま検討している1枚ぶんだけを引く
    """
    # seen_counts には河も含めて渡す想定。渡されなければ河だけを既知とする。
    seen = [max(a, b) for a, b in zip(seen_counts, river_counts)] if seen_counts else list(river_counts)

    def gone_outside(t: int) -> int:
        """自分の手牌と本人の河を除いた、場に見えている枚数（0-3）。"""
        held = mine[t] if mine is not None else 1
        return max(0, min(3, seen[t] - river_counts[t] - held))
    out: list[Danger] = []
    for t in candidates:
        if river_counts[t]:
            out.append(Danger(t, GENBUTSU, 0.0, "通っている"))
            continue
        if t >= HONOR:
            gone = seen[t]
            if gone >= 3:
                out.append(Danger(t, "字牌3枚見え", 0.2, "単騎のみ"))
            elif gone == 2:
                out.append(Danger(t, "字牌2枚切れ", 0.6, "ほぼ通る"))
            elif gone == 1:
                out.append(Danger(t, "字牌1枚切れ", 1.5, "シャンポン・単騎のみ"))
            else:
                out.append(Danger(t, HONOR_LIVE, 3.0 if late else 2.0, "国士・シャンポンに注意"))
            continue

        wall = _wall_state(t, seen)
        suji = _suji_state(t, river_counts)
        n = rank_of(t)
        if n in (4, 5, 6):
            base_risk = 6.0
        elif n in (3, 7):
            base_risk = 5.0
        elif n in (2, 8):
            base_risk = 4.5
        else:
            base_risk = 4.0

        if suji == "両スジ":
            out.append(Danger(t, "両スジ", 2.0, "残るは嵌張・辺張・単騎"))
        elif suji == "スジ":
            out.append(Danger(t, "スジ", 3.0, "スジ引っかけに注意"))
        elif suji == "片スジ":
            out.append(Danger(t, "片スジ", base_risk * 0.7, "半分だけ消えている"))
        elif wall == NOCHANCE:
            out.append(Danger(t, NOCHANCE, 1.5, "両面では待てない"))
        elif wall == ONECHANCE:
            out.append(Danger(t, ONECHANCE, 2.5, "両面の可能性は残る"))
        else:
            out.append(Danger(t, f"{MUSUJI}{n}", base_risk))

        if wall == NOCHANCE and out[-1].label not in (NOCHANCE,):
            out[-1].note = (out[-1].note + " / 壁あり").strip(" /")

        # 場に何枚切れているか。実測でいちばん効く要素（GONE_FACTOR 参照）。
        # スジ・壁の判定とは別の理屈（フリテンと、シャンポン・単騎の枚数）なので
        # 掛け合わせる。現物はここに来ない。
        g = gone_outside(t)
        if g:
            out[-1].risk *= GONE_FACTOR[g]
            out[-1].note = (out[-1].note + f" / {g}枚切れ").strip(" /")

    out.sort(key=lambda d: (d.risk, -rank_of(d.tile) if d.tile < HONOR else 0))
    return out
