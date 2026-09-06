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
from .players import (
    make_awareness_lab,
    make_fifth,
    make_players,
    make_reading_lab,
    make_honitsu_lab,
    make_reading_push_lab,
)

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
    # オーラスに入った時点の着順 → 最終着順 の変化。打ち回しの効果はここに出る
    allast_seen: int = 0
    allast_up: int = 0
    allast_same: int = 0
    allast_down: int = 0
    allast_entered_last: int = 0  # オーラス開始時にラス目だった回数
    allast_escaped_last: int = 0  # そこからラスを脱出した回数
    allast_entered_top: int = 0
    allast_kept_top: int = 0

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
        for k in (
            "allast_seen", "allast_up", "allast_same", "allast_down",
            "allast_entered_last", "allast_escaped_last",
            "allast_entered_top", "allast_kept_top",
        ):
            setattr(self, k, getattr(self, k) + getattr(o, k))


def play_hanchan(ai_players, rng, start_offset=0, on_result=None):
    """1半荘。ai_players[i] が席 i に座る。start_offset は起家をずらす量。

    on_result(game, result, sticks_before) を渡すと、1局ごとに呼ばれる。
    集計用のフックで、進行そのものには影響しない。
    """
    order = [ai_players[(i + start_offset) % 4] for i in range(4)]
    scores = [25000] * 4
    stats = {p.name: Stats() for p in ai_players}

    round_wind_idx = 0
    kyoku = 0  # 0-3 = 1〜4局
    honba = 0
    sticks = 0
    guard = 0
    allast_entry = None  # オーラスに入った時点の点数

    while True:
        guard += 1
        if guard > 60:
            break
        dealer = kyoku
        if allast_entry is None and round_wind_idx >= 1 and kyoku == 3:
            allast_entry = list(scores)
        g = Game(order, scores, 27 + round_wind_idx, dealer, honba, sticks, rng)
        sticks_before = sticks
        res = g.play()
        if on_result is not None:
            on_result(g, res, sticks_before)

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

    # オーラスでの着順の動き
    if allast_entry is not None:
        entry_rank = {s: i for i, s in enumerate(sorted(range(4), key=lambda i: (-allast_entry[i], i)))}
        for seat in range(4):
            st = stats[order[seat].name]
            before = entry_rank[seat]
            after = ranking.index(seat)
            st.allast_seen += 1
            if after < before:
                st.allast_up += 1
            elif after > before:
                st.allast_down += 1
            else:
                st.allast_same += 1
            if before == 3:
                st.allast_entered_last += 1
                if after < 3:
                    st.allast_escaped_last += 1
            if before == 0:
                st.allast_entered_top += 1
                if after == 0:
                    st.allast_kept_top += 1
    return stats


def build_lineup(lineup: str = "named", awareness: str = "none"):
    """対戦カードを作る。

    named     : ゆうだい / なおき / きくちゃん / ゆみこ（awareness を全員に適用）
    awareness : 状況判断の範囲だけを変えた4人（ベース戦術は共通）
    reading   : 読み方だけを変えた4人（手書き / 統計 / 手出し込み / 全知）
    reading-push : 読みの精度 × 押し引きの閾値
    """
    if lineup == "awareness":
        return make_awareness_lab()
    if lineup == "reading":
        return make_reading_lab()
    if lineup == "reading-push":
        return make_reading_push_lab()
    if lineup == "honitsu":
        return make_honitsu_lab()
    if lineup == "five":
        # 麻雀は4人でしか打てないので、5人だと毎半荘1人が抜け番になる
        return make_players(awareness) + [make_fifth()]
    return make_players(awareness)


def seat_for(ai, i: int):
    """i半荘目に座る4人を返す。

    5人以上いるときは1人ずつ抜け番にして順に回す。
    5人なら20半荘で、全員が各席に同じ回数座り、抜け番も同じ回数になる。
    """
    k = len(ai)
    if k == 4:
        return [ai[(i + j) % 4] for j in range(4)]
    return [ai[(i + j) % k] for j in range(4)]


def run(n: int, seed: int = 0, progress=None, lineup: str = "named", awareness: str = "none"):
    ai = build_lineup(lineup, awareness)
    rng = random.Random(seed)
    total = {p.name: Stats() for p in ai}
    for i in range(n):
        seated = seat_for(ai, i)
        s = play_hanchan(seated, rng, start_offset=0)
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
    lines.append("")
    lines.append(f"{'雀士':<{w}} {'オーラス':>8} {'着順UP':>8} {'維持':>7} {'DOWN':>7} {'ラス脱出':>9} {'トップ死守':>11}")
    lines.append("-" * (w + 55))
    for _, name, st, _ in rows:
        a = st.allast_seen or 1
        el = st.allast_entered_last or 1
        et = st.allast_entered_top or 1
        lines.append(
            f"{name:<{w}} {st.allast_seen:>8} {st.allast_up / a * 100:>7.1f}% "
            f"{st.allast_same / a * 100:>6.1f}% {st.allast_down / a * 100:>6.1f}% "
            f"{st.allast_escaped_last / el * 100:>8.1f}% ({st.allast_entered_last}) "
            f"{st.allast_kept_top / et * 100:>7.1f}% ({st.allast_entered_top})"
        )
    lines.append("")
    lines.append(f"総局数: {sum(total[n2].hands for n2 in names) // 4} 局 / 1半荘あたり {sum(total[n2].hands for n2 in names) / 4 / n:.2f} 局")
    lines.append("段位ptは玉の間の 1着+125 / 2着+60 / 3着-5 / 4着-180 を仮定した値。")
    return "\n".join(lines)
