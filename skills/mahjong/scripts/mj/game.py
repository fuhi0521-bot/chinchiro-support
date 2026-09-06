"""四人半荘の対局エンジン。

雀魂・段位戦の設定に合わせてある（赤各1枚・喰いタンあり・切り上げ満貫なし・
ダブロンあり・飛びあり・南入なし＝南4局で終了）。

実装していないもの（頻度が低く、結果統計にほぼ影響しない）:
  - 責任払い（包）・流し満貫・人和
  - 三家和は流局として扱う
  - 大明槓の responsibility、槍槓の一部の細かい形
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import fast
from .hand import Meld
from .score import noten_penalty
from .tiles import DRAGONS, HONOR, NUM_TILES, YAOCHU, dora_from_indicator
from .yaku import Context, evaluate

RED_TILES = (4, 13, 22)  # 5m 5p 5s
YAOCHU_SET = frozenset(YAOCHU)
WINDS = (27, 28, 29, 30)  # 東 南 西 北


def build_wall(rng: random.Random) -> list[tuple[int, bool]]:
    """(牌, 赤かどうか) を136枚。赤は 5m/5p/5s 各1枚。"""
    wall: list[tuple[int, bool]] = []
    for t in range(NUM_TILES):
        for k in range(4):
            wall.append((t, t in RED_TILES and k == 0))
    rng.shuffle(wall)
    return wall


@dataclass
class PlayerState:
    seat: int
    name: str
    score: int = 25000
    hand: list[int] = field(default_factory=lambda: [0] * NUM_TILES)
    red: set = field(default_factory=set)  # 赤を持っている牌 (4/13/22)
    melds: list = field(default_factory=list)
    meld_red: int = 0
    river: list[int] = field(default_factory=list)
    river_counts: list[int] = field(default_factory=lambda: [0] * NUM_TILES)
    riichi: bool = False
    riichi_turn: int = -1
    double_riichi: bool = False
    ippatsu: bool = False
    furiten: bool = False
    temp_furiten: bool = False
    drawn: int | None = None
    drawn_red: bool = False
    yaku_goal: tuple | None = None  # 鳴いた後に向かう役 ('tanyao',) / ('honitsu', 色) / ('yakuhai',)

    @property
    def menzen(self) -> bool:
        return all(m.kind == "ankan" for m in self.melds)

    @property
    def called(self) -> int:
        return len(self.melds)

    @property
    def open_melds(self) -> int:
        return sum(1 for m in self.melds if m.kind != "ankan")

    @property
    def aka(self) -> int:
        return len(self.red) + self.meld_red

    def hand_size(self) -> int:
        return sum(self.hand) + 3 * self.called


@dataclass
class Result:
    """1局の結果。"""

    kind: str  # tsumo / ron / draw / abort
    winners: list = field(default_factory=list)  # (seat, points, han, fu, yaku)
    loser: int | None = None
    deltas: list = field(default_factory=lambda: [0, 0, 0, 0])
    tenpai: list = field(default_factory=list)
    dealer_repeat: bool = False


class Game:
    """1局（東1局など）を進行させる。"""

    def __init__(self, players, scores, round_wind, dealer, honba, sticks, rng):
        self.ai = players
        self.round_wind = round_wind
        self.dealer = dealer
        self.honba = honba
        self.sticks = sticks
        self.rng = rng
        self.players = [
            PlayerState(seat=i, name=players[i].name, score=scores[i]) for i in range(4)
        ]
        self.wall = build_wall(rng)
        self.dead = self.wall[-14:]
        self.live = self.wall[:-14]
        self.dora_indicators = [self.dead[0][0]]
        self.ura_indicators = [self.dead[1][0]]
        self.kan_count = 0
        self.turn_no = 0
        self.first_go_around = True
        self.deal()

    # ------------------------------------------------------------------ setup

    def deal(self) -> None:
        for i in range(4):
            p = self.players[(self.dealer + i) % 4]
            for _ in range(13):
                t, red = self.live.pop(0)
                p.hand[t] += 1
                if red:
                    p.red.add(t)

    def seat_wind(self, seat: int) -> int:
        return WINDS[(seat - self.dealer) % 4]

    def dora_count(self, p: PlayerState) -> int:
        dora = [dora_from_indicator(i) for i in self.dora_indicators]
        n = 0
        for d in dora:
            n += p.hand[d]
            for m in p.melds:
                n += sum(1 for t in m.tiles if t == d)
        return n

    def ura_count(self, p: PlayerState) -> int:
        if not p.riichi:
            return 0
        ura = [dora_from_indicator(i) for i in self.ura_indicators[: len(self.dora_indicators)]]
        n = 0
        for d in ura:
            n += p.hand[d]
            for m in p.melds:
                n += sum(1 for t in m.tiles if t == d)
        return n

    def visible_counts(self) -> list[int]:
        """全員の河・副露・ドラ表示牌。読みと山読みに使う。"""
        seen = [0] * NUM_TILES
        for p in self.players:
            for t, n in enumerate(p.river_counts):
                seen[t] += n
            for m in p.melds:
                for t in m.tiles:
                    seen[t] += 1
        for i in self.dora_indicators:
            seen[i] += 1
        return seen

    # ------------------------------------------------------------------- flow

    def play(self) -> Result:
        cur = self.dealer
        rinshan = False
        first_discards: list[int] = []

        while True:
            p = self.players[cur]

            if not rinshan and not self.live:
                return self.exhaustive_draw()

            # --- ツモ ---
            if rinshan:
                t, red = self.dead.pop()
                if self.live:
                    self.dead.insert(0, self.live.pop())
            else:
                t, red = self.live.pop(0)
            p.hand[t] += 1
            if red:
                p.red.add(t)
            p.drawn, p.drawn_red = t, red
            p.temp_furiten = False

            view = self.view(cur, drawn=t, rinshan=rinshan)

            # --- ツモ和了 ---
            if self.can_tsumo(p) and self.ai[cur].want_tsumo(view):
                return self.settle_tsumo(cur, t, rinshan)

            # --- 九種九牌 ---
            if self.first_go_around and not any(pl.melds for pl in self.players):
                kinds = sum(1 for x in YAOCHU if p.hand[x])
                if kinds >= 9 and self.ai[cur].want_abort(view):
                    return self.abortive("九種九牌")

            # --- カン ---
            kan = self.ai[cur].want_kan(view, self.kan_options(p))
            if kan and self.kan_count < 4:
                res = self.do_kan(cur, kan)
                if res:
                    return res
                rinshan = True
                continue
            rinshan = False

            # --- 打牌 ---
            tile, declare_riichi = self.ai[cur].discard(view)
            if p.hand[tile] == 0:
                tile = next(x for x in range(NUM_TILES) if p.hand[x])
                declare_riichi = False
            if declare_riichi and self.can_riichi(p, tile):
                p.riichi = True
                p.riichi_turn = self.turn_no
                p.ippatsu = True
                p.double_riichi = self.first_go_around
                p.score -= 1000
                self.sticks += 1
            self.discard(cur, tile)

            if self.first_go_around:
                first_discards.append(tile)
                if len(first_discards) == 4 and cur == (self.dealer + 3) % 4:
                    if len(set(first_discards)) == 1 and first_discards[0] in WINDS:
                        return self.abortive("四風連打")
                if cur == (self.dealer + 3) % 4:
                    self.first_go_around = False

            if sum(1 for pl in self.players if pl.riichi) == 4:
                return self.abortive("四家立直")

            # --- 他家の反応 ---
            nxt, res = self.after_discard(cur, tile)
            if res:
                return res
            if nxt is None:
                if not self.live:
                    return self.exhaustive_draw()
                cur = (cur + 1) % 4
                self.turn_no += 1
            else:
                cur = nxt

    # -------------------------------------------------------------- decisions

    def view(self, seat, drawn=None, rinshan=False, discarded=None, from_seat=None):
        return View(self, seat, drawn, rinshan, discarded, from_seat)

    def can_tsumo(self, p: PlayerState) -> bool:
        if fast.shanten(p.hand, p.called) != -1:
            return False
        return self.score_hand(p, p.drawn, tsumo=True) is not None

    def can_riichi(self, p: PlayerState, discard: int) -> bool:
        if p.riichi or not p.menzen or p.score < 1000 or len(self.live) < 4:
            return False
        p.hand[discard] -= 1
        ok = fast.shanten(p.hand, p.called) == 0
        p.hand[discard] += 1
        return ok

    def kan_options(self, p: PlayerState) -> list:
        out = []
        if len(self.live) == 0 or self.kan_count >= 4:
            return out
        for t in range(NUM_TILES):
            if p.hand[t] == 4:
                out.append(("ankan", t))
        for m in p.melds:
            if m.kind == "pon" and p.hand[m.tile]:
                out.append(("kakan", m.tile))
        if p.riichi:
            # リーチ後は待ちと面子構成が変わらない暗槓のみ
            keep = []
            for kind, t in out:
                if kind != "ankan":
                    continue
                before = set(x for x, _ in fast.ukeire(p.hand, p.called)[1])
                p.hand[t] -= 4
                m2 = p.called + 1
                after = set(x for x, _ in fast.ukeire(p.hand, m2)[1])
                p.hand[t] += 4
                if before == after:
                    keep.append((kind, t))
            out = keep
        return out

    def do_kan(self, seat, kan):
        kind, t = kan
        p = self.players[seat]
        if kind == "ankan":
            p.hand[t] -= 4
            if t in p.red:
                p.red.discard(t)
                p.meld_red += 1
            p.melds.append(Meld("ankan", t))
        else:  # kakan
            p.hand[t] -= 1
            if t in p.red:
                p.red.discard(t)
                p.meld_red += 1
            for i, m in enumerate(p.melds):
                if m.kind == "pon" and m.tile == t:
                    p.melds[i] = Meld("minkan", t)
                    break
            # 搶槓
            for other in range(4):
                if other == seat:
                    continue
                o = self.players[other]
                o.hand[t] += 1
                win = fast.shanten(o.hand, o.called) == -1 and not o.furiten
                o.hand[t] -= 1
                if win and self.ai[other].want_ron(self.view(other, discarded=t, from_seat=seat)):
                    return self.settle_ron([other], t, seat, chankan=True)
        self.kan_count += 1
        self.dora_indicators.append(self.dead[len(self.dora_indicators) * 2][0])
        for pl in self.players:
            pl.ippatsu = False
        if self.kan_count == 4 and sum(1 for pl in self.players if any(m.is_kan for m in pl.melds)) > 1:
            return self.abortive("四開槓")
        return None

    def discard(self, seat, tile) -> None:
        p = self.players[seat]
        p.hand[tile] -= 1
        if tile in p.red and p.hand[tile] == 0:
            p.red.discard(tile)
        p.river.append(tile)
        p.river_counts[tile] += 1
        p.drawn = None
        # フリテン更新
        waits = {t for t, _ in fast.ukeire(p.hand, p.called)[1]} if fast.shanten(p.hand, p.called) == 0 else set()
        p.furiten = any(p.river_counts[w] for w in waits)

    def after_discard(self, seat, tile):
        """ロン・ポン・カン・チーの処理。(次の手番, 結果) を返す。"""
        # --- ロン ---
        ron = []
        for i in range(1, 4):
            other = (seat + i) % 4
            o = self.players[other]
            if o.furiten or o.temp_furiten:
                continue
            o.hand[tile] += 1
            win = fast.shanten(o.hand, o.called) == -1
            o.hand[tile] -= 1
            if not win:
                continue
            if self.score_hand(o, tile, tsumo=False, extra=tile) is None:
                continue
            if self.ai[other].want_ron(self.view(other, discarded=tile, from_seat=seat)):
                ron.append(other)
            else:
                o.temp_furiten = True
                o.furiten = True
        if len(ron) >= 3:
            return None, self.abortive("三家和")
        if ron:
            return None, self.settle_ron(ron, tile, seat)

        # --- ポン・カン（上家優先なし、鳴きは全員から） ---
        for i in range(1, 4):
            other = (seat + i) % 4
            o = self.players[other]
            if o.riichi:
                continue
            opts = []
            if o.hand[tile] >= 2:
                opts.append(("pon", tile))
            if o.hand[tile] == 3 and self.kan_count < 4 and self.live:
                opts.append(("minkan", tile))
            if not opts:
                continue
            choice = self.ai[other].want_call(self.view(other, discarded=tile, from_seat=seat), opts)
            if choice:
                return self.do_call(other, choice, tile, seat)

        # --- チー（下家のみ） ---
        other = (seat + 1) % 4
        o = self.players[other]
        if not o.riichi and tile < HONOR:
            opts = []
            r = tile % 9
            base = tile - r
            for start in (tile - 2, tile - 1, tile):
                sr = start - base
                if sr < 0 or sr > 6:
                    continue
                need = [start + k for k in range(3) if start + k != tile]
                if all(o.hand[x] for x in need):
                    opts.append(("chi", start))
            if opts:
                choice = self.ai[other].want_call(self.view(other, discarded=tile, from_seat=seat), opts)
                if choice:
                    return self.do_call(other, choice, tile, seat)

        return None, None

    def do_call(self, seat, choice, tile, from_seat):
        kind, arg = choice
        p = self.players[seat]
        src = self.players[from_seat]
        src.river.pop()
        src.river_counts[tile] -= 1
        for pl in self.players:
            pl.ippatsu = False
        self.first_go_around = False

        if kind == "pon":
            p.hand[tile] -= 2
            if tile in p.red and p.hand[tile] == 0:
                p.red.discard(tile)
                p.meld_red += 1
            p.melds.append(Meld("pon", tile))
        elif kind == "minkan":
            p.hand[tile] -= 3
            if tile in p.red:
                p.red.discard(tile)
                p.meld_red += 1
            p.melds.append(Meld("minkan", tile))
            self.kan_count += 1
            self.dora_indicators.append(self.dead[len(self.dora_indicators) * 2][0])
            t, red = self.dead.pop()
            if self.live:
                self.dead.insert(0, self.live.pop())
            p.hand[t] += 1
            if red:
                p.red.add(t)
            p.drawn = t
        else:  # chi
            start = arg
            for k in range(3):
                if start + k != tile:
                    p.hand[start + k] -= 1
                    if start + k in p.red and p.hand[start + k] == 0:
                        p.red.discard(start + k)
                        p.meld_red += 1
            p.melds.append(Meld("chi", start))

        if kind == "minkan":
            # 嶺上牌を引いた状態から打牌へ（ツモ和了は簡略化して省く）
            tile2, riichi = self.ai[seat].discard(self.view(seat, drawn=p.drawn))
            if p.hand[tile2] == 0:
                tile2 = next(x for x in range(NUM_TILES) if p.hand[x])
            self.discard(seat, tile2)
            nxt, res = self.after_discard(seat, tile2)
            if res:
                return None, res
            return (nxt if nxt is not None else (seat + 1) % 4), None

        tile2, riichi = self.ai[seat].discard(self.view(seat))
        if p.hand[tile2] == 0:
            tile2 = next(x for x in range(NUM_TILES) if p.hand[x])
        self.discard(seat, tile2)
        nxt, res = self.after_discard(seat, tile2)
        if res:
            return None, res
        return (nxt if nxt is not None else (seat + 1) % 4), None

    # -------------------------------------------------------------- scoring

    def score_hand(self, p: PlayerState, win_tile, tsumo, extra=None, **flags):
        """和了形を評価する。役なしなら None。"""
        hand = list(p.hand)
        if extra is not None:
            hand[extra] += 1
        ctx = Context(
            is_tsumo=tsumo,
            riichi=p.riichi and not p.double_riichi,
            double_riichi=p.double_riichi,
            ippatsu=p.ippatsu,
            seat_wind=self.seat_wind(p.seat),
            round_wind=self.round_wind,
            dora=self._dora_in(hand, p),
            uradora=self._ura_in(hand, p) if p.riichi else 0,
            aka=p.aka,
            honba=self.honba,
            riichi_sticks=self.sticks,
            haitei=tsumo and not self.live,
            houtei=(not tsumo) and not self.live,
            **flags,
        )
        try:
            r = evaluate(hand, p.melds, win_tile, ctx)
        except Exception:
            return None
        if not r.yakuman and r.han == 0:
            return None
        return r

    def _dora_in(self, hand, p):
        n = 0
        for ind in self.dora_indicators:
            d = dora_from_indicator(ind)
            n += hand[d]
            for m in p.melds:
                n += sum(1 for t in m.tiles if t == d)
        return n

    def _ura_in(self, hand, p):
        n = 0
        for ind in self.ura_indicators[: len(self.dora_indicators)]:
            d = dora_from_indicator(ind)
            n += hand[d]
            for m in p.melds:
                n += sum(1 for t in m.tiles if t == d)
        return n

    def settle_tsumo(self, seat, win_tile, rinshan=False):
        p = self.players[seat]
        r = self.score_hand(p, win_tile, tsumo=True, rinshan=rinshan)
        deltas = [0, 0, 0, 0]
        pay = r.payment
        is_dealer = p.seat == self.dealer
        for i in range(4):
            if i == seat:
                continue
            amount = pay.from_each_child if (is_dealer or self.players[i].seat != self.dealer) else pay.from_dealer
            deltas[i] -= amount
            deltas[seat] += amount
        deltas[seat] += self.sticks * 1000
        return Result(
            kind="tsumo",
            winners=[(seat, pay.total, r.han, r.fu, [n for n, _ in (r.yaku or r.yakuman)])],
            deltas=deltas,
            dealer_repeat=is_dealer,
        )

    def settle_ron(self, winners, tile, loser, chankan=False):
        deltas = [0, 0, 0, 0]
        info = []
        sticks_taken = False
        dealer_repeat = False
        order = sorted(winners, key=lambda w: (w - loser) % 4)
        for w in order:
            p = self.players[w]
            r = self.score_hand(p, tile, tsumo=False, extra=tile, chankan=chankan)
            if r is None:
                continue
            # payment.ron には本場（1本300点）がすでに入っている。ここで足すと二重になる
            got = r.payment.ron
            deltas[w] += got
            deltas[loser] -= got
            if not sticks_taken:
                deltas[w] += self.sticks * 1000
                sticks_taken = True
            if p.seat == self.dealer:
                dealer_repeat = True
            info.append((w, got, r.han, r.fu, [n for n, _ in (r.yaku or r.yakuman)]))
        if not info:
            return self.exhaustive_draw()
        return Result(kind="ron", winners=info, loser=loser, deltas=deltas, dealer_repeat=dealer_repeat)

    def exhaustive_draw(self):
        tenpai = [i for i in range(4) if fast.shanten(self.players[i].hand, self.players[i].called) == 0]
        gain, pay = noten_penalty(len(tenpai))
        deltas = [0, 0, 0, 0]
        for i in range(4):
            deltas[i] = gain if i in tenpai else -pay
        return Result(kind="draw", deltas=deltas, tenpai=tenpai, dealer_repeat=self.dealer in tenpai)

    def abortive(self, reason):
        return Result(kind="abort", deltas=[0, 0, 0, 0], dealer_repeat=True)


class View:
    """AI に渡す局面。手牌は自分のものだけ見える。"""

    __slots__ = ("game", "seat", "drawn", "rinshan", "discarded", "from_seat")

    def __init__(self, game, seat, drawn=None, rinshan=False, discarded=None, from_seat=None):
        self.game = game
        self.seat = seat
        self.drawn = drawn
        self.rinshan = rinshan
        self.discarded = discarded
        self.from_seat = from_seat

    @property
    def me(self):
        return self.game.players[self.seat]

    @property
    def others(self):
        return [p for p in self.game.players if p.seat != self.seat]

    @property
    def turn(self):
        """巡目（1〜18）。山の残り枚数から数える。"""
        return (70 - len(self.game.live) + 3) // 4

    @property
    def wall_left(self):
        return len(self.game.live)

    @property
    def is_dealer(self):
        return self.seat == self.game.dealer

    @property
    def seat_wind(self):
        return self.game.seat_wind(self.seat)

    @property
    def round_wind(self):
        return self.game.round_wind

    @property
    def scores(self):
        return [p.score for p in self.game.players]

    @property
    def honba(self):
        return self.game.honba

    @property
    def sticks(self):
        return self.game.sticks

    @property
    def kyoku(self):
        """0-3 = 1〜4局。連荘中も親の席と一致する。"""
        return self.game.dealer

    @property
    def is_all_last(self):
        """オーラス（南4局／西4局）か。"""
        return self.game.round_wind != 27 and self.game.dealer == 3

    def dora_tiles(self):
        return [dora_from_indicator(i) for i in self.game.dora_indicators]

    def visible(self):
        """自分の手牌を除いた、場に見えている牌。受け入れ計算に使う。

        ukeire() は自分の手牌を別途引くので、ここに入れると二重に引いてしまう。
        """
        return self.game.visible_counts()

    def seen_all(self):
        """自分の手牌も含めた既知の牌。危険度・壁の判定に使う。"""
        seen = self.game.visible_counts()
        for t, n in enumerate(self.me.hand):
            seen[t] += n
        return seen

    def threats(self):
        """危険な相手のリスト。(相手, 危険度 0-1)。"""
        out = []
        for p in self.others:
            level = 0.0
            if p.riichi:
                level = 1.0
            else:
                opens = p.open_melds
                if opens >= 3:
                    level = 0.9
                elif opens == 2:
                    level = 0.5 if self.turn < 12 else 0.85
                elif opens == 1 and self.turn >= 13:
                    level = 0.25
                if opens and any(
                    m.tile in DRAGONS or m.tile == self.game.seat_wind(p.seat) or m.tile == self.game.round_wind
                    for m in p.melds
                    if m.kind != "chi"
                ):
                    level = min(1.0, level + 0.15)
            if level > 0:
                out.append((p, level))
        return out
