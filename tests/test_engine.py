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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
