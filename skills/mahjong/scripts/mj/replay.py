"""雀魂の牌譜動画から、打牌の瞬間だけを抜き出す。

牌譜そのものは読み込めない（雀魂のフォーマットは非公開）。
その代わり **牌譜を再生した画面の動画** から局面を復元する。

    python3 skills/mahjong/scripts/mj/replay.py 牌譜.mp4 --out frames/

やること:
  1. 動画を毎秒 N 枚に分解する
  2. 河の領域を前フレームと比べて、**変化した瞬間＝打牌の瞬間** を検出する
  3. その瞬間のフレームだけを保存し、手牌・各家の河を切り出して並べる

こうすると 3分の牌譜（5000フレーム）が、読むべき 100枚程度に減る。
あとはその画像を読んで局面を組み立て、各打牌を かなめ と突き合わせる。

座標は 2556x1179（スマホ横持ちのスクショ）を基準にした割合で持っているので、
別の解像度でも動く。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

# 画面のどこに何があるか（幅・高さに対する割合）
REGIONS = {
    "hand":      (0.17, 0.84, 0.79, 1.00),   # 自分の手牌
    "river_me":  (0.32, 0.50, 0.58, 0.72),   # 自分の河
    "river_top": (0.40, 0.10, 0.62, 0.34),   # 対面の河
    "river_left":(0.26, 0.20, 0.44, 0.50),   # 上家の河
    "river_right":(0.55, 0.20, 0.73, 0.50),  # 下家の河
    "center":    (0.36, 0.24, 0.48, 0.40),   # 局・巡目・点数
    "dora":      (0.06, 0.02, 0.22, 0.18),   # ドラ表示牌・供託
}
RIVERS = ("river_me", "river_top", "river_left", "river_right")


def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def extract(video: str, out: str, fps: float) -> list[str]:
    os.makedirs(out, exist_ok=True)
    raw = os.path.join(out, "raw")
    os.makedirs(raw, exist_ok=True)
    subprocess.run(
        [ffmpeg_exe(), "-y", "-i", video, "-vf", f"fps={fps}",
         os.path.join(raw, "f%05d.png")],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return sorted(os.path.join(raw, f) for f in os.listdir(raw) if f.endswith(".png"))


def box(im, key):
    x0, y0, x1, y1 = REGIONS[key]
    w, h = im.size
    return (int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))


def diff(a, b) -> float:
    """2枚の差の大きさ。0〜1。"""
    from PIL import ImageChops
    d = ImageChops.difference(a.convert("L"), b.convert("L"))
    hist = d.histogram()
    total = sum(hist)
    if not total:
        return 0.0
    # 差が 25 を超えた画素の割合
    return sum(hist[25:]) / total


def find_events(frames: list[str], threshold: float = 0.012, quiet: float = 0.004):
    """河が変わったフレームを拾う。

    アニメーション中は毎フレーム変化するので、**変化が収まった直後**を取る。
    そうしないと牌が動いている最中のブレた絵を読むことになる。
    """
    from PIL import Image
    picked, prev, moving = [], None, False
    for i, f in enumerate(frames):
        im = Image.open(f)
        crops = {k: im.crop(box(im, k)) for k in RIVERS}
        if prev is not None:
            d = max(diff(prev[k], crops[k]) for k in RIVERS)
            if d > threshold:
                moving = True
            elif moving and d < quiet:
                picked.append(f)      # 動きが止まった＝打牌が置かれた
                moving = False
        prev = crops
    return picked


def save_panels(frames: list[str], out: str) -> None:
    """読むための切り出しを作る。1フレームにつき手牌＋4つの河。"""
    from PIL import Image
    os.makedirs(out, exist_ok=True)
    for n, f in enumerate(frames, 1):
        im = Image.open(f)
        for key in ("hand", *RIVERS, "center"):
            c = im.crop(box(im, key))
            c = c.resize((c.width * 2, c.height * 2), Image.LANCZOS)
            c.save(os.path.join(out, f"{n:03d}_{key}.png"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", default="replay_frames")
    ap.add_argument("--fps", type=float, default=4.0,
                    help="分解するコマ数/秒。打牌を取りこぼすなら上げる")
    ap.add_argument("--threshold", type=float, default=0.012)
    a = ap.parse_args()

    print(f"分解中（{a.fps} コマ/秒）…")
    frames = extract(a.video, a.out, a.fps)
    print(f"  {len(frames)} フレーム")
    print("打牌の瞬間を検出中…")
    picked = find_events(frames, a.threshold)
    print(f"  {len(picked)} 箇所")
    panels = os.path.join(a.out, "panels")
    save_panels(picked, panels)
    print(f"読むための切り出しを {panels} に保存した")
    print("\n次にやること: panels/ の画像を順に読んで局面を組み立て、")
    print("各打牌を かなめ の判断と突き合わせる。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
