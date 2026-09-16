---
description: 押し引きの即答。相手のリーチ／副露に対して押すか降りるかを基準表で判定する
argument-hint: "自分の手牌と状況（例: 1シャンテン両面2つ、ドラ1、8巡目、親リーチ）"
allowed-tools: Bash, Read
---

押し引きを判定する。

入力: $ARGUMENTS

1. `skills/mahjong/references/push-fold.md` の基準表を参照する
2. 自分の状態（シャンテン数・形の質・打点）を確定させる。
   手牌が渡されていれば `skills/mahjong/scripts/mj.py shanten` と `discard` で裏を取る
3. 補正条件（親リーチ／複数リーチ／終盤／着順）を当てる
4. 切る牌の候補があれば `mj.py danger --river "..." --tiles "..."` で危険度の序列を出す

答えは **「押す」「降りる」「五分」のどれか1行**から始める。
どの行に当てはまったかを明示する（例:「テンパイ・悪形・安手 → 降りる」）。
五分なら五分と言い切る。
