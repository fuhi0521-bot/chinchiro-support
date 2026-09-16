"""和了役の分布を集計する。

エンジンの打ち筋が現実とずれていないかを確かめるための診断。
役の出現率が実戦統計と近ければ、少なくとも「人間と違う変な麻雀」には
なっていないと言える。

    python3 skills/mahjong/scripts/mj.py yaku --hanchan 10000 -j 4
"""

from __future__ import annotations

import collections
import os
import pickle
import random
import sys
from concurrent.futures import ProcessPoolExecutor

from .game import Game
from .players import make_players


def collect(hanchan: int, seed: int):
    """半荘を回して、和了ごとの役を数える。

    半荘の進行は `simulate.play_hanchan` に任せる（ロジックを二重に持たない）。
    """
    from .simulate import play_hanchan

    ai = make_players()
    rng = random.Random(seed)
    yaku = collections.Counter()
    han_dist = collections.Counter()
    fu_dist = collections.Counter()
    tally = dict(wins=0, tsumo=0, ron=0, draws=0, hands=0, points=0, han=0,
                 yakuman=0, hanchan=0, riichi_wins=0)

    def observe(g, res, sticks_before):
        tally["hands"] += 1
        if res.kind == "draw":
            tally["draws"] += 1
        for _seat, pts, han, fu, names in res.winners:
            tally["wins"] += 1
            tally["points"] += pts - sticks_before * 1000
            tally["tsumo" if res.kind == "tsumo" else "ron"] += 1
            if han:
                tally["han"] += han
                han_dist[min(han, 13)] += 1
                fu_dist[fu] += 1
            else:
                tally["yakuman"] += 1
            seen = set()
            for n in names:
                # 「役牌 白」「場風 東」などは種類でまとめる
                # 天鳳の統計は役牌を牌ごとに出しているので、こちらも牌別に持つ
                # （「役牌 白」はそのまま「役牌 白」で数える）
                key = n
                if key.startswith(("ドラ", "赤ドラ", "裏ドラ")) or key in seen:
                    continue
                seen.add(key)
                yaku[key] += 1
            if "立直" in seen or "ダブル立直" in seen:
                tally["riichi_wins"] += 1

    for i in range(hanchan):
        play_hanchan(ai, rng, start_offset=i % 4, on_result=observe)
        tally["hanchan"] += 1
        if (i + 1) % max(1, hanchan // 10) == 0:
            print(f"  {i + 1}/{hanchan} 半荘", flush=True)
    return yaku, han_dist, fu_dist, tally


def _worker(args):
    n, seed = args
    sys.setrecursionlimit(10000)
    return pickle.dumps(collect(n, seed))


def run(hanchan: int, seed: int = 1, workers: int = 0):
    workers = workers or min(4, os.cpu_count() or 1)
    if workers <= 1:
        return collect(hanchan, seed)
    per = hanchan // workers
    jobs = [(per + (1 if i < hanchan % workers else 0), seed + i * 7919) for i in range(workers)]
    jobs = [j for j in jobs if j[0] > 0]
    yaku = collections.Counter()
    han_dist = collections.Counter()
    fu_dist = collections.Counter()
    tally = None
    with ProcessPoolExecutor(max_workers=len(jobs)) as ex:
        for blob in ex.map(_worker, jobs):
            y, h, f, t = pickle.loads(blob)
            yaku.update(y)
            han_dist.update(h)
            fu_dist.update(f)
            tally = t if tally is None else {k: tally[k] + v for k, v in t.items()}
    return yaku, han_dist, fu_dist, tally


def report(yaku, han_dist, fu_dist, tally) -> str:
    w = tally["wins"] or 1
    lines = [
        f"{tally['hanchan']:,}半荘 / {tally['hands']:,}局 / 和了 {w:,}回",
        "",
        f"和了率(1局あたり全員合計) {w / max(1, tally['hands']) * 100:5.1f}%"
        f"   流局率 {tally['draws'] / max(1, tally['hands']) * 100:5.1f}%"
        f"   ツモ率 {tally['tsumo'] / w * 100:5.1f}%",
        f"平均和了打点(供託を除く) {tally['points'] / w:,.0f}点"
        f"   平均翻数 {tally['han'] / max(1, w - tally['yakuman']):.2f}"
        f"   1半荘あたり {tally['hands'] / max(1, tally['hanchan']):.2f}局",
        "",
        "役の出現率（和了に占める割合・ドラは除く）",
    ]
    for name, n in yaku.most_common():
        if n / w < 0.0005:
            continue
        lines.append(f"  {name:<16}{n / w * 100:6.2f}%  ({n:,})")
    lines.append("")
    lines.append("翻数の分布")
    tot = sum(han_dist.values()) or 1
    for h in sorted(han_dist):
        lines.append(f"  {h:2}翻: {han_dist[h] / tot * 100:5.2f}%")
    return "\n".join(lines)
