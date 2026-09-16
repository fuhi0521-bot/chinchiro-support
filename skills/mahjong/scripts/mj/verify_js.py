"""ブラウザ用（JavaScript）のシャンテン計算を、Python の実装と突き合わせる。

tools/nanikiru.html に載せている計算は、Python のエンジンとは別物。
別実装である以上、**照合しないと静かに間違った数字を出す**。
実際、最初に書いた版は 4000局面のうち 89件でずれていた
（5ブロック揃っていて雀頭が無い形の補正が抜けていた）。
直したら今度は効きすぎて 53件ずれた（対子を雀頭として数えられていなかった）。

  python3 skills/mahjong/scripts/mj/verify_js.py

node が要る。不一致が1件でもあれば失敗として終了する。
"""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mj import fast  # noqa: E402

HTML = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "tools", "nanikiru.html")


def extract_js() -> str:
    """ページから計算部分だけを抜き出す。DOM に触る部分は要らない。"""
    src = open(HTML, encoding="utf-8").read()
    body = src[src.index("<script>") + 8: src.rindex("</script>")]
    end = body.index("let hasYaku")
    return body[:end] + "\nmodule.exports={shanten,ukeire};\n"


def cases(n: int, seed: int):
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        wall = [t for t in range(34) for _ in range(4)]
        rng.shuffle(wall)
        k = rng.choice([13, 14])
        c = [0] * 34
        for t in wall[:k]:
            c[t] += 1
        s, acc = fast.ukeire(c, 0, [0] * 34) if k == 13 else (fast.shanten(c, 0), [])
        out.append({"c": c, "s": s if k == 13 else fast.shanten(c, 0),
                    "acc": sorted([t, x] for t, x in acc), "k": k})
    return out


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    with tempfile.TemporaryDirectory() as d:
        js = os.path.join(d, "core.js")
        open(js, "w", encoding="utf-8").write(extract_js())
        data = os.path.join(d, "cases.json")
        json.dump(cases(n, 1), open(data, "w"))
        run = f'''
const {{shanten,ukeire}}=require({js!r});
const cs=require({data!r});
let bad=0, first=null;
for(const k of cs){{
  const s=shanten(k.c.slice());
  let ok = s===k.s;
  if(ok && k.k===13){{
    const [,acc]=ukeire(k.c.slice(),null);
    ok = JSON.stringify(acc.sort((x,y)=>x[0]-y[0]))===JSON.stringify(k.acc);
  }}
  if(!ok){{ bad++; if(!first) first=k; }}
}}
console.log(JSON.stringify({{n:cs.length,bad,first}}));
'''
        p = subprocess.run(["node", "-e", run], capture_output=True, text=True)
        if p.returncode:
            print(p.stderr)
            return 2
        r = json.loads(p.stdout)
    print(f"照合 {r['n']} 件 / 不一致 {r['bad']}")
    if r["bad"]:
        print("最初の不一致:", json.dumps(r["first"], ensure_ascii=False)[:300])
        return 1
    print("シャンテン数・受け入れとも Python の実装と一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
