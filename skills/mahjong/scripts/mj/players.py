"""4人のAI雀士。

判断は `skills/mahjong/references/` の基準をそのまま数値化してある。
性格の差はパラメータ（押し引きの閾値・鳴きの下限打点・リーチの条件）だけで、
判断のロジックは共通。誰が強いかを、方針の差だけで比較できるようにしてある。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from . import fast, placement, reading
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
    awareness: str = "none"  # 点数状況を見る範囲: none / allast / south / always
    top_caution: float = 0.0  # トップ目のとき押しを引く量
    low_aggression: float = 0.0  # 下位のとき押しを足す量（ラス目に満額、3着に半分）
    allast_conditions: bool = False  # オーラスの条件計算（ダマ・見逃し・形式テンパイ）を使うか
    # 相手のテンパイをどう読むか
    #   heuristic = 手書きの副露数×巡目 / stats = 実測表（手出しを見ない）
    #   tedashi   = 実測表（手出し・ツモ切り込み） / oracle = 相手の手牌が見える（上限測定用）
    reading: str = "heuristic"
    chase_honitsu: bool = True  # 染め手（混一色・清一色）を狙うか
    # 河から当たり牌を推定するか。現物・スジに加えて「早切りの周辺は安全」を使う。
    # 安全の根拠がある牌なら無筋でも切り、根拠が無ければスジでも避ける。
    river_read: bool = False
    # 鳴いて染めに向かう最低枚数（その色＋字牌）。大きいほど選択的。
    # 2000半荘の実験で 11 が最良だった（9だと雑に染めて順位が下がる）
    honitsu_min: int = 11


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
        self.rng = rng or random.Random(sum(ord(c) * (i + 1) for i, c in enumerate(name)))

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

    def estimate_value(self, view, dama: bool = False) -> int:
        """自分の手の完成時打点をざっくり見積る（符は30-40符と仮定）。

        dama=True なら、リーチ・一発・裏ドラの上乗せを外した「ダマのままの打点」。
        """
        me = view.me
        dora = sum(me.hand[d] for d in view.dora_tiles())
        for m in me.melds:
            dora += sum(1 for t in m.tiles if t in view.dora_tiles())
        han = dora + me.aka
        if me.menzen and not dama:
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

    # ------------------------------------------------------- 点数状況を見る

    def _aware(self, view) -> bool:
        """いま点数状況を見るべき局面か。"""
        a = self.style.awareness
        if a == "always":
            return True
        if a == "south":
            return view.round_wind != 27
        if a == "allast":
            return view.is_all_last
        return False

    # ------------------------------------------------------------ 読み

    THREAT_FLOOR = 0.12  # これ未満のテンパイ確率は無視する（計算量と雑音のため）

    def _reads(self, view):
        """(相手, テンパイ確率) のリスト。style.reading で読み方が変わる。"""
        mode = self.style.reading
        out = []
        for p in view.others:
            if mode == "oracle":
                prob = 1.0 if (p.riichi or fast.shanten(p.hand, p.called) == 0) else 0.0
            elif mode == "stats":
                prob = reading.tenpai_probability(p, view.turn, use_tedashi=False)
            elif mode == "tedashi":
                prob = reading.tenpai_probability(p, view.turn, use_tedashi=True)
            else:
                prob = reading.heuristic_probability(
                    p, view.turn, view.round_wind, view.game.seat_wind
                )
            if prob >= self.THREAT_FLOOR:
                out.append((p, prob))
        return out

    def _rank(self, view) -> int:
        return placement.rank_of(view.scores, view.seat)

    def _lead(self, view) -> int:
        """トップとの差（自分がトップなら2着との差、正の値）。"""
        s = sorted(view.scores, reverse=True)
        return view.scores[view.seat] - s[1] if self._rank(view) == 0 else s[0] - view.scores[view.seat]

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
        reads = self._reads(view)
        if any(p.riichi and p.seat == view.game.dealer for p, _ in reads):
            v -= 0.10
        if sum(1 for _, lv in reads if lv >= 0.5) >= 2:
            v -= 0.12
        if me.riichi:
            v = 1.0  # リーチ後は選択肢がない
        v += self._placement_bias(view)
        return v * threat_level + (1.0 - threat_level) * 1.0

    def _placement_bias(self, view) -> float:
        """点数状況による押し引きの補正。

        「下位なら押す」と「トップ目なら引く」を別々のつまみにしてある。
        どちらが効いているのかを実験で切り分けられるようにするため。
        """
        rank = self._rank(view)
        st = self.style
        if not self._aware(view):
            # 状況を見ない打ち手も、ラス目とトップ目だけは最低限意識する
            if rank == 3:
                return st.last_place_desperation
            if rank == 0 and view.round_wind != 27:
                return -0.08
            return 0.0

        bias = 0.0
        if rank == 3:
            bias += st.low_aggression
        elif rank == 2:
            bias += st.low_aggression * 0.5
        elif rank == 0:
            bias -= st.top_caution * (1.4 if self._lead(view) >= 12000 else 1.0)

        if view.is_all_last and st.allast_conditions:
            if rank == 0:
                bias -= 0.15  # アガれば終局。放銃だけを避ければいい
            elif rank == 3:
                bias += 0.15  # アガらないと終わり
            # 終盤、テンパイかノーテンかで着順が動くなら形式テンパイを取りに行く
            if view.turn >= 13:
                near = min(
                    (abs(s - view.scores[view.seat]) for i, s in enumerate(view.scores) if i != view.seat),
                    default=99999,
                )
                if near <= 4000:
                    bias += 0.20
        return bias

    # ------------------------------------------------------------ 打牌

    def discard(self, view, forbidden=frozenset()):
        """切る牌と、リーチするかを返す。

        forbidden は切れない牌（喰い替え禁止）。
        """
        me = view.me
        if me.riichi:
            return (me.drawn if me.drawn is not None else self._any_tile(me)), False

        threats = self._reads(view)
        level = max((l for _, l in threats), default=0.0)

        # 脅威の強さに応じて押し引きを決める。リーチ（level 1.0）なら基準表そのまま、
        # 2副露（0.5）なら「よほど絶望的でなければ押す」に自然に落ちる。
        if level > 0:
            if not self._should_push(self.push_value(view, level)):
                return self._fold_discard(view, threats, forbidden), False

        return self._push_discard(view, threats, level, forbidden)

    def _any_tile(self, me):
        return next(t for t in range(NUM_TILES) if me.hand[t])

    def _risk_of(self, view, tile, threats, seen):
        """その牌を切ったときの放銃リスク。相手ごとのテンパイ確率で重み付けする。

        river_read が有効なら、河から当たり牌を推定する（早切りの周辺は無筋でも安全、
        という実測に基づく）。無効なら従来どおり現物・スジ・壁だけで見る。
        """
        total = 0.0
        for p, level in threats:
            weight = 1.5 if p.seat == view.game.dealer else 1.0
            if self.style.river_read:
                r = reading.wait_risk(p, tile, seen)
            else:
                r = danger([tile], p.river_counts, seen, late=view.turn >= 8)[0].risk
            total += r * level * weight
        return total

    def _fold_discard(self, view, threats, forbidden=frozenset()):
        """降りる。安全度が最優先だが、同じくらい安全なら手を残す（回し打ち寄り）。

        安全牌が複数あるときに手をバラすのは、ただの損。
        安全度が並んだら受け入れの広いほうを残す。
        """
        me = view.me
        candidates = [t for t in range(NUM_TILES) if me.hand[t] and t not in forbidden]
        if not candidates:
            candidates = [t for t in range(NUM_TILES) if me.hand[t]]
        seen = view.seen_all()
        seen_out = view.visible()
        risks = {t: self._risk_of(view, t, threats, seen) for t in candidates}
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

    def _push_discard(self, view, threats, level, forbidden=frozenset()):
        """前に出る。受け入れ・打点・安全度を合わせて選ぶ。"""
        me = view.me
        hand = me.hand
        seen = view.visible()      # 受け入れ用（自分の手牌を含まない）
        seen_all = view.seen_all()  # 危険度用
        options = []
        base_shanten = None
        for t in range(NUM_TILES):
            if not hand[t] or t in forbidden:
                continue
            hand[t] -= 1
            s = fast.shanten(hand, me.called)
            hand[t] += 1
            options.append((t, s))
        if not options:  # 全部禁止（起こらないはずだが保険）
            t0 = next(x for x in range(NUM_TILES) if hand[x])
            options = [(t0, fast.shanten(hand, me.called))]
        best_s = min(s for _, s in options)
        # 門前の染め手判定はループの外で1回だけやる
        chase_suit = None
        if self.style.chase_honitsu and not me.open_melds:
            cs, cnt = self._suit_shape(me)
            if cnt >= self.style.honitsu_min + 1:
                chase_suit = cs
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
            # 門前でも色が寄っていれば染め手に向かう（混一色は門前3翻）
            if chase_suit is not None and t < HONOR and t // 9 != chase_suit:
                score += 10
            # 鳴いた後は役を確定させにいく。役に要らない牌を優先して切る
            if me.open_melds and me.yaku_goal:
                goal = me.yaku_goal
                if goal[0] == "tanyao" and t in YAOCHU_SET:
                    score += 14
                elif goal[0] == "honitsu" and t < HONOR and t // 9 != goal[1]:
                    score += 14
            # 危険度
            if threats:
                risk = self._risk_of(view, t, threats, seen_all)
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

        if width == 0 or view.wall_left < 4:
            return False

        # 点数状況で決まるなら、そちらを優先する
        if self._aware(view) and st.allast_conditions:
            decided = self._situational_riichi(view, width)
            if decided is not None:
                return decided

        # ダマのままで十分高い
        if value - (1300 if view.is_dealer else 1000) >= st.damaten_value and width <= 4:
            return False
        # 悪形・安手・終盤
        if not st.riichi_bad_wait_cheap and width <= 4 and value < 5200 and view.turn >= 12:
            return False
        return True

    def _situational_riichi(self, view, width):
        """点数状況からリーチ／ダマを決める。決まらなければ None。"""
        scores = view.scores
        me = view.seat
        rank = self._rank(view)
        dama_value = self.estimate_value(view, dama=True)

        if view.is_all_last:
            if rank == 0:
                # アガれば終局。リーチ棒1000点を出す理由がない。
                # ただし誰も30000点に届かないと西入するので、その場合は普通に判断する
                after = list(scores)
                after[me] += dama_value
                if max(after) >= 30000:
                    return False
                return None

            req = placement.requirements(scores, me, view.kyoku, view.honba, view.sticks)
            if req.get("already"):
                # すでに条件を満たしている。形式テンパイで足りるのでリーチしない
                return False
            # 直撃と他家ロンで必要打点が違う。出やすいほうに合わせて、緩いほうを見る
            needs = [v[2] for v in req["ron"].values()]
            if not needs:
                return True  # ロンでは届かない。打点を伸ばすしかない
            need = min(needs)
            # リーチ棒1000点ぶん条件がきつくなる
            need += 1000
            if dama_value >= need and width >= 3:
                # ダマで足りる。リーチして相手を降ろすと出アガリの機会が減る
                return False
            return True

        if (self.style.top_caution > 0 and rank == 0
                and self._lead(view) >= 12000 and view.round_wind != 27):
            # 大きくリードしている南場。リーチで押し込む必要がない
            return False
        return None

    # ------------------------------------------------------------ 和了・鳴き

    def want_tsumo(self, view) -> bool:
        return self._take_win(view, tsumo=True)

    def want_ron(self, view) -> bool:
        return self._take_win(view, tsumo=False)

    def _take_win(self, view, tsumo: bool) -> bool:
        """オーラスのラス目だけ、着順が上がらない和了は見逃す。

        和了すると半荘が終わってラスが確定する。ラス目以外は、
        見逃すと逆に落ちる危険があるので必ずアガる。
        親も連荘できるのでアガる。
        """
        if not (self._aware(view) and self.style.allast_conditions and view.is_all_last):
            return True
        if view.is_dealer:
            return True
        if self._rank(view) != 3:
            return True
        if view.wall_left < 16:  # 残り4巡を切ったら、次の機会はもう無い
            return True
        me = view.me
        win_tile = me.drawn if tsumo else view.discarded
        if win_tile is None:
            return True
        r = view.game.score_hand(me, win_tile, tsumo=tsumo, extra=None if tsumo else win_tile)
        if r is None or r.payment is None:
            return True
        new_rank = placement.rank_after_win(
            view.scores, r.payment, view.seat, view.kyoku, tsumo,
            loser=view.from_seat, sticks=view.sticks,
        )
        return new_rank < 3

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
        # 染め手を最初に見る。混一色は鳴いても2翻あるので役牌・タンヤオより価値が高い
        if self.style.chase_honitsu:
            best, count = self._suit_shape(me, tile)
            if count >= self.style.honitsu_min:
                fits = (arg // 9 == best) if kind == "chi" else (tile >= HONOR or tile // 9 == best)
                if fits:
                    return ("honitsu", best)
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
        return None

    def _suit_shape(self, me, extra_tile=None):
        """(いちばん多い色, その色＋字牌の枚数)。副露と、鳴こうとしている牌も数える。

        以前は「手牌が既に1色になっているか」で判定していたので、
        染めかけの手を一生拾えなかった。ここは枚数で見る。
        """
        by_suit = [0, 0, 0]
        honors = 0
        for x in range(NUM_TILES):
            n = me.hand[x]
            if not n:
                continue
            if x >= HONOR:
                honors += n
            else:
                by_suit[x // 9] += n
        for m in me.melds:
            for x in m.tiles:
                if x >= HONOR:
                    honors += 1
                else:
                    by_suit[x // 9] += 1
        if extra_tile is not None:
            if extra_tile >= HONOR:
                honors += 1
            else:
                by_suit[extra_tile // 9] += 1
        best = max(range(3), key=lambda s: by_suit[s])
        return best, by_suit[best] + honors


def make_awareness_lab() -> list:
    """状況判断を要素ごとに分解した4人。ベース戦術は「なおき」で統一してある。

    素直      : 点数状況を見ない（比較の土台）
    オーラス型 : オーラスだけ条件計算する（ダマ判断・見逃し・形式テンパイ・押し引き）
    攻め型    : 全局で「下位なら押す」だけ。トップ目の守りは入れない
    守り型    : 全局で「トップ目なら引く」だけ。下位の押しは入れない

    2〜4 をそれぞれ「素直」と比べれば、どの打ち回しが効いているかが分かる。
    """
    # 鳴きの基準は実戦の統計に合わせて較正してある
    # （副露率38% / 平均和了6338点 / 平均翻3.31 / 飛び14%。実戦は 30-35% / 6000-6500 / 3.3-3.5 / 5-8%）
    base = dict(
        push=0.50,
        call_min_value=1000,
        call_max_shanten=3,
        damaten_value=8000,
        riichi_bad_wait_cheap=True,
        safety_weight=1.0,
        value_weight=1.0,
        last_place_desperation=0.15,
    )
    return [
        Player("素直", Style(**base, awareness="none")),
        Player("オーラス型", Style(**base, awareness="allast", allast_conditions=True,
                                low_aggression=0.25, top_caution=0.25)),
        Player("攻め型", Style(**base, awareness="always", low_aggression=0.25, top_caution=0.0)),
        Player("守り型", Style(**base, awareness="always", low_aggression=0.0, top_caution=0.25)),
    ]


def make_reading_lab() -> list:
    """読み方だけを変えた4人。ベース戦術は共通。

    手書き読み : references/reading.md の副露数×巡目の表（従来の実装）
    統計読み   : 実測テーブル。副露数×巡目だけを見る
    手出し読み : 実測テーブル。直近3打の手出し／ツモ切りも見る
    全知       : 相手の手牌が見える。**反則**だが、読みの上限を知るための参照点
    """
    base = dict(
        push=0.50,
        call_min_value=1000,
        call_max_shanten=3,
        damaten_value=8000,
        riichi_bad_wait_cheap=True,
        safety_weight=1.0,
        value_weight=1.0,
        last_place_desperation=0.15,
    )
    return [
        Player("手書き読み", Style(**base, reading="heuristic")),
        Player("統計読み", Style(**base, reading="stats")),
        Player("手出し読み", Style(**base, reading="tedashi")),
        Player("全知", Style(**base, reading="oracle")),
    ]


def make_reading_push_lab() -> list:
    """「読みが正確になったら、押し引きの閾値も下げるべきか」を測る4人。

    読み実験で、正確に読むほど順位が悪化した。放銃率は下がるのに和了率と
    流局聴牌率が落ちる ＝ 正しく降りているが降りすぎている、という形だった。
    押し引きの閾値は「読めない前提」で作られた表なので、読みが良くなったら
    下げる（押す方向に寄せる）べきではないか、という仮説を確かめる。
    """
    base = dict(
        call_min_value=1000,
        call_max_shanten=3,
        damaten_value=8000,
        riichi_bad_wait_cheap=True,
        safety_weight=1.0,
        value_weight=1.0,
        last_place_desperation=0.15,
    )
    return [
        Player("手書き読み.50", Style(**base, reading="heuristic", push=0.50)),
        Player("手出し読み.50", Style(**base, reading="tedashi", push=0.50)),
        Player("手出し読み.35", Style(**base, reading="tedashi", push=0.35)),
        Player("全知.35", Style(**base, reading="oracle", push=0.35)),
    ]


def make_honitsu_lab() -> list:
    """染め手にどれくらい選択的であるべきかを測る4人。

    honitsu_min は「その色＋字牌が何枚あれば染めに向かうか」。
    大きいほど選択的（染める頻度が下がる）。
    """
    base = dict(
        push=0.50,
        call_min_value=1000,
        call_max_shanten=3,
        damaten_value=8000,
        riichi_bad_wait_cheap=True,
        safety_weight=1.0,
        value_weight=1.0,
        last_place_desperation=0.15,
        reading="tedashi",
    )
    return [
        Player("染めない", Style(**base, chase_honitsu=False)),
        Player("9枚で染める", Style(**base, chase_honitsu=True, honitsu_min=9)),
        Player("11枚で染める", Style(**base, chase_honitsu=True, honitsu_min=11)),
        Player("12枚で染める", Style(**base, chase_honitsu=True, honitsu_min=12)),
    ]


def make_fifth() -> "Player":
    """5人目「さとる」— 河を読んで危険牌を避け、根拠のある安全牌なら無筋でも切る。

    他の4人との違いは3つ。

    1. **相手のテンパイを手出し／ツモ切りから読む**（reading="tedashi"）。
       1副露でツモ切り3連続ならテンパイ69%、2副露でも手出しが続くなら25%、
       という実測テーブルを使う
    2. **当たり牌を河から推定する**（river_read）。現物・スジに加えて
       「序盤に切られた牌の隣は無筋でも4割安全」という実測を使う。
       安全の根拠があれば無筋でも切り、根拠が無ければ避ける
    3. **テンパイのサインが出たら打ち方を切り替える**。読んだテンパイ確率が
       そのまま押し引きの重みになるので、相手の河次第で自然に硬軟が変わる

    押し引きの閾値は 0.42。読みが正確なぶん、押せると判断したら押す
    （読みだけ良くして閾値を据え置くと、怖がって降りすぎて逆に弱くなることが
    実験で分かっているため。results/experiment-reading.md）。
    """
    return Player(
        "さとる",
        Style(
            awareness="allast",
            allast_conditions=True,
            low_aggression=0.25,
            push=0.42,
            call_min_value=2000,
            call_max_shanten=3,
            damaten_value=8000,
            riichi_bad_wait_cheap=True,
            safety_weight=1.3,
            value_weight=1.0,
            last_place_desperation=0.15,
            reading="tedashi",
            river_read=True,
        ),
    )


def make_players(awareness: str = "none", **knobs) -> list:
    """4人の雀士。awareness を指定すると全員に同じ状況判断を載せる。

    鳴きの基準は実戦の統計に合わせて較正済み。性格の差は
    押し引きの閾値・打点の追い方・守備の重み・リーチ方針で表してある。
    """
    extra = dict(knobs)
    if awareness != "none" and not knobs:
        extra = dict(allast_conditions=True, low_aggression=0.25, top_caution=0.0)
    return [
        Player(
            "ゆうだい",
            Style(
                awareness=awareness,
                **extra,
                push=0.32,
                call_min_value=2000,
                call_max_shanten=3,
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
                awareness=awareness,
                **extra,
                push=0.50,
                call_min_value=2000,
                call_max_shanten=3,
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
                awareness=awareness,
                **extra,
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
                awareness=awareness,
                **extra,
                push=0.64,
                call_min_value=3900,
                call_max_shanten=2,
                damaten_value=5200,
                riichi_bad_wait_cheap=False,
                safety_weight=1.6,
                value_weight=1.0,
                last_place_desperation=0.10,
            ),
        ),
    ]
