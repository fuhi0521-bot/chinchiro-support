"""1つの局面を、これまで作った道具ぜんぶで診断する。

    mj.py review --hand 3456778m234p55s99s --dora 3s --turn 8 \
                 --river "1m9p東南5s7m" --visible "1m9p東南5s7m2p3p"

`discard` `wait` `danger` `oorasu` を別々に呼ぶ代わりに、
**SKILL.md のモード1の順番**（結論 → 形 → 場況 → 着順 → 次点との差）で
まとめて出す。牌譜を読み込む機能が無いので、
自分の対局を振り返るときはこれに局面を入れて使う。
"""

from __future__ import annotations

from . import wall
from .efficiency import discard_options, waits
from .safety import danger
from .tiles import HONOR, NUM_TILES, counts_str, dora_from_indicator, tile_str


def _fmt_accepts(accepts, limit=9):
    return " ".join(f"{tile_str(t)}{n}" for t, n in accepts[:limit])


def _wall_note(t: int, left: int) -> str:
    """残り枚数のうち、どれくらいが山にありそうかを一言で。

    left は「見えていない枚数」（自分の手牌も引いた実質の残り）。
    references/wall-reading.md の実測値。見えていない1枚が山にある確率:
      字牌 84.5% / 1・9 62.2% / 2・8 53.4% / 3・7 50.9% / 4・6 49.7% / 5 49.8%
    残りは相手の手の中にある。**山に多い牌ほど出てこない**ので、
    ツモを狙うのか出和了りを狙うのかで読み方が変わる。
    """
    if left <= 0:
        return "枯れ"
    if t >= HONOR:
        return f"山に約{left * 0.85:.1f}枚（残りやすいが出ない）"
    r = t % 9 + 1
    p = {1: .62, 9: .62, 2: .53, 8: .53, 3: .51, 7: .51}.get(r, .50)
    return f"山に約{left * p:.1f}枚（残りは相手の手の中）"


def review(
    counts,
    called: int = 0,
    *,
    visible=None,
    dora_indicators=(),
    turn: int | None = None,
    river=None,
    scores=None,
    me: int = 0,
    dealer: int = 3,
    honba: int = 0,
    sticks: int = 0,
    is_dealer: bool = False,
) -> str:
    out = []
    n = sum(counts) + 3 * called
    dora = [dora_from_indicator(i) for i in dora_indicators]
    seen = list(visible) if visible else [0] * NUM_TILES

    head = f"手牌 {counts_str(counts)}"
    if called:
        head += f" + 副露{called}"
    if dora:
        head += f"   ドラ {' '.join(tile_str(d) for d in dora)}"
    if turn:
        head += f"   {turn}巡目"
    out.append(head)
    out.append("=" * 60)

    # ---- 1. 何切る / 待ち -------------------------------------------------
    if n == 14:
        opts = discard_options(counts, called, seen)
        top = opts[0]
        label = {-1: "和了", 0: "テンパイ"}.get(top.shanten, f"{top.shanten}シャンテン")
        out.append(f"\n■ 結論: 打{tile_str(top.tile)}   （切ると {label}）")
        if top.shanten == 0:
            w = top.accepts
            width = sum(x for _, x in w)
            out.append(f"   待ち {' '.join(tile_str(t) for t, _ in w)}  実質{width}枚")
            for t, c in w:
                out.append(f"     {tile_str(t)}  残り{c}枚  {_wall_note(t, c)}")
        else:
            out.append(f"   受け入れ {top.kinds}種{top.width}枚: {_fmt_accepts(top.accepts)}")

        out.append("\n■ 次点との差")
        for o in opts[1:4]:
            mark = " ※ドラ" if o.tile in dora else ""
            if o.shanten != top.shanten:
                # シャンテンが戻る打牌は枚数で比べても意味がない
                out.append(f"   打{tile_str(o.tile)}  {o.shanten}シャンテンに戻る"
                           f"  → 論外{mark}")
                continue
            gap = o.width - top.width
            verdict = "ほぼ互角" if abs(gap) <= 2 else "明確に劣る"
            out.append(f"   打{tile_str(o.tile)}  同シャンテン {o.width}枚 ({gap:+d})"
                       f"  → {verdict}{mark}")
    elif n == 13:
        w = waits(counts, called, seen)
        if w:
            width = sum(x for _, x in w)
            out.append(f"\n■ テンパイ。待ち {' '.join(tile_str(t) for t, _ in w)}  実質{width}枚")
            for t, c in w:
                out.append(f"     {tile_str(t)}  残り{c}枚  {_wall_note(t, c)}")
        else:
            from . import fast
            out.append(f"\n■ {fast.shanten(list(counts), called)}シャンテン")
    else:
        out.append(f"\n(手牌が {n} 枚。13枚か14枚で渡してください)")

    # ---- 2. 危険度 --------------------------------------------------------
    if river:
        river_counts = [0] * NUM_TILES
        for t in river:
            river_counts[t] += 1
        cands = [t for t in range(NUM_TILES) if counts[t]]
        ds = danger(cands, river_counts, seen, late=(turn or 8) >= 8)
        out.append("\n■ 場況: 手牌の中の安全な順")
        for d in ds[:6]:
            out.append(f"   {d}")
        out.append("   ※ リーチ後に他家が切って通った牌も現物。--river に足して数えること")

    # ---- 3. 着順条件 ------------------------------------------------------
    if scores:
        from .placement import describe, rank_after_draw, ranking

        order = ranking(scores)
        out.append("\n■ 着順状況")
        for i in range(4):
            mark = " ←自分" if i == me else ("  (親)" if i == dealer else "")
            out.append(f"   席{i}  {scores[i]:>6}   {order.index(i) + 1}着{mark}")
        out.append("   " + describe(scores, me, dealer, honba, sticks).replace("\n", "\n   "))
        out.append(f"   流局: 自分だけテンパイ → {rank_after_draw(scores, me, {me}) + 1}着 / "
                   f"自分だけノーテン → "
                   f"{rank_after_draw(scores, me, {i for i in range(4) if i != me}) + 1}着")

    return "\n".join(out)


__all__ = ["review"]
