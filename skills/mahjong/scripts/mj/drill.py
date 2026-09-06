"""練習問題を作る。打ち手が反復して上手くなるための出題器。

    python3 mj.py drill --kind discard -n 5
    python3 mj.py drill --kind discard -n 5 --answers

問題は **同じ --seed なら同じものが出る**。出題と答え合わせを別々に
呼べるようにしてあるので、先に問題だけ見て、考えてから答えを出せる。

出題の種類:
  discard  何切る。答えは受け入れ枚数で機械的に決まる
  danger   どれが安全か。リーチ者の河から危険度の序列を出す
  tenpai   相手はテンパイしているか。実際の手牌が正解
  wall     この待ちは山に何枚残っているか
"""

from __future__ import annotations

import random

from . import fast, reading, wall
from .efficiency import discard_options
from .game import Game
from .safety import danger
from .tiles import HONOR, NUM_TILES, counts_str, tile_str

ROUND_NAMES = {27: "東", 28: "南", 29: "西"}


def _deal(rng, n=14):
    wall_ = [t for t in range(NUM_TILES) for _ in range(4)]
    rng.shuffle(wall_)
    counts = [0] * NUM_TILES
    for t in wall_[:n]:
        counts[t] += 1
    return counts, wall_[n:]


def _river_str(p) -> str:
    out = []
    for i, t in enumerate(p.river):
        mark = "" if (i < len(p.tedashi) and p.tedashi[i]) else "ツ"
        if p.riichi and i == p.riichi_turn:
            mark += "リ"
        out.append(tile_str(t) + (f"({mark})" if mark else ""))
    return " ".join(out)


# ------------------------------------------------------------ 局面を1つ拾う

def sample(rng, want, tries: int = 60):
    """対局を回して、条件に合う局面を1つ拾う。

    want(view) が dict を返したらそれを採用して打ち切る。
    ランダムな14枚を配るより、実際の対局から取るほうが問題として自然。
    """
    from . import players as pl

    ai = pl.make_players()
    for _ in range(tries):
        g = Game(ai, [25000] * 4, 27, rng.randrange(4), 0, 0, rng)
        found = {}
        orig = pl.Player.discard

        def wrapped(self, view, forbidden=frozenset()):
            if not found:
                got = want(view)
                if got:
                    found.update(got)
            return orig(self, view, forbidden)

        pl.Player.discard = wrapped
        try:
            g.play()
        finally:
            pl.Player.discard = orig
        if found:
            return found
    return None


# ---------------------------------------------------------------- 何切る

def make_discard(rng):
    """実際の対局から何切るを拾う。候補が割れる局面だけを選ぶ。"""
    from .tiles import dora_from_indicator

    floor = rng.choice((2, 4, 6, 8, 10))

    def want(view):
        if view.turn < floor:
            return None
        me = view.me
        if sum(me.hand) != 14 or me.called or me.riichi:
            return None
        s = fast.shanten(me.hand, 0)
        if s not in (1, 2):
            return None
        seen = view.visible()
        opts = discard_options(list(me.hand), 0, seen)
        best = [o for o in opts if o.shanten == opts[0].shanten]
        if len(best) < 2:
            return None
        # 1位と2位に差がある問題だけ。同点だと「正解」が決まらない
        if not (1 <= best[0].width - best[1].width <= 8):
            return None
        return {
            "hand": list(me.hand),
            "dora": [dora_from_indicator(i) for i in view.game.dora_indicators],
            "turn": view.turn,
            "options": opts,
            "shanten": s,
            "rivers": [(p.seat, list(p.river)) for p in view.others],
        }

    return sample(rng, want)


def show_discard(q, i):
    return (f"[{i}] 何切る（{q['turn']}巡目 / {q['shanten']}シャンテン"
            f" / ドラ {' '.join(tile_str(d) for d in q['dora'])}）\n"
            f"    {counts_str(q['hand'])}")


def answer_discard(q, i):
    opts = q["options"]
    top = opts[0]
    dora = set(q["dora"])
    lines = [f"[{i}] 受け入れ最大: 打{tile_str(top.tile)}"
             f"   {top.width}枚 / {top.kinds}種"]
    for o in opts[1:3]:
        note = " ※ドラ" if o.tile in dora else ""
        lines.append(f"     次点: 打{tile_str(o.tile)}"
                     f"   {o.width}枚 ({o.width - top.width:+d}){note}")
    lines.append("     受け入れ: " + " ".join(
        f"{tile_str(t)}{n}" for t, n in top.accepts[:9]))
    if top.tile in dora:
        lines.append("     ※ 受け入れ最大の牌がドラ。打点と比べて決めること")
    return "\n".join(lines)


# ---------------------------------------------------------------- 危険度

def _winning_tiles(p):
    out = set()
    for t in range(NUM_TILES):
        if p.hand[t] >= 4:
            continue
        p.hand[t] += 1
        if fast.shanten(p.hand, p.called) < 0:
            out.add(t)
        p.hand[t] -= 1
    return out


def make_danger(rng):
    floor = rng.choice((7, 9, 11, 13))

    def want(view):
        if view.turn < floor or sum(view.me.hand) != 14:
            return None
        threats = [p for p in view.others if p.riichi]
        if not threats:
            return None
        t = threats[0]
        return {
            "hand": list(view.me.hand),
            "seen": view.seen_all(),
            "river": list(t.river),
            "tedashi": list(t.tedashi),
            "riichi_turn": t.riichi_turn,
            "waits": _winning_tiles(t),
            "turn": view.turn,
        }

    found = sample(rng, want)
    if not found:
        return None
    hand = found["hand"]
    cands = [t for t in range(NUM_TILES) if hand[t]]
    if len(cands) < 4:
        return None
    rng.shuffle(cands)
    cands = sorted(cands[:5])
    return {
        "river": found["river"],
        "tedashi": found["tedashi"],
        "riichi_turn": found["riichi_turn"],
        "turn": found["turn"],
        "candidates": cands,
        "waits": found["waits"],
        "hand": hand,
        "seen": found["seen"],
    }


def _river_text(river, tedashi, riichi_turn):
    out = []
    for i, t in enumerate(river):
        mark = ""
        if i >= len(tedashi) or not tedashi[i]:
            mark += "ツ"
        if i == riichi_turn:
            mark += "リ"
        out.append(tile_str(t) + (f"({mark})" if mark else ""))
    return " ".join(out)


def show_danger(q, i):
    return (f"[{i}] リーチ者への打牌（{q['turn']}巡目）\n"
            f"    相手の河: {_river_text(q['river'], q['tedashi'], q['riichi_turn'])}\n"
            f"    候補: {' '.join(tile_str(t) for t in q['candidates'])}\n"
            f"    どれが一番安全？  （ツ=ツモ切り リ=リーチ宣言牌）")


def answer_danger(q, i):
    river_counts = [0] * NUM_TILES
    for t in q["river"]:
        river_counts[t] += 1
    ds = danger(q["candidates"], river_counts, q["seen"], late=q["turn"] >= 8)
    lines = [f"[{i}] 安全な順:"]
    for d in ds:
        hit = " ← 当たり牌だった" if d.tile in q["waits"] else ""
        lines.append(f"     {d}{hit}")
    lines.append("     実際の待ち: " + " ".join(sorted(
        tile_str(t) for t in q["waits"])))
    return "\n".join(lines)


# ---------------------------------------------------------------- テンパイ読み

def make_tenpai(rng):
    floor = rng.choice((7, 9, 11, 13))

    def want(view):
        if view.turn < floor:
            return None
        others = list(view.others)
        rng.shuffle(others)
        for p in others:
            if p.riichi or len(p.river) < 6:
                continue
            # 門前でテンパイしている相手はほぼリーチしてしまうので、
            # 「読む」意味があるのは鳴いている相手。そちらを主に出す
            if not p.open_melds and rng.random() < 0.8:
                continue
            tenpai = fast.shanten(p.hand, p.called) == 0
            # テンパイしていない局面のほうが多いので、半分は捨てて均す
            if not tenpai and rng.random() < 0.6:
                continue
            return dict(
                river=list(p.river),
                tedashi=list(p.tedashi),
                melds=[tuple(m.tiles) for m in p.melds],
                turn=view.turn,
                tenpai=tenpai,
                shanten=fast.shanten(p.hand, p.called),
                guess=reading.tenpai_probability(p, view.turn),
            )
        return None

    return sample(rng, want)


def show_tenpai(q, i):
    melds = ("  副露: " + " / ".join(
        "".join(tile_str(t) for t in m) for m in q["melds"])) if q["melds"] else ""
    return (f"[{i}] この人はテンパイしている？（{q['turn']}巡目）\n"
            f"    河: {_river_text(q['river'], q['tedashi'], -1)}{melds}")


def answer_tenpai(q, i):
    truth = "テンパイ" if q["tenpai"] else f"{q['shanten']}シャンテン"
    return (f"[{i}] 正解: {truth}"
            f"   （エンジンの読み: テンパイ率 {q['guess'] * 100:.0f}%）")


# ---------------------------------------------------------------- 山読み

def make_wall(rng):
    floor = rng.choice((7, 9, 11, 13))

    def want(view):
        if view.turn < floor:
            return None
        me = view.me
        if fast.shanten(me.hand, me.called) > 1:
            return None
        seen = view.seen_all()
        # 「見えている枚数が同じ」牌を並べる。枚数だけでは差が付かない問題にする
        by_seen = {}
        for t in range(NUM_TILES):
            if seen[t] < 4:
                by_seen.setdefault(seen[t], []).append(t)
        pool = max(by_seen.values(), key=len)
        if len(pool) < 4:
            return None
        rng.shuffle(pool)
        pick = sorted(pool[:4])
        actual = [0] * NUM_TILES
        for t, _ in view.game.live:
            actual[t] += 1
        wc = wall.wall_counts(view, seen)
        return dict(
            tiles=pick,
            seen=[seen[t] for t in pick],
            actual=[actual[t] for t in pick],
            pred=[wc[t] for t in pick],
            turn=view.turn,
            left=view.wall_left,
            rivers=[" ".join(tile_str(x) for x in p.river) for p in view.others],
        )

    return sample(rng, want)


def show_wall(q, i):
    body = "  ".join(f"{tile_str(t)}（場に{s}枚見え）"
                     for t, s in zip(q["tiles"], q["seen"]))
    return (f"[{i}] 山読み（{q['turn']}巡目 / 山の残り {q['left']}枚）\n"
            f"    {body}\n"
            f"    このうち、いちばん山に残っているのはどれ？")


def answer_wall(q, i):
    rows = sorted(zip(q["tiles"], q["seen"], q["actual"], q["pred"]),
                  key=lambda r: -r[2])
    lines = [f"[{i}] 実際に山にあった枚数（多い順）:"]
    for t, s, a, pr in rows:
        lines.append(f"     {tile_str(t)}  実際 {a}枚 "
                     f"（見えている {s}枚 / 山読みの見積り {pr:.1f}枚）")
    return "\n".join(lines)


KINDS = {
    "discard": (make_discard, show_discard, answer_discard),
    "danger": (make_danger, show_danger, answer_danger),
    "tenpai": (make_tenpai, show_tenpai, answer_tenpai),
    "wall": (make_wall, show_wall, answer_wall),
}


def run(kind: str, n: int, seed: int, answers: bool) -> str:
    make, show, ans = KINDS[kind]
    rng = random.Random(seed)
    out = []
    made = 0
    tries = 0
    while made < n and tries < n * 6:
        tries += 1
        q = make(rng)
        if q is None:
            continue
        made += 1
        out.append(ans(q, made) if answers else show(q, made))
    if not out:
        return "問題を作れませんでした。--seed を変えて試してください。"
    head = f"■ {kind} の練習問題（--seed {seed}）"
    if answers:
        head = f"■ {kind} の答え（--seed {seed}）"
    else:
        head += "\n  答えは同じコマンドに --answers を付けて実行"
    return head + "\n\n" + "\n\n".join(out)


__all__ = ["run", "KINDS"]
