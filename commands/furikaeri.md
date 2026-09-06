---
description: 対局の振り返り。悪手を3分類して、今日直す1点を出す
argument-hint: "[半荘の内容・気になった局面・牌譜URL]"
allowed-tools: Bash, Read
---

対局を振り返る。`skills/mahjong/references/training.md` の手順に従う。

入力: $ARGUMENTS

1. **順位から見ない。** 判断の質だけを見る
2. 局面を **2〜3個だけ** 扱う
3. **A. 牌効率 / B. 押し引き / C. 場況読み** に分類する
4. **今日の1点**を選んで終わる

「あの牌のほうが広かった」と言う前に `skills/mahjong/scripts/mj.py discard` で実際に数える。

情報が足りなくても先に分類と仮の結論を出し、最後に1つだけ確認する。
正しく押しての放銃は「その放銃は正解」とはっきり言う。
