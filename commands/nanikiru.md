---
description: 何切る。手牌を渡すと受け入れ順に切る牌を出し、結論を1行で返す
argument-hint: "3456778m234p55s99s [巡目/ドラ/場況]"
allowed-tools: Bash, Read
---

麻雀の何切る問題に答える。

入力: $ARGUMENTS

1. `skills/mahjong/scripts/mj.py discard <手牌> --top 5` で受け入れを計算する
   （副露があれば `--melds chi=234p` の形で渡す）
2. テンパイする切り方があれば `mj.py wait` で待ちを確認する
3. `skills/mahjong/SKILL.md` の「モード1: 打牌検討」の型で答える

**結論を1行目に置く。** テンパイならリーチ/ダマまで含める。
枚数だけで決めず、打点・危険度・着順を足して結論を出す。
巡目やドラが書かれていなければ、平場・中盤と仮定して答え、最後に1つだけ確認する。
