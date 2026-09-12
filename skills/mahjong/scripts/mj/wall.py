"""山読み — 「その牌はまだ山に何枚あるか」を見積もる。

場に見えていない牌は、**相手の手の中**か **山（＋王牌）** のどちらかにある。
見えている枚数を引くだけの受け入れ計算は、この2つを区別しない。
区別できると何が変わるか:

  - 同じ「残り4枚」の待ちでも、相手が抱えていそうな牌なら実際には出てこない
  - 序盤に切られた牌の近くは、誰も持っていないので山に濃い
  - 誰かが染めている色は山に薄い

ここでの見積もりは、シミュレータの正解（実際の山の中身）に対して
mj/wall_fit.py で較正してある。係数はすべて実測値。

用語:
  unseen[t] … 4 - 見えている枚数。相手の手＋山＋王牌のどこかにある
  held[t]   … そのうち相手が抱えていると推定される枚数
  wall[t]   … unseen[t] - held[t]。「山に残っている」期待枚数
"""

from __future__ import annotations

from .tiles import NUM_TILES, HONOR

# --- 抱えられやすさの係数（wall_fit.py で実測して決めた） -------------------

# 数牌の位置による重み。中張牌ほど手に残る
RANK_HOLD = (0.89, 1.02, 1.07, 1.04, 1.06, 1.04, 1.07, 1.02, 0.89)
HONOR_HOLD = 0.39          # 字牌は用がなければ早く切られる
DORA_HOLD = 1.55           # ドラは抱える
DORA_NEIGHBOR_HOLD = 1.18  # ドラの隣（ドラ受け）も抱える

EARLY_TURNS = 6            # 「序盤の手出し」とみなす巡目
EARLY_SELF = 0.30          # その牌そのもの（＝現物）を抱えている率の下がり方
EARLY_NEAR = 0.62          # ±1 の牌
EARLY_FAR = 0.80           # ±2 の牌

SUIT_CONC_GAIN = 0.0       # 色の偏りをどれだけ重みに反映するか（実測で 0 が最良）
SUIT_CONC_CAP = 1.9        # その上限

# 見えていない枚数そのものが証拠になる。実測（wall_fit.py）:
#   場に3枚見えている牌の4枚目 … 実際に山にある期待枚数 0.78（均等割りの予想は 0.51）
#   1枚も見えていない牌        … 4枚のうち山にあるのは 2.13（均等割りの予想は 2.38）
# つまり「まだ場に出ていない牌」ほど誰かが抱えている。
# 待ちを選ぶときの直感「4枚残っているから広い」は、その分だけ割り引いて考える。
UNSEEN_HOLD = (1.0, 0.55, 0.83, 1.11, 1.15)


def _dora_sets(view):
    dora = set(view.dora_tiles())
    near = set()
    for d in dora:
        if d < HONOR:
            r = d % 9
            if r > 0:
                near.add(d - 1)
            if r < 8:
                near.add(d + 1)
    return dora, near - dora


def _early_relief(player, weight):
    """その相手が序盤に手出しした牌の周辺を「持っていない」側に倒す。

    weight は牌ごとの倍率。手出しだけを見る（ツモ切りは情報がない）。
    """
    for i, t in enumerate(player.river[:EARLY_TURNS]):
        if i >= len(player.tedashi) or not player.tedashi[i]:
            continue
        weight[t] *= EARLY_SELF
        if t >= HONOR:
            continue
        r = t % 9
        for d, f in ((1, EARLY_NEAR), (2, EARLY_FAR)):
            if r - d >= 0:
                weight[t - d] *= f
            if r + d <= 8:
                weight[t + d] *= f


def _suit_concentration(player):
    """その相手が集めていそうな色を推定して、色ごとの倍率を返す。

    「染めている相手の色は山に薄い」を数値にしたもの。ただし証拠は厳しく取る。

    最初は「河に切った色の割合が低いほど集めている」という緩い判定にしていたが、
    実測すると**外した方が当たった**（同枚数判別 68.5% → 69.9%）。
    ふつうの手でも手役の関係で切る色は偏るので、河の偏りだけでは
    「集めている」証拠にならない。副露が一色に寄っている相手だけに絞る。
    """
    out = [1.0, 1.0, 1.0]
    if SUIT_CONC_GAIN <= 0 or not player.melds:
        return out
    by_suit = [0, 0, 0]
    honors = 0
    for m in player.melds:
        for t in m.tiles:
            if t >= HONOR:
                honors += 1
            else:
                by_suit[t // 9] += 1
    total = sum(by_suit) + honors
    best = max(range(3), key=lambda s: by_suit[s])
    # 副露が「1色＋字牌」だけで、その色が2枚以上あるときだけ染めとみなす
    if by_suit[best] >= 2 and by_suit[best] + honors == total:
        out[best] = min(SUIT_CONC_CAP, 1.0 + SUIT_CONC_GAIN)
    return out


def hold_weights(view) -> list[float]:
    """牌ごとの「相手に抱えられていそうな度合い」。1.0 が平均。"""
    w = [0.0] * NUM_TILES
    for t in range(NUM_TILES):
        w[t] = HONOR_HOLD if t >= HONOR else RANK_HOLD[t % 9]
    dora, near = _dora_sets(view)
    for t in dora:
        w[t] *= DORA_HOLD
    for t in near:
        w[t] *= DORA_NEIGHBOR_HOLD

    others = view.others
    per = [[1.0] * NUM_TILES for _ in others]
    for k, p in enumerate(others):
        _early_relief(p, per[k])
        suit = _suit_concentration(p)
        for t in range(HONOR):
            per[k][t] *= suit[t // 9]
    # 相手ごとの倍率は平均を取る（誰か1人が持っていれば山にはない）
    n = len(others) or 1
    for t in range(NUM_TILES):
        w[t] *= sum(per[k][t] for k in range(n)) / n
    return w


def wall_counts(view, seen=None) -> list[float]:
    """牌ごとに「山（＋王牌）に残っている期待枚数」を返す。

    合計は必ず「見えていない枚数 - 相手の手牌の合計枚数」に一致する。
    """
    if seen is None:
        seen = view.seen_all()
    unseen = [4 - seen[t] for t in range(NUM_TILES)]
    total_unseen = sum(unseen)
    hidden = sum(sum(p.hand) for p in view.others)
    if total_unseen <= 0:
        return [0.0] * NUM_TILES
    hidden = min(hidden, total_unseen)

    w = hold_weights(view)
    mass = [unseen[t] * w[t] * UNSEEN_HOLD[unseen[t]] for t in range(NUM_TILES)]
    s = sum(mass)
    if s <= 0:
        f = hidden / total_unseen
        return [unseen[t] * (1 - f) for t in range(NUM_TILES)]

    out = [0.0] * NUM_TILES
    over = 0.0
    for t in range(NUM_TILES):
        held = hidden * mass[t] / s
        if held > unseen[t]:            # 4枚以上は抱えられない
            over += held - unseen[t]
            held = unseen[t]
        out[t] = unseen[t] - held
    # あふれた分を、まだ余裕のある牌に配り直す
    if over > 0:
        room = sum(out)
        if room > 0:
            scale = max(0.0, 1.0 - over / room)
            out = [x * scale for x in out]
    return out


def flat_fraction(view, seen=None) -> float:
    """均等割りしたときの「1枚あたり山にある確率」。山読みの比較対象。"""
    if seen is None:
        seen = view.seen_all()
    total = sum(4 - seen[t] for t in range(NUM_TILES))
    if total <= 0:
        return 0.0
    hidden = min(sum(sum(p.hand) for p in view.others), total)
    return 1.0 - hidden / total


def live_fraction(view) -> float:
    """山に残っている牌のうち、実際に引ける割合（王牌14枚は引けない）。"""
    dead = 14 - len(view.game.dora_indicators)
    left = view.wall_left
    total = left + dead
    return left / total if total else 0.0


def wait_liveness(view, tiles, seen=None) -> float:
    """待ち牌の集合について「山にある期待枚数」を合計する。"""
    wall = wall_counts(view, seen)
    return sum(wall[t] for t in tiles)


__all__ = ["wall_counts", "hold_weights", "wait_liveness", "live_fraction",
           "flat_fraction"]
