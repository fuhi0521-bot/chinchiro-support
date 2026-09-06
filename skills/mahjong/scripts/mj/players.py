"""4人のAI雀士。

判断は `skills/mahjong/references/` の基準をそのまま数値化してある。
性格の差はパラメータ（押し引きの閾値・鳴きの下限打点・リーチの条件）だけで、
判断のロジックは共通。誰が強いかを、方針の差だけで比較できるようにしてある。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from . import fast
from .safety import danger
from .tiles import DRAGONS, HONOR, NUM_TILES, YAOCHU_SET, rank_of

# 押し引きスコア表。references/push-fold.md の基準表を 0-1 に写したもの。
# キー: (シャンテン, 形の質, 打点帯) → 押す価値
FORM_GOOD, FORM_MIXED, FORM_BAD = "good", "mixed", "bad"
VAL_CHEAP, VAL_MID, VAL_MANGAN = "cheap", "mid", "mangan"

PUSH_TABLE = {
    (0, FORM_GOOD, VAL_MANGAN): 0.95,
    (0, FORM_GOOD, VAL_MID): 0.85,
    (0, FORM_GOOD, VAL_CHEAP): 0.70,
    (0, FORM_BAD, VAL_MANGAN): 0.80,
    (0, FORM_BAD, VAL_MID): 0.55,
    (0, FORM_BAD, VAL_CHEAP): 0.35,
    (1, FORM_GOOD, VAL_MANGAN): 0.65,
    (1, FORM_GOOD, VAL_MID): 0.52,
    (1, FORM_GOOD, VAL_CHEAP): 0.45,
    (1, FORM_MIXED, VAL_MANGAN): 0.45,
    (1, FORM_MIXED, VAL_MID): 0.32,
    (1, FORM_MIXED, VAL_CHEAP): 0.25,
    (1, FORM_BAD, VAL_MANGAN): 0.25,
    (1, FORM_BAD, VAL_MID): 0.15,
    (1, FORM_BAD, VAL_CHEAP): 0.12,
}


@dataclass
class Style:
    """性格を決めるパラメータ。"""

    push: float = 0.50  # これ以上の押し価値があれば押す（低い＝攻撃的）
    call_min_value: int = 3900  # 鳴く最低打点
    call_max_shanten: int = 2  # 何シャンテンまで鳴くか
    damaten_value: int = 8000  # これ以上ダマで打点があればリーチしない
    riichi_bad_wait_cheap: bool = True  # 悪形・安手でもリーチするか
    safety_weight: float = 1.0  # 押すときの安全牌への寄り
    value_weight: float = 1.0  # 打点への寄り（受け入れを削ってでも打点を取るか）
    last_place_desperation: float = 0.15  # ラス目で押しを緩める量


def value_band(points: int) -> str:
    if points >= 7700:
        return VAL_MANGAN
    if points >= 3900:
        return VAL_MID
    return VAL_CHEAP


class Player:
    """AI雀士の共通ロジック。"""

    def __init__(self, name: str, style: Style, rng=None):
        self.name = name
        self.style = style
        self.rng = rng or random.Random(hash(name) & 0xFFFF)

    # 閾値ちょうどの局面は本当に「五分」なので、決定論的に降りない。
    # 基準表が「五分」と書いている行を、実際に五分の頻度で押すようにする。
    TEMPERATURE = 0.08

    def _should_push(self, push_value: float) -> bool:
        gap = (push_value - self.style.push) / self.TEMPERATURE
        if gap > 8:
            return True
        if gap < -8:
            return False
        return self.rng.random() < 1.0 / (1.0 + math.exp(-gap))

    # ------------------------------------------------------------ 見積り

    def estimate_value(self, view) -> int:
        """自分の手の完成時打点をざっくり見積る（符は30-40符と仮定）。"""
        me = view.me
        dora = sum(me.hand[d] for d in view.dora_tiles())
        for m in me.melds:
            dora += sum(1 for t in m.tiles if t in view.dora_tiles())
        han = dora + me.aka
        if me.menzen:
            han += 2  # リーチ + ツモ/一発/裏 の期待上乗せ
        # 役牌の刻子・対子
        for t in list(DRAGONS) + [view.seat_wind, view.round_wind]:
            if me.hand[t] >= 3:
                han += 1
            elif any(m.tile == t and m.kind != "chi" for m in me.melds):
                han += 1
        # 断幺九
        if not any(me.hand[t] for t in YAOCHU_SET) and not any(
            any(x in YAOCHU_SET for x in m.tiles) for m in me.melds
        ):
            han += 1
        elif me.menzen:
            han += 0
        han = max(1, han)
        table = {1: 1300, 2: 2600, 3: 5200, 4: 7700, 5: 8000, 6: 12000, 7: 12000}
        base = table.get(han, 16000 if han < 11 else 24000)
        return base if not view.is_dealer else int(base * 1.5)

    def form_quality(self, view) -> str:
        """受け入れの広さから形の質を決める。"""
        me = view.me
        s, acc = fast.ukeire(me.hand, me.called, view.visible())
        width = sum(n for _, n in acc)
        if s == 0:
            return FORM_GOOD if width >= 5 else FORM_BAD
        if width >= 14:
            return FORM_GOOD
        if width >= 7:
            return FORM_MIXED
        return FORM_BAD

    def push_value(self, view, threat_level: float) -> float:
        me = view.me
        s = fast.shanten(me.hand, me.called)
        if s < 0:
            return 1.0
        if s >= 2:
            return 0.05
        band = value_band(self.estimate_value(view))
        form = self.form_quality(view)
        key = (s, form, band)
        if key not in PUSH_TABLE:
            key = (s, FORM_MIXED if s else FORM_BAD, band)
        v = PUSH_TABLE.get(key, 0.1)

        # 補正
        if view.turn >= 12:
            v -= 0.10
        elif view.turn <= 5:
            v += 0.05
        riichi_dealers = [p for p, _ in view.threats() if p.riichi and p.seat == view.game.dealer]
        if riichi_dealers:
            v -= 0.10
        if len(view.threats()) >= 2:
            v -= 0.12
        if me.riichi:
            v = 1.0  # リーチ後は選択肢がない
        # 着順補正: ラス目は押し、トップ目は引き
        ranks = sorted(range(4), key=lambda i: -view.game.players[i].score)
        my_rank = ranks.index(view.seat)
        if my_rank == 3:
            v += self.style.last_place_desperation
        elif my_rank == 0 and view.game.round_wind != 27:
            v -= 0.08
        return v * threat_level + (1.0 - threat_level) * 1.0

    # ------------------------------------------------------------ 打牌

    def discard(self, view):
        me = view.me
        if me.riichi:
            return (me.drawn if me.drawn is not None else self._any_tile(me)), False

        threats = view.threats()
        level = max((l for _, l in threats), default=0.0)

        # 脅威の強さに応じて押し引きを決める。リーチ（level 1.0）なら基準表そのまま、
        # 2副露（0.5）なら「よほど絶望的でなければ押す」に自然に落ちる。
        if level > 0:
            if not self._should_push(self.push_value(view, level)):
                return self._fold_discard(view, threats), False

        return self._push_discard(view, threats, level)

    def _any_tile(self, me):
        return next(t for t in range(NUM_TILES) if me.hand[t])

    def _fold_discard(self, view, threats):
        """降りる。安全度が最優先だが、同じくらい安全なら手を残す（回し打ち寄り）。

        安全牌が複数あるときに手をバラすのは、ただの損。
        安全度が並んだら受け入れの広いほうを残す。
        """
        me = view.me
        candidates = [t for t in range(NUM_TILES) if me.hand[t]]
        seen = view.seen_all()
        seen_out = view.visible()
        risks = {}
        for t in candidates:
            risk = 0.0
            for p, level in threats:
                d = danger([t], p.river_counts, seen, late=view.turn >= 8)[0]
                w = 1.5 if p.seat == view.game.dealer else 1.0
                risk += d.risk * level * w
            risks[t] = risk
        floor = min(risks.values())
        # 最安手から 1.0ポイント以内の牌を「同程度に安全」とみなす
        near = [t for t in candidates if risks[t] <= floor + 1.0]
        if len(near) == 1:
            return near[0]
        best, best_score = None, -1e9
        for t in near:
            me.hand[t] -= 1
            s = fast.shanten(me.hand, me.called)
            _, acc = fast.ukeire(me.hand, me.called, seen_out)
            width = sum(n for _, n in acc)
            me.hand[t] += 1
            score = -risks[t] * 8.0 - s * 3.0 + width * 0.12
            score += 0.3 * min(me.hand[t] - 1, 2)  # 安全牌の重ね持ちを温存
            if score > best_score:
                best, best_score = t, score
        return best

    def _push_discard(self, view, threats, level):
        """前に出る。受け入れ・打点・安全度を合わせて選ぶ。"""
        me = view.me
        hand = me.hand
        seen = view.visible()      # 受け入れ用（自分の手牌を含まない）
        seen_all = view.seen_all()  # 危険度用
        options = []
        base_shanten = None
        for t in range(NUM_TILES):
            if not hand[t]:
                continue
            hand[t] -= 1
            s = fast.shanten(hand, me.called)
            hand[t] += 1
            options.append((t, s))
        best_s = min(s for _, s in options)
        if base_shanten is None:
            base_shanten = best_s
        keep = [t for t, s in options if s == best_s]

        scored = []
        for t in keep:
            hand[t] -= 1
            _, acc = fast.ukeire(hand, me.called, seen)
            width = sum(n for _, n in acc)
            kinds = len(acc)
            hand[t] += 1

            score = width * 1.0 + kinds * 0.5

            # 打点: ドラ・赤を切るのは損
            if t in view.dora_tiles():
                score -= 6 * self.style.value_weight
            if t in me.red and me.hand[t] == 1:
                score -= 8 * self.style.value_weight
            # 役牌の対子は残す価値
            if t in DRAGONS or t == view.seat_wind or t == view.round_wind:
                if me.hand[t] >= 2:
                    score -= 5 * self.style.value_weight
            # 鳴いた後は役を確定させにいく。役に要らない牌を優先して切る
            if me.open_melds and me.yaku_goal:
                goal = me.yaku_goal
                if goal[0] == "tanyao" and t in YAOCHU_SET:
                    score += 14
                elif goal[0] == "honitsu" and t < HONOR and t // 9 != goal[1]:
                    score += 14
            # 危険度
            if threats:
                risk = 0.0
                for p, lv in threats:
                    d = danger([t], p.river_counts, seen_all, late=view.turn >= 8)[0]
                    w = 1.5 if p.seat == view.game.dealer else 1.0
                    risk += d.risk * lv * w
                score -= risk * 2.2 * self.style.safety_weight
            scored.append((score, t))
        scored.sort(reverse=True)
        tile = scored[0][1]

        # リーチ判断
        hand[tile] -= 1
        tenpai = fast.shanten(hand, me.called) == 0
        hand[tile] += 1
        declare = False
        if tenpai and me.menzen and not me.riichi:
            declare = self._want_riichi(view, tile)
        return tile, declare

    def _want_riichi(self, view, discard) -> bool:
        me = view.me
        st = self.style
        hand = me.hand
        hand[discard] -= 1
        _, acc = fast.ukeire(hand, me.called, view.visible())
        width = sum(n for _, n in acc)
        hand[discard] += 1
        value = self.estimate_value(view)

        # ダマのままで十分高い
        if value - (1300 if view.is_dealer else 1000) >= st.damaten_value and width <= 4:
            return False
        # 悪形・安手・終盤
        if not st.riichi_bad_wait_cheap and width <= 4 and value < 5200 and view.turn >= 12:
            return False
        if width == 0:
            return False
        if view.wall_left < 4:
            return False
        return True

    # ------------------------------------------------------------ 和了・鳴き

    def want_tsumo(self, view) -> bool:
        return True

    def want_ron(self, view) -> bool:
        return True

    def want_abort(self, view) -> bool:
        return True

    def want_kan(self, view, options):
        if not options:
            return None
        me = view.me
        if fast.shanten(me.hand, me.called) > 1:
            return None
        for kind, t in options:
            if kind == "ankan":
                return (kind, t)
        if fast.shanten(me.hand, me.called) == 0:
            return options[0]
        return None

    def want_call(self, view, options):
        me = view.me
        st = self.style
        if me.riichi:
            return None
        cur = fast.shanten(me.hand, me.called)
        tile = view.discarded

        best = None
        best_gain = 0
        for kind, arg in options:
            after = self._simulate_call(me, kind, arg, tile)
            if after is None:
                continue
            new_shanten, restore = after
            gain = cur - new_shanten
            restore()
            if gain <= 0:
                continue
            if gain > best_gain:
                best_gain, best = gain, (kind, arg)
        if best is None:
            return None

        if cur > st.call_max_shanten:
            return None

        # 鳴いた後に役があるか。あるなら「どの役に向かうか」を覚えておく
        goal = self._has_yaku_route(view, best, tile)
        if goal is None:
            return None
        me.yaku_goal = goal
        value = self.estimate_value(view)
        if not me.menzen:
            value = int(value * 0.6)  # 既に鳴いていれば門前の上乗せは無い
        threshold = st.call_min_value
        if view.is_dealer:
            threshold = int(threshold * 0.7)
        ranks = sorted(range(4), key=lambda i: -view.game.players[i].score)
        if ranks.index(view.seat) == 3 and view.game.round_wind != 27:
            threshold = int(threshold * 0.6)
        if value < threshold and cur > 0:
            return None
        return best

    def _simulate_call(self, me, kind, arg, tile):
        removed = []
        if kind in ("pon", "minkan"):
            need = 2 if kind == "pon" else 3
            if me.hand[tile] < need:
                return None
            me.hand[tile] -= need
            removed.append((tile, need))
        else:
            start = arg
            for k in range(3):
                if start + k != tile:
                    if not me.hand[start + k]:
                        for t, n in removed:
                            me.hand[t] += n
                        return None
                    me.hand[start + k] -= 1
                    removed.append((start + k, 1))
        called = me.called + 1
        # 鳴いた直後は14枚相当。打牌後の13枚で比べないと必ず「得」に見えてしまう。
        s = 99
        for d in range(NUM_TILES):
            if not me.hand[d]:
                continue
            me.hand[d] -= 1
            v = fast.shanten(me.hand, called)
            me.hand[d] += 1
            if v < s:
                s = v

        def restore():
            for t, n in removed:
                me.hand[t] += n

        return s, restore

    def _has_yaku_route(self, view, choice, tile):
        """鳴いた後に向かえる役を返す。無ければ None。"""
        me = view.me
        kind, arg = choice
        # 役牌の刻子
        if kind in ("pon", "minkan") and (tile in DRAGONS or tile == view.seat_wind or tile == view.round_wind):
            return ("yakuhai",)
        # 既に役牌の刻子を持っている
        for t in list(DRAGONS) + [view.seat_wind, view.round_wind]:
            if me.hand[t] >= 3 or any(m.tile == t and m.kind != "chi" for m in me.melds):
                return ("yakuhai",)
        # 断幺九
        tiles = [t for t in range(NUM_TILES) if me.hand[t]]
        called_tiles = [t for m in me.melds for t in m.tiles]
        if kind == "chi":
            called_tiles += [arg, arg + 1, arg + 2]
        else:
            called_tiles += [tile] * 3
        if all(t not in YAOCHU_SET for t in called_tiles):
            yaochu_in_hand = sum(me.hand[t] for t in YAOCHU_SET)
            # 么九牌が2枚までなら、鳴いた後に落として断幺九に向かえる
            if yaochu_in_hand <= 2:
                return ("tanyao",)
        # 染め手
        suits = {t // 9 for t in tiles if t < HONOR}
        if len(suits) <= 1 and sum(me.hand[t] for t in range(HONOR, NUM_TILES)) + sum(
            me.hand[t] for t in range(NUM_TILES) if t < HONOR and (t // 9) in suits
        ) >= 10:
            return ("honitsu", next(iter(suits)) if suits else 0)
        return None


def make_players() -> list:
    """4人の雀士。"""
    return [
        Player(
            "ゆうだい",
            Style(
                push=0.32,
                call_min_value=3900,
                call_max_shanten=2,
                damaten_value=12000,
                riichi_bad_wait_cheap=True,
                safety_weight=0.5,
                value_weight=1.4,
                last_place_desperation=0.20,
            ),
        ),
        Player(
            "なおき",
            Style(
                push=0.50,
                call_min_value=3900,
                call_max_shanten=1,
                damaten_value=8000,
                riichi_bad_wait_cheap=True,
                safety_weight=1.0,
                value_weight=1.0,
                last_place_desperation=0.15,
            ),
        ),
        Player(
            "きくちゃん",
            Style(
                push=0.45,
                call_min_value=1000,
                call_max_shanten=3,
                damaten_value=8000,
                riichi_bad_wait_cheap=True,
                safety_weight=0.8,
                value_weight=0.6,
                last_place_desperation=0.15,
            ),
        ),
        Player(
            "ゆみこ",
            Style(
                push=0.64,
                call_min_value=5200,
                call_max_shanten=1,
                damaten_value=5200,
                riichi_bad_wait_cheap=False,
                safety_weight=1.6,
                value_weight=1.0,
                last_place_desperation=0.10,
            ),
        ),
    ]
