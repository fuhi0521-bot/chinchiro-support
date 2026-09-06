# 麻雀AIエージェント

麻雀（日本リーチ麻雀）専用の Claude エージェント。
**知識**（役・符・戦術）と**計算エンジン**（シャンテン・受け入れ・点数・危険度）を
1つのプラグインにまとめてある。

前提の卓は **雀魂・四人半荘・赤あり・玉の間**（ラス回避優先）。
リアル雀荘にも同じ基準で答えるが、トップ賞のある場では判断軸が変わるので先に確認する。

## できること

| 相談 | 答えるもの |
|---|---|
| 何切る | 受け入れ枚数つきの結論。テンパイならリーチ/ダマまで |
| 押す？降りる？ | 基準表のどの行に当たるかを明示した1行結論 |
| 鳴く？ | 鳴いた後の手がどうなるかで判断 |
| この手いくら？ | 役・符の内訳・点数（高点法で最高の解釈） |
| テンパイしてる？ | 副露数×巡目からの見立てと危険牌の序列 |
| オーラスの条件は？ | ロン／ツモ／直撃に分けた必要打点 |
| 今日の対局を振り返って | 悪手を3分類して「今日の1点」 |
| 〜って何？ | 役・用語・ルールの照会 |

## 導入

### プラグインとして入れる（推奨）

```
/plugin marketplace add fuhi0521-bot/chinchiro-support
/plugin install mahjong@fuhi0521-mahjong
```

`/nanikiru` `/oshihiki` `/tensuu` `/kikendo` `/furikaeri` のスラッシュコマンドと、
`mahjong-coach` `mahjong-reviewer` のサブエージェントが使えるようになる。

### スキルだけ手元に置く

```bash
git clone https://github.com/fuhi0521-bot/chinchiro-support.git
cp -r chinchiro-support/skills/mahjong ~/.claude/skills/
```

## 計算エンジンを直接使う

Python 3 だけで動く（依存パッケージなし）。

```bash
S=skills/mahjong/scripts/mj.py

python3 $S shanten 3456778m234p55s99s          # シャンテン数（一般形/七対子/国士）
python3 $S wait    34567m123p456p11s           # 待ち牌と残り枚数
python3 $S discard 3456778m234p55s99s --top 5  # 何切る（受け入れ順）
python3 $S score   234m567m234p678p11s --win 2m --tsumo --riichi --fu-detail
python3 $S danger  --river "123m9p東南白" --tiles "456789m5p3s発"
python3 $S points  --han 3 --fu 40
python3 $S noten   --tenpai 2
python3 $S match   --hanchan 1000 -j 4         # 4人のAI雀士で対戦させる
```

牌の表記は `1m〜9m`（萬子）`1p〜9p`（筒子）`1s〜9s`（索子）`東南西北白發中`。
赤ドラは `0m/0p/0s`。字牌は `1z〜7z` でも書ける。
副露は `--melds chi=234p,pon=白,ankan=5s`。

### 実装しているもの

- **シャンテン**: 一般形（5ブロック制約つき全探索）・七対子・国士
- **受け入れ / 待ち**: 残り枚数つき。場に見えている牌を `--visible` で反映できる
- **役**: 1翻〜役満まで全役。食い下がり・複合の可否・**高点法**（最も高い解釈を採用）
- **符**: 20符固定（平和ツモ）・25符（七対子）・鳴き平和形30符・切り上げまで
- **点数**: 満貫〜役満、本場、供託、親子×ロンツモ、ノーテン罰符
- **危険度**: 現物 / スジ / 片スジ / 両スジ / ノーチャンス / ワンチャンス / 無筋、字牌の切れ枚数

### テスト

```bash
python3 tests/test_engine.py
```

点数表は標準の値と全件照合済み。シャンテン計算はランダム4000ハンドで
和了形判定との整合性を検証してある。

## 4人のAI雀士で対戦させる

性格の違う4人（`agents/README.md`）を戦わせて、方針の差が順位に出るかを見られる。

```bash
python3 skills/mahjong/scripts/mj.py match --hanchan 1000 -j 4
```

1000半荘の結果は `results/match-1000.txt`。

## 中身

```
skills/mahjong/
  SKILL.md                    入口。相談の型を見分けて必要な参照だけ読む
  references/
    rules.md                  ルール・進行・流局・フリテン・雀魂とリアルの差
    yaku.md                   役の全一覧・食い下がり・複合の可否
    scoring.md                符計算・点数表・本場・供託
    efficiency.md             牌効率・5ブロック・ターツ序列・見落としやすい形
    push-fold.md              押し引きの基準表・回し打ち・ベタオリ
    reading.md                河読み・副露読み・ダマテン察知・危険度
    wait-selection.md         待ち取り・山読み・残り枚数の数え方
    probability.md            配牌分布・有効牌を引ける確率・実戦の統計値
    edge-cases.md             フリテン・槓・流局・ダブロン・包など迷いやすい細部
    calls.md                  鳴き判断・カン・喰い替え・後付け
    riichi.md                 リーチ/ダマ/追っかけ・宣言牌の選び方
    placement.md              着順戦術・オーラス条件計算・ラス回避
    majsoul.md                雀魂のルール設定・段位・UI由来の注意点
    glossary.md               用語集
    training.md               上達ロードマップ・牌譜検討・Mortal/NAGA/MAKA
  scripts/
    mj.py                     CLI 入口
    mj/                       計算エンジン（tiles/shanten/efficiency/hand/score/yaku/safety）
agents/                       mahjong-coach / mahjong-reviewer
commands/                     /nanikiru /oshihiki /tensuu /kikendo /furikaeri
tests/test_engine.py          回帰テスト
```

## 数値の扱い

押し引きの基準表と危険度は、天鳳・雀魂で広く使われている統計の**目安**。
ルールや場況で振れるので、**絶対値ではなく序列**として使う。
小数点以下の差を根拠に結論を変えない。

雀魂の順位ポイントと昇段ptは更新で変わるため、正確な値はゲーム内で確認する。
判断に効くのは値そのものではなく「4着だけが大きく沈む」という構造。

## このリポジトリについて

もとはチンチロアプリのサポートページ（`index.html`）だった。
麻雀エージェントに入れ替えたため、サポートページは削除してある。
必要なら `git show main:index.html` で取り出せる。
