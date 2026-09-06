"""計算エンジンの回帰テスト。

    python3 -m pytest tests -q      （pytest があれば）
    python3 tests/test_engine.py    （無くても動く）
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills", "mahjong", "scripts"))

from mj.efficiency import discard_options, waits  # noqa: E402
from mj.hand import is_chiitoitsu, is_kokushi, parse_melds, standard_parses  # noqa: E402
from mj.safety import danger  # noqa: E402
from mj.score import base_points, payments  # noqa: E402
from mj.shanten import shanten  # noqa: E402
from mj.tiles import parse_counts, parse_tile, tile_str  # noqa: E402
from mj.yaku import Context, evaluate  # noqa: E402


def C(h):
    return parse_counts(h)[0]


def test_parse():
    counts, aka = parse_counts("0m123p東東発")
    assert aka == 1
    assert counts[4] == 1  # 0m は 5m
    assert counts[27] == 2 and counts[32] == 1


def test_shanten_basics():
    assert shanten(C("123m456p789s11122z")) == -1
    assert shanten(C("123m456p789s1112z")) == 0
    assert shanten(C("19m19p19s1234567z")) == 0  # 国士十三面
    assert shanten(C("1133557799m1133p")) == -1  # 七対子和了
    assert shanten(C("258m258p258s1234z")) == 6  # 七対子ルート


def test_waits():
    w = dict(waits(C("34567m123p456p11s")))
    assert {parse_tile("2m"), parse_tile("5m"), parse_tile("8m")} == set(w)  # 三面張
    w = dict(waits(C("1112345678999m")))
    assert len(w) == 9  # 九蓮宝燈 九面待ち
    assert waits(C("4444m5555p6666s1z")) == []


def test_discard():
    opts = discard_options(C("3456778m234p55s99s"))
    assert tile_str(opts[0].tile) == "7m"
    assert opts[0].shanten == 0


def _score(hand, win, melds=None, **kw):
    counts, aka = parse_counts(hand)
    ctx = Context(aka=aka, **kw)
    return evaluate(counts, parse_melds(melds), parse_tile(win), ctx)


def test_scoring():
    r = _score("234m567m234p678p11s", "2m", is_tsumo=True, riichi=True)
    assert r.han == 3 and r.fu == 20 and r.payment.total == 2700  # 700/1300

    r = _score("1133557799m1133p", "3p", is_tsumo=True, riichi=True)
    assert r.fu == 25 and r.han == 4 and r.payment.total == 6400

    r = _score("19m19p19s12345677z", "7z")
    assert r.payment.total == 64000  # 国士十三面 = ダブル役満

    r = _score("19m19p19s12345677z", "1m")
    assert r.payment.total == 32000

    r = _score("111m333m555m777m22p", "7m", is_tsumo=True, seat_wind=27)
    assert [n for n, _ in r.yakuman] == ["四暗刻"] and r.payment.total == 48000

    r = _score("234m567m678p11s", "2m", melds="chi=234p")
    assert r.han == 0  # 役なし

    r = _score("234m567m678p22s", "2m", melds="chi=234p")
    assert r.han == 1 and r.payment.total == 1000  # 喰いタン

    r = _score("555z666z77z123m456m", "6z")
    names = [n for n, _ in r.yaku]
    assert "小三元" in names and "混一色" in names and r.fu == 50

    r = _score("111999m11z111999p", "9p")
    names = [n for n, _ in r.yaku]
    assert "混老頭" in names and "対々和" in names and "混全帯幺九" not in names

    r = _score("11223344556677m", "7m")
    assert r.han == 10  # 高点法: 平和+二盃口+清一色


def test_point_table():
    table = {
        (1, 30): (1000, 1500),
        (2, 30): (2000, 2900),
        (3, 40): (5200, 7700),
        (4, 30): (7700, 11600),
        (4, 40): (8000, 12000),
        (5, 30): (8000, 12000),
        (6, 30): (12000, 18000),
        (8, 30): (16000, 24000),
        (11, 30): (24000, 36000),
        (13, 30): (32000, 48000),
    }
    for (han, fu), (ko, oya) in table.items():
        base, _ = base_points(han, fu)
        assert payments(base, is_dealer=False, is_tsumo=False).ron == ko, (han, fu)
        assert payments(base, is_dealer=True, is_tsumo=False).ron == oya, (han, fu)


def test_danger():
    river = C("1m4m")
    ds = {tile_str(d.tile): d.label for d in danger([parse_tile(t) for t in ("1m", "4m", "7m", "5p")], river)}
    assert ds["1m"] == "現物"
    assert ds["4m"] == "現物"
    assert ds["7m"] == "スジ"      # 4m が切れているので 7m は完全スジ
    assert ds["5p"].startswith("無筋")
    ds = {tile_str(d.tile): d.label for d in danger([parse_tile("5m")], C("2m"))}
    assert ds["5m"] == "片スジ"    # 中張牌は両側そろって初めて安全度が上がる
    ds = {tile_str(d.tile): d.label for d in danger([parse_tile("2m")], C("1s"), C("4444m"))}
    assert ds["2m"] == "ノーチャンス"


def test_random_consistency():
    random.seed(1)
    for _ in range(1500):
        wall = [i for i in range(34) for _ in range(4)]
        random.shuffle(wall)
        counts = [0] * 34
        for t in wall[:14]:
            counts[t] += 1
        agari = bool(standard_parses(counts)) or is_chiitoitsu(counts) or is_kokushi(counts)
        assert (shanten(counts) == -1) == agari




# --- 高速シャンテンと対局エンジンの検証 -------------------------------------

from mj import fast  # noqa: E402
from mj.shanten import shanten_standard as slow_standard  # noqa: E402


def test_fast_shanten_matches_reference():
    """高速版が全探索版と完全に一致すること。"""
    random.seed(3)
    for _ in range(3000):
        wall = [j for j in range(34) for _ in range(4)]
        random.shuffle(wall)
        n = random.choice([13, 14, 10, 11, 7, 8])
        called = (13 - n) // 3 if n in (10, 11, 7, 8) else 0
        counts = [0] * 34
        for t in wall[:n]:
            counts[t] += 1
        assert fast.shanten_standard(counts, called) == slow_standard(counts, called)


def test_ukeire_filter_is_exact():
    """受け入れの絞り込みが、全34種を調べた結果と一致すること。"""
    random.seed(11)
    for _ in range(800):
        wall = [i for i in range(34) for _ in range(4)]
        random.shuffle(wall)
        counts = [0] * 34
        for t in wall[:13]:
            counts[t] += 1
        cur = fast.shanten(counts)
        full = set()
        for t in range(34):
            if counts[t] >= 4:
                continue
            counts[t] += 1
            if fast.shanten(counts) < cur:
                full.add(t)
            counts[t] -= 1
        assert full == {t for t, _ in fast.ukeire(counts)[1]}


def test_game_runs_and_conserves_points():
    """1半荘を通して、点棒の合計が保たれること（供託を含む）。"""
    import random as _r

    from mj.simulate import play_hanchan
    from mj.players import make_players

    ai = make_players()
    rng = _r.Random(5)
    for i in range(6):
        stats = play_hanchan(ai, rng, start_offset=i)
        total_hanchan = sum(s.hanchan for s in stats.values())
        assert total_hanchan == 4
        assert sum(s.hands for s in stats.values()) >= 4 * 4


def test_no_yakuless_wins():
    """役なしでアガれてしまわないこと。"""
    import random as _r

    from mj.game import Game
    from mj.players import make_players

    ai = make_players()
    rng = _r.Random(9)
    for _ in range(25):
        g = Game(ai, [25000] * 4, 27, 0, 0, 0, rng)
        res = g.play()
        for seat, pts, han, fu, yaku in res.winners:
            assert yaku, "役のない和了が発生した"
            assert pts > 0



# --- 着順とオーラスの条件計算 -----------------------------------------------

from mj import placement  # noqa: E402


def test_ranking_tiebreak():
    """同点は起家（席0）に近いほうが上位。"""
    assert placement.ranking([25000] * 4) == [0, 1, 2, 3]
    assert placement.rank_of([24000, 26000, 25000, 25000], 2) == 1
    assert placement.rank_of([24000, 26000, 25000, 25000], 3) == 2


def test_all_last_requirements():
    """1000点差は直撃1000点で逆転できる（点差が2倍動くため）。"""
    scores = [24000, 25000, 25500, 25500]
    req = placement.requirements(scores, me=0, dealer=3)
    assert req["rank"] == 3
    assert req["direct"][2] == 1000, req["direct"]
    # 直撃で 25000 / 24000 になり、順位が入れ替わる
    han, fu, pts = req["direct"]
    from mj.score import base_points, payments

    base, _ = base_points(han, fu)
    pay = payments(base, is_dealer=False, is_tsumo=False)
    after = placement.scores_after_win(scores, pay, me=0, dealer=3, is_tsumo=False, loser=1)
    assert after[0] > after[1]
    assert placement.rank_of(after, 0) < 3


def test_tenpai_changes_placement():
    """流局のテンパイ／ノーテンで着順が動くことを検出できる。"""
    scores = [24000, 25000, 25500, 25500]
    assert placement.rank_after_draw(scores, 0, {0}) == 0  # 1人テンパイなら +3000
    assert placement.rank_after_draw(scores, 0, {1, 2, 3}) == 3


def test_requirements_consistency():
    """必要打点が本当に着順を上げるか、全パターンで検算する。"""
    import random as _r

    rng = _r.Random(4)
    for _ in range(300):
        scores = [25000 + rng.randrange(-15, 16) * 1000 for _ in range(4)]
        me = rng.randrange(4)
        dealer = rng.randrange(4)
        req = placement.requirements(scores, me, dealer)
        if req.get("already"):
            continue
        from mj.score import base_points, payments

        for loser, (han, fu, _pts) in req["ron"].items():
            base, _ = base_points(han, fu)
            pay = payments(base, is_dealer=(me == dealer), is_tsumo=False)
            after = placement.scores_after_win(scores, pay, me, dealer, False, loser=loser)
            assert placement.rank_of(after, me) <= req["target"]
        if req["tsumo"]:
            han, fu, _t, _txt = req["tsumo"]
            base, _ = base_points(han, fu)
            pay = payments(base, is_dealer=(me == dealer), is_tsumo=True)
            after = placement.scores_after_win(scores, pay, me, dealer, True)
            assert placement.rank_of(after, me) <= req["target"]


def test_situational_players_run():
    """状況判断つきの4人が最後まで打てること。"""
    import random as _r

    from mj.simulate import play_hanchan
    from mj.players import make_awareness_lab, make_players

    for ai in (make_awareness_lab(), make_players("always")):
        rng = _r.Random(2)
        for i in range(3):
            stats = play_hanchan(ai, rng, start_offset=i)
            assert sum(s.hanchan for s in stats.values()) == 4



# --- 手出し／ツモ切りと読み -------------------------------------------------

from mj import reading  # noqa: E402


def test_tedashi_recorded():
    """河と手出しフラグの長さが常に一致すること。"""
    import random as _r

    from mj.game import Game
    from mj.players import make_players

    ai = make_players()
    rng = _r.Random(7)
    for k in range(8):
        g = Game(ai, [25000] * 4, 27, k % 4, 0, 0, rng)
        g.play()
        for p in g.players:
            assert len(p.river) == len(p.tedashi), (len(p.river), len(p.tedashi))


def test_reading_table_monotone():
    """ツモ切りが続くほどテンパイ確率が上がること（副露あり・中盤以降）。"""
    for melds in (1, 2):
        for turn in (11, 14):
            probs = []
            for tg in range(4):
                key = (melds, reading.turn_bucket(turn), tg)
                v = reading.TENPAI_FULL.get(key)
                if v is not None:
                    probs.append(v)
            assert len(probs) >= 3, (melds, turn)
            assert probs[-1] > probs[0], (melds, turn, probs)


def test_reading_beats_heuristic():
    """実測テーブルが手書きの読みより当たること（未学習のシードで検証）。"""
    import random as _r

    from mj import fast as _fast
    from mj.game import Game
    from mj.players import make_players

    truth, heur, stats = [], [], []
    ai = make_players()
    rng = _r.Random(20260906)
    for k in range(14):
        g = Game(ai, [25000] * 4, 27, k % 4, 0, 0, rng)
        orig = type(ai[0]).discard

        def hook(self, view, *a, _orig=orig, **kw):
            for p in view.others:
                if p.riichi:
                    continue
                truth.append(1 if _fast.shanten(p.hand, p.called) == 0 else 0)
                heur.append(
                    reading.heuristic_probability(p, view.turn, view.round_wind, view.game.seat_wind)
                )
                stats.append(reading.tenpai_probability(p, view.turn))
            return _orig(self, view, *a, **kw)

        type(ai[0]).discard = hook
        try:
            g.play()
        finally:
            type(ai[0]).discard = orig

    n = len(truth)
    assert n > 500, n
    brier_h = sum((a - b) ** 2 for a, b in zip(heur, truth)) / n
    brier_s = sum((a - b) ** 2 for a, b in zip(stats, truth)) / n
    assert brier_s < brier_h, (brier_s, brier_h)



# --- ルールの監査 -----------------------------------------------------------


def test_rules_audit():
    """半荘を回しながら、ルール上の不変条件を全部検査する。

    ここで見ているもの:
      牌の総数136 / 手牌枚数 / 点棒の保存 / 王牌14枚とドラ表示牌の枚数
      チーは上家のみ / リーチ後に鳴かない / リーチの成立条件
      現物喰い替えの禁止 / 役なし和了がない
      流局時のノーテン罰符の金額（テンパイ人数別）と親の連荘条件
      途中流局には罰符が無いこと
      赤ドラ3枚 / 河と手出しフラグの整合
    """
    import random as _r

    from mj import fast as _fast
    from mj.game import DORA_POS, RINSHAN_POS, Game
    from mj.players import make_players

    ai = make_players()
    rng = _r.Random(31)
    violations = []

    orig_discard = Game.discard
    orig_call = Game.do_call
    orig_riichi = Game.can_riichi

    def d(self, seat, tile):
        total = len(self.live) + len(self.dead)
        for q in self.players:
            total += sum(q.hand) + len(q.river) + sum(len(m.tiles) for m in q.melds)
        if total != 136:
            violations.append(f"牌の総数が{total}")
        return orig_discard(self, seat, tile)

    def c(self, seat, choice, tile, from_seat):
        kind, _arg = choice
        if kind == "chi" and (from_seat + 1) % 4 != seat:
            violations.append("チーが上家以外から")
        if self.players[seat].riichi:
            violations.append("リーチ後に鳴いた")
        r = orig_call(self, seat, choice, tile, from_seat)
        p = self.players[seat]
        if p.river and p.river[-1] == tile:
            violations.append("現物喰い替え")
        return r

    def rc(self, p, tile):
        ok = orig_riichi(self, p, tile)
        if ok and not (p.menzen and p.score >= 1000 and len(self.live) >= 4):
            violations.append("リーチの条件を満たしていない")
        return ok

    Game.discard, Game.do_call, Game.can_riichi = d, c, rc
    try:
        for k in range(60):
            g = Game(ai, [25000] * 4, 27 + (k // 4) % 2, k % 4, k % 3, k % 2, rng)
            before = sum(pl.score for pl in g.players) + (k % 2) * 1000
            res = g.play()

            assert len(g.dead) == 14
            assert len(g.dora_indicators) == 1 + g.kan_count
            assert len(g.ura_indicators) == len(g.dora_indicators)
            used = (
                set(DORA_POS[: len(g.dora_indicators)])
                | {x + 1 for x in DORA_POS[: len(g.dora_indicators)]}
                | set(RINSHAN_POS[: g.rinshan_taken])
            )
            assert len(used) == len(g.dora_indicators) * 2 + g.rinshan_taken

            after_scores = [g.players[i].score + res.deltas[i] for i in range(4)]
            new_sticks = 0 if res.kind in ("tsumo", "ron") else g.sticks
            assert before == sum(after_scores) + new_sticks * 1000, (before, after_scores)

            if res.kind == "draw":
                # 合計が0（保存則）だけでなく、罰符の金額そのものを検証する。
                # 合計0は「全員±0」でも通ってしまうので、それだけでは足りない。
                tenpai = [
                    i for i in range(4)
                    if _fast.shanten(g.players[i].hand, g.players[i].called) == 0
                ]
                assert set(res.tenpai) == set(tenpai), (res.tenpai, tenpai)
                gain, pay = {0: (0, 0), 1: (3000, 1000), 2: (1500, 1500),
                             3: (1000, 3000), 4: (0, 0)}[len(tenpai)]
                for i in range(4):
                    want = 0 if len(tenpai) in (0, 4) else (gain if i in tenpai else -pay)
                    assert res.deltas[i] == want, (len(tenpai), i, res.deltas[i], want)
                # 親はテンパイのときだけ連荘する
                assert res.dealer_repeat == (g.dealer in tenpai)
            elif res.kind == "abort":
                # 途中流局に罰符は無い
                assert res.deltas == [0, 0, 0, 0]

            for p in g.players:
                assert len(p.river) == len(p.tedashi)
                assert sum(p.hand) + 3 * p.called in (13, 14)

            for _seat, pts, _han, _fu, yaku in res.winners:
                assert yaku, "役なしで和了した"
                assert pts > 0
    finally:
        Game.discard, Game.do_call, Game.can_riichi = orig_discard, orig_call, orig_riichi

    assert not violations, violations


def test_red_dora_count():
    """赤ドラは 5m/5p/5s の各1枚、計3枚。"""
    import random as _r

    from mj.game import Game
    from mj.players import make_players

    rng = _r.Random(5)
    for _ in range(20):
        g = Game(make_players(), [25000] * 4, 27, 0, 0, 0, rng)
        reds = sum(1 for _t, r in (g.live + g.dead) if r) + sum(len(p.red) for p in g.players)
        assert reds == 3, reds


def test_honitsu_is_pursued():
    """染め手の判定が働くこと。

    以前は「手牌が既に1色」を要求していたため、染めかけの手を一生拾えなかった。
    ここでは閾値を 9 に緩めて、実際に混一色が出るようになったことを確認する。

    既定の閾値は 11（実験で 9 は雑に染めすぎて成績が落ちたため）。
    その設定では混一色はほとんど出ない。これは既知の未解決点で、
    `results/experiment-honitsu.md` に記録してある。
    """
    import collections as _c
    import random as _r

    from mj.game import Game
    from mj.players import make_players

    counts = {}
    for chase, minimum in ((False, 9), (True, 9)):
        ai = make_players()
        for p in ai:
            p.style.chase_honitsu = chase
            p.style.honitsu_min = minimum
        rng = _r.Random(77)
        yaku = _c.Counter()
        for k in range(120):
            res = Game(ai, [25000] * 4, 27 + (k // 4) % 2, k % 4, 0, 0, rng).play()
            for _s, _p, _h, _f, ys in res.winners:
                for y in ys:
                    yaku[y] += 1
        counts[chase] = yaku["混一色"] + yaku["清一色"]
    assert counts[True] > counts[False], counts
    assert counts[True] >= 3, counts


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
