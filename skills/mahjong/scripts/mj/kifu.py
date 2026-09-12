"""雀魂の牌譜再生を録画したコマ列から、機械的に事実を取り出す。

牌の絵を目で読むのは当てにならない（実際、同じ局で3回読み違えた）。
なので **雀魂が数字と記号で出しているものだけ** を使う。

  持ち点     局の途中で動くのはリーチ棒だけ → リーチの検出
  待ち表示   テンパイしたか、待ちが何枚残っているか
  評価バッジ 雀魂AIの採点。金＝最善、青＝妥協、数字が大きいほど適切
             「打牌◯◯」と「立直◯◯」の2種類があり、リーチ判断も採点される
  手牌の差分 コマ間で消えた牌＝実際に切った牌（柄が読めなくても分かる）

検算に使った既知の事実（東2局）:
  リーチ=コマ113 / テンパイ=112 / 待ち1→0=117
"""
from PIL import Image
import numpy as np
import os

SCORE = (462, 196, 540, 214)   # 自分の持ち点の数字だけ
WAIT  = (288, 296, 372, 322)   # 「待ち◯◯ N」
BADGE = (170, 368, 890, 400)   # 手牌の上の評価バッジ（右端のUIは除く）
TOP   = (400, 409)             # 牌の上端の無地部分
FACE  = (396, 458)


def _img(d, n):
    p = os.path.join(d, f"{n:03d}.jpg")
    return Image.open(p) if os.path.exists(p) else None


def riichi_frame(d, a, b):
    """局頭から見て、持ち点が変わったまま戻らない最初のコマ。

    手番のハイライトは一瞬で戻るので、持続性で弾ける。
    """
    base = _img(d, a)
    if base is None:
        return None
    base = (np.asarray(base.crop(SCORE).convert("L"), dtype=np.float32) > 150)
    diff = []
    for n in range(a, b + 1):
        im = _img(d, n)
        if im is None:
            continue
        v = (np.asarray(im.crop(SCORE).convert("L"), dtype=np.float32) > 150)
        diff.append((n, float(np.abs(v.astype(float) - base).mean())))
    for i, (n, x) in enumerate(diff):
        if x > 0.04 and all(y > 0.04 for _, y in diff[i:]):
            return n
    return None


def wait_changes(d, a, b, tol=3.0):
    """「待ち」表示が変わったコマ。テンパイした瞬間と待ち替えが出る。"""
    prev, out = None, []
    for n in range(a, b + 1):
        im = _img(d, n)
        if im is None:
            continue
        v = np.asarray(im.crop(WAIT).convert("L"), dtype=np.float32)
        if prev is not None and np.abs(v - prev).mean() > tol:
            out.append(n)
        prev = v
    return out


def badges(d, n):
    """評価バッジの色と位置。金＝AIの最善、青＝妥協。"""
    im = _img(d, n)
    if im is None:
        return []
    a = np.asarray(im.crop(BADGE).convert("RGB"), dtype=np.int16)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    out = []
    for kind, m in (("金", (r > 170) & (g > 140) & (b < 110) & (r - b > 80)),
                    ("青", (b > 150) & (r < 110) & (b - r > 60))):
        cols = m.sum(0)
        segs = []
        for c in np.where(cols > 2)[0]:
            if segs and c - segs[-1][1] <= 4:
                segs[-1][1] = int(c)
            else:
                segs.append([int(c), int(c)])
        for s, e in segs:
            if e - s >= 8:
                out.append({"kind": kind, "x": [s + BADGE[0], e + BADGE[0]]})
    return out


def _spans(d, n):
    im = _img(d, n)
    if im is None:
        return []
    a = np.asarray(im.crop((170, TOP[0], 930, TOP[1])).convert("L"), dtype=np.float32)
    on = a.mean(0) > 190
    out, i = [], 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and on[j]:
                j += 1
            if j - i >= 20:
                out.append((i + 170, j + 170))
            i = j
        else:
            i += 1
    return out


def _faces(d, n):
    im = _img(d, n)
    if im is None:
        return []
    return [((s, e),
             np.asarray(im.crop((s + 3, FACE[0], e - 3, FACE[1])).convert("L")
                        .resize((20, 30)), dtype=np.float32) / 255.0)
            for s, e in _spans(d, n)]


def discarded(d, n, tol=0.085):
    """コマ n の手牌のうち、コマ n+1 で消えている牌の位置。＝切った牌。"""
    A, B = _faces(d, n), _faces(d, n + 1)
    if not A or not B:
        return []
    return [pos for pos, fa in A
            if min((np.abs(fa - fb).mean() for _, fb in B), default=9) > tol]


def followed_ai(d, n):
    """切った牌が、AIの最善（金）と一致したか。判定できなければ None。"""
    bs = badges(d, n)
    gold = [b["x"] for b in bs if b["kind"] == "金"]
    blue = [b["x"] for b in bs if b["kind"] == "青"]
    if not gold:
        return None
    gone = discarded(d, n)
    if not gone:
        return None
    def ov(p, q):
        return max(0, min(p[1], q[1]) - max(p[0], q[0])) > 6
    if any(ov(p, q) for p in gone for q in gold):
        return "金"
    if any(ov(p, q) for p in gone for q in blue):
        return "青"
    return "外"
