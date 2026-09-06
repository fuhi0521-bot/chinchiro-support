"""麻雀計算エンジンのコマンドライン。

    mj.py shanten  <手牌>              シャンテン数
    mj.py wait     <手牌13枚>          待ち牌と残り枚数
    mj.py discard  <手牌14枚>          何切る（受け入れ順）
    mj.py score    <手牌14枚> --win X  役・符・点数
    mj.py danger   --river ... --tiles ...  危険度の序列
    mj.py points   --han 3 --fu 40     点数表引き
    mj.py noten    --tenpai 2          ノーテン罰符
"""

from __future__ import annotations

import argparse
import sys

from .efficiency import discard_options, ukeire, waits
from .hand import parse_melds
from .safety import danger
from .score import base_points, noten_penalty, payments
from .shanten import shanten_detail
from .tiles import (
    NUM_TILES,
    TileError,
    counts_str,
    parse_counts,
    parse_tile,
    tile_str,
)
from .yaku import Context, evaluate, format_result

WINDS = {"東": 27, "南": 28, "西": 29, "北": 30, "east": 27, "south": 28, "west": 29, "north": 30}


def _wind(text: str) -> int:
    key = text.strip()
    if key in WINDS:
        return WINDS[key]
    return parse_tile(key)


def _counts(text: str):
    return parse_counts(text)


def cmd_shanten(args) -> None:
    counts, aka = _counts(args.hand)
    melds = parse_melds(args.melds)
    d = shanten_detail(counts, len(melds))
    print(f"手牌: {counts_str(counts)}" + (f" + {' '.join(map(str, melds))}" if melds else ""))
    label = {-1: "和了", 0: "テンパイ"}.get(d["best"], f"{d['best']}シャンテン")
    print(f"シャンテン: {d['best']}  ({label})")
    if "chiitoitsu" in d:
        print(f"  一般形 {d['standard']} / 七対子 {d['chiitoitsu']} / 国士 {d['kokushi']}")


def cmd_wait(args) -> None:
    counts, aka = _counts(args.hand)
    melds = parse_melds(args.melds)
    visible = _counts(args.visible)[0] if args.visible else None
    w = waits(counts, len(melds), visible)
    print(f"手牌: {counts_str(counts)}" + (f" + {' '.join(map(str, melds))}" if melds else ""))
    if not w:
        s, acc = ukeire(counts, len(melds), visible)
        print(f"テンパイしていません（{s}シャンテン）")
        print("受け入れ: " + " ".join(f"{tile_str(t)}({n})" for t, n in acc))
        print(f"  {len(acc)}種{sum(n for _, n in acc)}枚")
        return
    print("待ち: " + " ".join(f"{tile_str(t)}({n}枚)" for t, n in w))
    print(f"  {len(w)}種{sum(n for _, n in w)}枚")


def cmd_discard(args) -> None:
    counts, aka = _counts(args.hand)
    melds = parse_melds(args.melds)
    visible = _counts(args.visible)[0] if args.visible else None
    opts = discard_options(counts, len(melds), visible)
    print(f"手牌: {counts_str(counts)}" + (f" + {' '.join(map(str, melds))}" if melds else ""))
    for o in opts[: args.top]:
        print(o.describe())


def cmd_score(args) -> None:
    counts, aka = _counts(args.hand)
    melds = parse_melds(args.melds)
    ctx = Context(
        is_tsumo=args.tsumo,
        riichi=args.riichi,
        double_riichi=args.double_riichi,
        ippatsu=args.ippatsu,
        chankan=args.chankan,
        rinshan=args.rinshan,
        haitei=args.haitei,
        houtei=args.houtei,
        tenhou=args.tenhou,
        chiihou=args.chiihou,
        seat_wind=_wind(args.seat),
        round_wind=_wind(args.round),
        dora=args.dora,
        uradora=args.uradora,
        aka=aka + args.aka,
        honba=args.honba,
        riichi_sticks=args.sticks,
        kuitan=not args.no_kuitan,
        kiriage=args.kiriage,
    )
    r = evaluate(counts, melds, parse_tile(args.win), ctx)
    seat = "親" if ctx.is_dealer else "子"
    print(f"手牌: {counts_str(counts)}" + (f" + {' '.join(map(str, melds))}" if melds else ""))
    print(f"和了牌: {args.win}  {'ツモ' if args.tsumo else 'ロン'}  {seat}")
    print(format_result(r))
    if args.fu_detail and r.fu_detail:
        print("符の内訳:")
        for line in r.fu_detail:
            print(f"    {line}")


def cmd_points(args) -> None:
    base, name = base_points(args.han, args.fu, kiriage=args.kiriage)
    for dealer in (False, True):
        for tsumo in (False, True):
            p = payments(base, is_dealer=dealer, is_tsumo=tsumo, honba=args.honba)
            who = "親" if dealer else "子"
            how = "ツモ" if tsumo else "ロン"
            print(f"{who}{how}: {p.text:<14} 合計 {p.total}点")
    if name:
        print(f"（{name}）")


def cmd_danger(args) -> None:
    river, _ = _counts(args.river)
    seen = _counts(args.visible)[0] if args.visible else None
    if args.tiles:
        cands, _ = parse_counts(args.tiles)
        candidates = [t for t in range(NUM_TILES) if cands[t]]
    else:
        candidates = list(range(NUM_TILES))
    for d in danger(candidates, river, seen, late=not args.early):
        print(d)


def cmd_noten(args) -> None:
    gain, pay = noten_penalty(args.tenpai)
    if gain == 0:
        print("全員テンパイ / 全員ノーテン: 罰符なし")
    else:
        print(f"テンパイ者: +{gain}点 / ノーテン者: -{pay}点")


def cmd_oorasu(args) -> None:
    from .placement import describe, rank_after_draw, ranking

    scores = [int(x) for x in args.scores.replace(",", " ").split()]
    if len(scores) != 4:
        raise TileError("点数は4人ぶん指定してください（例: --scores 24000,25000,25500,25500）")
    me, dealer = args.me, args.dealer
    order = ranking(scores)
    print("席   点数    着順")
    for i in range(4):
        mark = " ←自分" if i == me else ("  (親)" if i == dealer else "")
        print(f"{i}  {scores[i]:>6}   {order.index(i) + 1}着{mark}")
    print()
    print(describe(scores, me, dealer, args.honba, args.sticks))
    print()
    print(f"流局: 自分だけテンパイ → {rank_after_draw(scores, me, {me}) + 1}着 / "
          f"自分だけノーテン → {rank_after_draw(scores, me, {i for i in range(4) if i != me}) + 1}着")


def cmd_yaku(args) -> None:
    from .yakustats import report, run

    print(report(*run(args.hanchan, seed=args.seed, workers=args.workers)))


def cmd_match(args) -> None:
    from .tournament import match
    from .simulate import report

    total = match(
        args.hanchan, seed=args.seed, workers=args.workers,
        lineup=args.lineup, awareness=args.awareness,
    )
    print(report(total, args.hanchan))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mj", description="麻雀の計算エンジン")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_hand(sp, visible=False):
        sp.add_argument("hand", help="例: 123m456p789s11122z (赤5は 0m/0p/0s)")
        sp.add_argument("--melds", "-M", default=None, help="例: chi=234p,pon=白,ankan=5s")
        if visible:
            sp.add_argument("--visible", "-V", default=None, help="場に見えている牌（河・ドラ表示など）")

    s = sub.add_parser("shanten", help="シャンテン数")
    add_hand(s)
    s.set_defaults(func=cmd_shanten)

    s = sub.add_parser("wait", help="待ち牌 / 受け入れ")
    add_hand(s, visible=True)
    s.set_defaults(func=cmd_wait)

    s = sub.add_parser("discard", help="何切る")
    add_hand(s, visible=True)
    s.add_argument("--top", type=int, default=6, help="上位いくつ表示するか")
    s.set_defaults(func=cmd_discard)

    s = sub.add_parser("score", help="役・符・点数")
    add_hand(s)
    s.add_argument("--win", "-w", required=True, help="和了牌")
    s.add_argument("--tsumo", action="store_true")
    s.add_argument("--riichi", action="store_true")
    s.add_argument("--double-riichi", action="store_true")
    s.add_argument("--ippatsu", action="store_true")
    s.add_argument("--chankan", action="store_true")
    s.add_argument("--rinshan", action="store_true")
    s.add_argument("--haitei", action="store_true")
    s.add_argument("--houtei", action="store_true")
    s.add_argument("--tenhou", action="store_true")
    s.add_argument("--chiihou", action="store_true")
    s.add_argument("--seat", default="南", help="自風（東=親）")
    s.add_argument("--round", default="東", help="場風")
    s.add_argument("--dora", type=int, default=0)
    s.add_argument("--uradora", type=int, default=0)
    s.add_argument("--aka", type=int, default=0, help="手牌表記に 0m 等を使わない場合の赤ドラ枚数")
    s.add_argument("--honba", type=int, default=0)
    s.add_argument("--sticks", type=int, default=0, help="供託リーチ棒")
    s.add_argument("--no-kuitan", action="store_true")
    s.add_argument("--kiriage", action="store_true", help="切り上げ満貫あり（雀魂の段位戦は無し）")
    s.add_argument("--fu-detail", action="store_true")
    s.set_defaults(func=cmd_score)

    s = sub.add_parser("points", help="翻・符から点数を引く")
    s.add_argument("--han", type=int, required=True)
    s.add_argument("--fu", type=int, default=30)
    s.add_argument("--honba", type=int, default=0)
    s.add_argument("--kiriage", action="store_true")
    s.set_defaults(func=cmd_points)

    s = sub.add_parser("danger", help="危険度の序列")
    s.add_argument("--river", "-r", required=True, help="相手の捨て牌")
    s.add_argument("--tiles", "-t", default=None, help="候補牌（省略時は全種）")
    s.add_argument("--visible", "-V", default=None, help="場に見えている全ての牌")
    s.add_argument("--early", action="store_true", help="序盤（字牌の危険度を下げる）")
    s.set_defaults(func=cmd_danger)

    s = sub.add_parser("oorasu", help="オーラスの着順条件を計算する")
    s.add_argument("--scores", "-s", required=True, help="4人の点数（席0から順に）例: 24000,25000,25500,25500")
    s.add_argument("--me", "-m", type=int, required=True, help="自分の席 0-3")
    s.add_argument("--dealer", "-d", type=int, default=3, help="親の席 0-3")
    s.add_argument("--honba", type=int, default=0)
    s.add_argument("--sticks", type=int, default=0, help="場に出ているリーチ棒")
    s.set_defaults(func=cmd_oorasu)

    s = sub.add_parser("match", help="4人のAI雀士で対戦させる")
    s.add_argument("--hanchan", "-n", type=int, default=100)
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--workers", "-j", type=int, default=0, help="並列プロセス数（0で自動）")
    s.add_argument("--lineup", default="named", choices=["named", "awareness", "reading", "reading-push", "honitsu", "shape", "five", "six"],
                   help="named=4人 / five=5人 / six=6人（抜け番あり） / awareness / reading / reading-push / honitsu")
    s.add_argument("--awareness", default="none", choices=["none", "allast", "south", "always"],
                   help="named のとき、4人全員に適用する状況判断の範囲")
    s.set_defaults(func=cmd_match)

    s = sub.add_parser("yaku", help="和了役の分布を集計する（打ち筋の診断）")
    s.add_argument("--hanchan", "-n", type=int, default=1000)
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--workers", "-j", type=int, default=0)
    s.set_defaults(func=cmd_yaku)

    s = sub.add_parser("noten", help="ノーテン罰符")
    s.add_argument("--tenpai", type=int, required=True, help="テンパイ者の人数 0-4")
    s.set_defaults(func=cmd_noten)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except TileError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    return 0
