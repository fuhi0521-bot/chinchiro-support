"""4人の雀士で N 半荘を回し、結果をまとめる。

    python3 mj.py match --hanchan 1000 --seed 1 --workers 4
"""

from __future__ import annotations

import os
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor

from .simulate import Stats, report, run


def _worker(args):
    n, seed = args
    sys.setrecursionlimit(10000)
    return pickle.dumps(run(n, seed=seed))


def match(hanchan: int, seed: int = 1, workers: int = 0):
    workers = workers or min(4, os.cpu_count() or 1)
    if workers <= 1:
        return run(hanchan, seed=seed)
    per = hanchan // workers
    jobs = [(per + (1 if i < hanchan % workers else 0), seed + i * 7919) for i in range(workers)]
    jobs = [j for j in jobs if j[0] > 0]
    total = None
    with ProcessPoolExecutor(max_workers=len(jobs)) as ex:
        for blob in ex.map(_worker, jobs):
            part = pickle.loads(blob)
            if total is None:
                total = {k: Stats() for k in part}
            for name, st in part.items():
                total[name].merge(st)
    return total


__all__ = ["match", "report"]
