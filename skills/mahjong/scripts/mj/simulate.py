"""半荘の進行とシミュレーション。

雀魂・段位戦の半荘（東南戦）に合わせてある:
  - 25000点持ち / 30000点返し
  - 親のアガリ・親テンパイ流局で連荘
  - 南4終了時に誰も30000点に届かなければ西入（西4で強制終了）
  - 誰かが0点未満になったら即終了（飛び）
  - 南場以降、親がトップかつ30000点以上でアガれば終了（和了やめ）
  - 同点は起家に近いほうが上位
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field

from .game import Game
from .players import make_awareness_lab, make_players

ROUND_NAMES = ["東", "南", "西"]


@dataclass
class Stats:
    hands: int = 0
    wins: int = 0
    tsumo: int = 0
    deals: int = 0  # 放銃
    calls: int = 0  # 副露した局
    riichi: int = 0
    win_points: int = 0
    deal_points: int = 0
    tenpai_at_draw: int = 0
    draws: int = 0
    ranks: list = field(default_factory=lambda: [0, 0, 0, 0])
    total_score: int = 0
    hanchan: int = 0

    def merge(self, o: "Stats") -> None:
        self.hands += o.hands
        self.wins += o.wins
        self.tsumo += o.tsumo
        self.deals += o.deals
        self.calls += o.calls
        self.riichi += o.riichi
        self.win_points += o.win_points
        self.deal_points += o.deal_points
        self.tenpai_at_draw += o.tenpai_at_draw
        self.draws += o.draws
        self.total_score += o.total_score
        self.hanchan += o.hanchan
        for i in range(4):
            self.ranks[i] += o.ranks[i]


def play_hanchan(ai_players, rng, start_offset=0):
    """1半荘。ai_players[i] が席 i に座る。start_offset は起家をずらす量。"""
    order = [ai_players[(i + start_offset) % 4] for i in range(4)]
    scores = [25000] * 4
    stats = {p.name: Stats() for p in ai_players}

    round_wind_idx = 0
    kyoku = 0  # 0-3 = 1〜4局
    honba = 0
    sticks = 0
    guard = 0

    while True:
        guard += 1
        if guard > 60:
            break
        dealer = kyoku
        g = Game(order, scores, 27 + round_wind_idx, dealer, honba, sticks, rng)
        res = g.play()

        for i in range(4):
            st = stats[order[i].name]
            st.hands += 1
            if g.players[i].riichi:
                st.riichi += 1
            if g.players[i].open_melds:
                st.calls += 1
        if res.kind in ("tsumo", "ron"):
            for seat, pts, han, fu, yaku in res.winners:
                st = stats[order[seat].name]
                st.wins += 1
                st.win_points += pts
                if res.kind == "tsumo":
                    st.tsumo += 1
            if res.loser is not None:
                st = stats[order[res.loser].name]
                st.deals += 1
                st.deal_points += -res.deltas[res.loser]
        elif res.kind == "draw":
            for i in range(4):
                stats[order[i].name].draws += 1
                if i in res.tenpai:
                    stats[order[i].name].tenpai_at_draw += 1

        for i in range(4):
            scores[i] = g.players[i].score + res.deltas[i]

        if res.kind in ("tsumo", "ron"):
            sticks = 0
        else:
            sticks = g.sticks

        # 飛び
        if any(s < 0 for s in scores):
            break

        if res.dealer_repeat:
            honba += 1
            # 和了やめ
            if (
                res.kind in ("tsumo", "ron")
                and round_wind_idx >= 1
                and kyoku == 3
                and scores[dealer] >= 30000
                and scores[dealer] == max(scores)
            ):
                break
            continue

        honba = 0 if res.kind in ("tsumo", "ron") else honba + 1
        kyoku += 1
        if kyoku == 4:
            kyoku = 0
            round_wind_idx += 1
            if round_wind_idx == 1:
                continue  # 南場へ
            if round_wind_idx == 2:
                if max(scores) >= 30000:
                    break
                continue  # 西入
            break  # 西4終了

    # 順位（同点は起家に近いほうが上）
    ranking = sorted(range(4), key=lambda i: (-scores[i], i))
    for rank, seat in enumerate(ranking):
        st = stats[order[seat].name]
        st.ranks[rank] += 1
        st.total_score += scores[seat]
        st.hanchan += 1
    return stats


def build_lineup(lineup: str = "named", awareness: str = "none"):
    """対戦カードを作る。

    named     : ゆうだい / なおき / きくちゃん / ゆみこ（awareness を全員に適用）
    awareness : 状況判断の範囲だけを変えた4人（ベース戦術は共通）
    """
    if lineup == "awareness":
        return make_awareness_lab()
    return make_players(awareness)


def run(n: int, seed: int = 0, progress=None, lineup: str = "named", awareness: str = "none"):
    ai = build_lineup(lineup, awareness)
    rng = random.Random(seed)
    total = {p.name: Stats() for p in ai}
    for i in range(n):
        s = play_hanchan(ai, rng, start_offset=i % 4)
        for name, st in s.items():
            total[name].merge(st)
        if progress and (i + 1) % progress == 0:
            print(f"  {i + 1}/{n} 半荘", flush=True)
    return total


PLACEMENT_PT = {0: 125, 1: 60, 2: -5, 3: -180}


def report(total, n) -> str:
    names = list(total)
    lines = []
    w = max(len(x) for x in names) + 1
    lines.append(f"{n}半荘の結果\n")
    lines.append(
        f"{'雀士':<{w}} {'平均順位':>7} {'1着':>6} {'2着':>6} {'3着':>6} {'4着':>6} {'平均点':>8} {'段位pt/半荘':>11}"
    )
    lines.append("-" * (w + 60))
    rows = []
    for name in names:
        st = total[name]
        h = st.hanchan or 1
        avg_rank = sum((i + 1) * st.ranks[i] for i in range(4)) / h
        pt = sum(PLACEMENT_PT[i] * st.ranks[i] for i in range(4)) / h
        rows.append((avg_rank, name, st, pt))
    rows.sort()
    for avg_rank, name, st, pt in rows:
        h = st.hanchan or 1
        lines.append(
            f"{name:<{w}} {avg_rank:>7.3f} "
            f"{st.ranks[0] / h * 100:>5.1f}% {st.ranks[1] / h * 100:>5.1f}% "
            f"{st.ranks[2] / h * 100:>5.1f}% {st.ranks[3] / h * 100:>5.1f}% "
            f"{st.total_score / h:>8.0f} {pt:>11.1f}"
        )
    lines.append("")
    lines.append(
        f"{'雀士':<{w}} {'和了率':>7} {'放銃率':>7} {'副露率':>7} {'立直率':>7} "
        f"{'平均和了':>9} {'平均放銃':>9} {'ツモ率':>7} {'流局聴牌':>9}"
    )
    lines.append("-" * (w + 70))
    for _, name, st, _ in rows:
        h = st.hands or 1
        lines.append(
            f"{name:<{w}} "
            f"{st.wins / h * 100:>6.2f}% {st.deals / h * 100:>6.2f}% "
            f"{st.calls / h * 100:>6.2f}% {st.riichi / h * 100:>6.2f}% "
            f"{st.win_points / max(1, st.wins):>9.0f} {st.deal_points / max(1, st.deals):>9.0f} "
            f"{st.tsumo / max(1, st.wins) * 100:>6.1f}% "
            f"{st.tenpai_at_draw / max(1, st.draws) * 100:>8.1f}%"
        )
    lines.append("")
    lines.append(f"総局数: {sum(total[n2].hands for n2 in names) // 4} 局 / 1半荘あたり {sum(total[n2].hands for n2 in names) / 4 / n:.2f} 局")
    lines.append("段位ptは玉の間の 1着+125 / 2着+60 / 3着-5 / 4着-180 を仮定した値。")
    return "\n".join(lines)
