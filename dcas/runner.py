"""Run lists of cases, optionally in parallel worker processes (one esmini instance per process, as in P5)."""
from __future__ import annotations

import csv
import hashlib
import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

from .backends import make_backend
from .closed_loop import RunResult, flat, run_case
from .params import BASELINE

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
_BACKEND = None


def _init_worker(kind, lib):
    global _BACKEND
    _BACKEND = make_backend(kind, lib)


def _run_one(job) -> RunResult:
    case, overrides, record, log_stem, seed = job
    cfg = replace(BASELINE, **overrides) if overrides else BASELINE
    return run_case(case, _BACKEND, cfg, record=record, log_stem=log_stem, seed=seed)


def run_many(jobs: list[tuple], kind: str, esmini_lib: str | None, workers: int = 1) -> list[RunResult]:
    """jobs: (Case, cfg overrides dict, record, log_stem, seed)."""
    if workers <= 1 or len(jobs) < 4:
        _init_worker(kind, esmini_lib)
        return [_run_one(j) for j in jobs]
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker, initargs=(kind, esmini_lib)) as ex:
        return list(ex.map(_run_one, jobs, chunksize=4))


def allowed_workers(requested: int) -> int:
    """House rule of this machine: at most 2 workers before 18:30 UTC on 2026-10-27 (a long simulation sweep is
    running), at most 6 afterwards."""
    now = time.gmtime()
    limit = 2 if (now.tm_year, now.tm_mon, now.tm_mday) == (2026, 10, 27) and (now.tm_hour, now.tm_min) < (18, 30) else 6
    return max(1, min(requested, limit))


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_series(r: RunResult, path: Path) -> None:
    if not r.series:
        return
    keys = list(r.series)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(keys)
        for row in zip(*(r.series[k] for k in keys)):
            w.writerow([f"{v:.4f}" if isinstance(v, float) else v for v in row])


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row(r: RunResult, case, verdict: str, **extra) -> dict:
    d = flat(r)
    out = {"case_id": r.case_id, "family": r.family, "backend": r.backend, "verdict": verdict}
    out.update({k: v for k, v in case.meta.items() if k not in ("script",) and not isinstance(v, (dict, list))})
    out.update(extra)
    for k in ("collision", "collided_with", "v_rel_impact_kph", "backend_collision", "min_ttc_s", "min_gap_m",
              "peak_decel", "peak_decel_500ms", "peak_decel_cmd", "peak_jerk", "max_abs_d", "lane_departure",
              "t_lane_departure", "t_d05", "peak_ay", "ay_over_sustained_max_s", "peak_jy_500ms", "v0_kph",
              "v_min_kph", "v_end_kph", "t_confirmed", "t_selected", "t_brake", "a_kin_at_selection", "brake_on_object", "selected_objects",
              "states", "transitions", "events", "refusals", "lockout", "t_standstill", "end_reason", "t_end"):
        v = d.get(k)
        out[k] = round(v, 4) if isinstance(v, float) else v
    return out


_ = os
