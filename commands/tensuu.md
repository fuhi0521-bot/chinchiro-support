---
description: 点数計算。手牌と和了牌から役・符・点数を出す
argument-hint: "234m567m234p678p11s --win 2m --tsumo --riichi --dora 1"
allowed-tools: Bash, Read
---

点数を計算する。

入力: $ARGUMENTS

`skills/mahjong/scripts/mj.py score` に渡す。符の内訳が要るときは `--fu-detail` を付ける。

```
python3 skills/mahjong/scripts/mj.py score <手牌14枚> --win <和了牌> [--tsumo] [--riichi]
    [--seat 南] [--round 東] [--dora N] [--uradora N] [--melds chi=234p] [--fu-detail]
```

- 手牌は **和了牌を含めた14枚**（副露があれば副露を除いた枚数 + `--melds`）
- 赤ドラは手牌表記に `0m/0p/0s` と書けば自動で数える
- `--seat 東` が親。省略時は子（南家）扱い

結果はエンジンの出力をそのまま示し、**符がどこから来たか**を1〜2行で補足する。
翻数や点数を自分で計算し直さない。
