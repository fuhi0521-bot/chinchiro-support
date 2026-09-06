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

        def hook(self, view, _orig=orig):
            for p in view.others:
                if p.riichi:
                    continue
                truth.append(1 if _fast.shanten(p.hand, p.called) == 0 else 0)
                heur.append(
                    reading.heuristic_probability(p, view.turn, view.round_wind, view.game.seat_wind)
                )
                stats.append(reading.tenpai_probability(p, view.turn))
            return _orig(self, view)

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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
