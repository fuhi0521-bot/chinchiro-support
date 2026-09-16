"""各エージェントが自分の半荘を振り返り、良い点と反省点を出す。

感想ではなく、**測定値から機械的に診断する**。
判断の根拠はこれまでの実験で測った次の関係。

  平均順位 = 3.491 − 0.0543 × 和了率(%)      R² = 0.953（6人打ち3000半荘）

  → 和了率1ptは平均順位0.054に相当する。
  → 放銃率と順位の相関は −0.857 で **符号が逆**。この環境では
     「放銃を減らす」方向の改善は順位に繋がらない。

だから診断は和了率と、その源である「流局時テンパイ率」を主軸に置く。
放銃率は、和了率を犠牲にしていないかの確認にだけ使う。

実戦の目安（出典は references/probability.md）:
  和了率 21〜22% / 放銃率 11〜12% / 副露率 32.6% / 立直率 18.4% / 流局率 16.0%
"""

from __future__ import annotations

from dataclasses import dataclass

# 実戦の目安（天鳳鳳凰卓。出典は references/probability.md の末尾）
REAL = dict(win=21.5, deal=11.5, call=32.6, riichi=18.4, tenpai_at_draw=50.0)

# 和了率1ptあたりの平均順位への効果（6人打ち3000半荘の回帰から）
RANK_PER_WIN_PT = 0.0543


@dataclass
class Finding:
    kind: str  # "良い点" / "反省点"
    text: str
    fix: str = ""  # パラメータの修正案（あれば）


def review(name: str, st, field: dict) -> list[Finding]:
    """1人ぶんの振り返り。field は場の平均（同じ卓の全員の平均）。"""
    h = st.hands or 1
    win = st.wins / h * 100
    deal = st.deals / h * 100
    call = st.calls / h * 100
    riichi = st.riichi / h * 100
    tenpai = st.tenpai_at_draw / max(1, st.draws) * 100
    avg_win = st.win_points / max(1, st.wins)
    rank = sum((i + 1) * st.ranks[i] for i in range(4)) / max(1, st.hanchan)
    out: list[Finding] = []

    # --- 良い点 ---
    if win >= field["win"] + 0.5:
        out.append(Finding("良い点", f"和了率 {win:.2f}% は場の平均より {win - field['win']:+.2f}pt 高い。"
                                    f"順位に換算すると {(win - field['win']) * RANK_PER_WIN_PT:.3f} 相当の貢献"))
    if tenpai >= field["tenpai"] + 3:
        out.append(Finding("良い点", f"流局時テンパイ率 {tenpai:.1f}% が高い（場の平均 {field['tenpai']:.1f}%）。"
                                    f"最後まで手を進められている"))
    if avg_win >= field["avg_win"] + 300:
        out.append(Finding("良い点", f"平均和了打点 {avg_win:.0f}点 が場の平均より {avg_win - field['avg_win']:+.0f}点 高い"))
    if deal <= field["deal"] - 1.0 and win >= field["win"] - 0.5:
        out.append(Finding("良い点", f"和了率を落とさずに放銃率 {deal:.2f}% を抑えている"))

    # --- 反省点 ---
    if win < field["win"] - 0.5:
        gap = field["win"] - win
        # 押しで和了率を稼ぐのは割に合わないので、まず形の質を疑う
        fix = "shape_aware / 鳴きの基準を見直す（押しで稼ぐのは割に合わない）"
        if deal < field["deal"] - 1.5:
            fix = "push を下げる（放銃率も低いので、押す余地がある）"
        out.append(Finding(
            "反省点",
            f"和了率 {win:.2f}% が場の平均より {gap:.2f}pt 低い。"
            f"平均順位で {gap * RANK_PER_WIN_PT:.3f} の損。**これが最大の問題**",
            fix,
        ))
    if tenpai < field["tenpai"] - 3:
        out.append(Finding(
            "反省点",
            f"流局時テンパイ率 {tenpai:.1f}% が低い（場の平均 {field['tenpai']:.1f}%）。降りすぎている",
            "push を下げる / safety_weight を下げる",
        ))
    if deal > field["deal"] + 1.5 and win < field["win"]:
        out.append(Finding(
            "反省点",
            f"放銃率 {deal:.2f}% が高いのに和了率 {win:.2f}% が伸びていない。押し方が雑",
            "push を上げる / safety_weight を上げる",
        ))
    if avg_win < field["avg_win"] - 300 and win >= field["win"]:
        out.append(Finding(
            "反省点",
            f"平均和了打点 {avg_win:.0f}点 が低い。速いが安い",
            "value_weight を上げる / call_min_value を上げる",
        ))
    # --- 実戦との違い（順位のための反省とは分ける） ---
    #
    # 実戦の統計に近づけることと、この卓で勝つことは別。
    # 実際、副露率を実戦の32.6%に寄せた「かなめ鳴き絞」は
    # 和了率が1.83pt落ちて平均順位も -0.064 悪化した。
    # だからここは「直すべき欠点」ではなく「人間との違い」として出す。
    if abs(call - REAL["call"]) > 8:
        d = "多い" if call > REAL["call"] else "少ない"
        out.append(Finding(
            "実戦との違い",
            f"副露率 {call:.1f}%（実戦の目安 {REAL['call']}%より{d}）。"
            f"順位のためには直さなくてよい。人間らしさを上げたいときだけ調整する",
        ))
    if abs(riichi - REAL["riichi"]) > 5:
        d = "多い" if riichi > REAL["riichi"] else "少ない"
        out.append(Finding(
            "実戦との違い",
            f"立直率 {riichi:.1f}%（実戦の目安 {REAL['riichi']}%より{d}）",
        ))
    if not out:
        out.append(Finding("良い点", "場の平均から大きく外れている指標はない"))
    return out


def field_average(total: dict) -> dict:
    """場の平均。自分を含む全員の平均を基準にする。"""
    n = len(total)
    def avg(f):
        return sum(f(s) for s in total.values()) / n
    return dict(
        win=avg(lambda s: s.wins / max(1, s.hands) * 100),
        deal=avg(lambda s: s.deals / max(1, s.hands) * 100),
        tenpai=avg(lambda s: s.tenpai_at_draw / max(1, s.draws) * 100),
        avg_win=avg(lambda s: s.win_points / max(1, s.wins)),
    )


def report_all(total: dict) -> str:
    """全員ぶんの振り返りを1つの文字列にする。"""
    field = field_average(total)
    order = sorted(
        total.items(),
        key=lambda kv: sum((i + 1) * kv[1].ranks[i] for i in range(4)) / max(1, kv[1].hanchan),
    )
    lines = ["", "=" * 66, "各エージェントの振り返り", "=" * 66]
    lines.append(
        f"場の平均: 和了率 {field['win']:.2f}% / 放銃率 {field['deal']:.2f}% / "
        f"流局時テンパイ率 {field['tenpai']:.1f}% / 平均和了 {field['avg_win']:.0f}点"
    )
    for name, st in order:
        rank = sum((i + 1) * st.ranks[i] for i in range(4)) / max(1, st.hanchan)
        lines.append("")
        lines.append(f"── {name}（平均順位 {rank:.3f}）")
        for f in review(name, st, field):
            lines.append(f"   [{f.kind}] {f.text}")
            if f.fix:
                lines.append(f"           → {f.fix}")
    lines.append("")
    lines.append("※ 診断は「和了率1pt = 平均順位0.054」という実測の関係に基づく。")
    lines.append("   この環境では放銃率と順位の相関が逆（-0.857）なので、")
    lines.append("   放銃を減らす方向の改善は順位に繋がらない。")
    lines.append("   ただし **押しで和了率を稼ぐのは別**。押し引きの閾値だけを下げると")
    lines.append("   和了率 +0.29pt に対して放銃率 +1.28pt で、順位はむしろ悪化した。")
    lines.append("   和了率は「形の質・速度」で上げること。")
    return "\n".join(lines)
