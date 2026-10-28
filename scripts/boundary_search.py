"""Cut-in failure boundary: grid, then bisection on TTC for every (relative speed, lateral speed) pair.

Pass / fail per run = dcas/evaluate.py (fixed before running): safe = PASS or PASS_HARSH, unsafe = collision,
min TTC < 1.0 s, 500 ms deceleration > 5.5 m/s2 or lateral offset > 0.5 m.
Method (fixed before running):
  1. read the grid verdicts (results/cutin_grid.csv for --config baseline, otherwise run the grid first);
  2. for each (dv, vlat): u = highest grid TTC that is unsafe, s = next higher grid TTC that is safe;
     bisect [u, s] N_ITER = 4 times (0.5 s grid -> 0.03 s);
  3. TTC* = the safe end after bisection.  All safe -> TTC* < lowest grid value; all unsafe -> TTC* > highest.
     A safe grid TTC below an unsafe one is recorded as non-monotonic (the top transition is refined).
Outputs: results/cutin_boundary_<config>.csv, results/cutin_refine_<config>.csv and the refinement points as an
OpenSCENARIO grid scenarios/cutin_refine_<config>_grid.xosc (traceability).

Run:  python -X utf8 -I scripts/boundary_search.py --esmini-lib <...> --config baseline --workers 2
"""
import argparse
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dcas.evaluate import is_safe, longitudinal_verdict  # noqa: E402
from dcas.params import BASELINE, FIXES  # noqa: E402
from dcas.runner import RES, allowed_workers, read_csv, row, run_many, write_csv  # noqa: E402
from dcas.scenarios import CUTIN_DV_KPH, CUTIN_TTC_S, CUTIN_VLAT_MPS, cutin_case, cutin_grid_cases, write_grid  # noqa: E402

N_ITER = 4


def config_overrides(name: str) -> dict:
    if name == "baseline":
        return {}
    if name.startswith("proposed"):
        import json
        sel = json.loads((RES / "tradeoff_selected.json").read_text(encoding="utf-8"))
        return {**FIXES, "t_pred_s": sel["t_pred_s"]}
    raise SystemExit(f"unknown config {name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--esmini-lib")
    ap.add_argument("--backend", default="esmini", choices=["esmini", "python"])
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--config", default="baseline")
    a = ap.parse_args()
    workers = allowed_workers(a.workers)
    ov = config_overrides(a.config)
    grid = cutin_grid_cases()
    if a.config == "baseline" and (RES / "cutin_grid.csv").exists():
        verdict = {r["case_id"]: r["verdict"] for r in read_csv(RES / "cutin_grid.csv")}
    else:
        rs = run_many([(c, ov, False, None, 0) for c in grid], a.backend, a.esmini_lib, workers)
        verdict = {c.case_id: longitudinal_verdict(r) for c, r in zip(grid, rs)}
        write_csv([row(r, c, verdict[c.case_id]) for c, r in zip(grid, rs)], RES / f"cutin_grid_{a.config}.csv")
    by_pair = {}
    for c in grid:
        by_pair.setdefault((c.meta["dv_kph"], c.meta["vlat"]), []).append((c.meta["ttc"], verdict[c.case_id]))
    # ---------------------------------------------------------------- bisection, all pairs advanced together
    state = {}
    for pair, pts in by_pair.items():
        pts.sort()
        unsafe = [t for t, v in pts if not is_safe(v)]
        safe = [t for t, v in pts if is_safe(v)]
        nonmono = bool(unsafe and safe and min(safe) < max(unsafe))
        if not unsafe:
            state[pair] = dict(lo=None, hi=min(safe), mode="all_safe", nonmono=False, lo_verdict="")
        elif not any(t > max(unsafe) for t in safe):
            state[pair] = dict(lo=max(unsafe), hi=None, mode="all_unsafe_above", nonmono=nonmono,
                               lo_verdict=dict(pts)[max(unsafe)])
        else:
            u = max(unsafe)
            s = min(t for t in safe if t > u)
            state[pair] = dict(lo=u, hi=s, mode="bisect", nonmono=nonmono, lo_verdict=dict(pts)[u])
    refine_rows, refine_cases = [], []
    for it in range(N_ITER):
        jobs, keys = [], []
        for pair, st in state.items():
            if st["mode"] != "bisect":
                continue
            mid = round(0.5 * (st["lo"] + st["hi"]), 4)
            c = cutin_case(mid, pair[1], pair[0], prefix=f"CIR-{a.config}")
            if not c.meta["valid"]:
                st["mode"] = "invalid_mid"
                continue
            jobs.append((c, ov, False, None, 0))
            keys.append(pair)
        if not jobs:
            break
        rs = run_many(jobs, a.backend, a.esmini_lib, workers)
        for (c, *_), pair, r in zip(jobs, keys, rs):
            v = longitudinal_verdict(r)
            st = state[pair]
            if is_safe(v):
                st["hi"] = c.meta["ttc"]
            else:
                st["lo"], st["lo_verdict"] = c.meta["ttc"], v
            refine_rows.append(row(r, c, v, iteration=it + 1, config=a.config))
            refine_cases.append(c)
        print(f"iteration {it + 1}: {len(jobs)} runs", flush=True)
    write_csv(refine_rows, RES / f"cutin_refine_{a.config}.csv")
    if refine_cases:
        write_grid(f"cutin_refine_{a.config}_grid.xosc", "CutIn", refine_cases, f"bisection points, config {a.config}")
    out = []
    for (dv, vl), st in sorted(state.items()):
        out.append({"config": a.config, "dv_kph": dv, "vlat_mps": vl, "mode": st["mode"],
                    "ttc_unsafe": "" if st["lo"] is None else st["lo"], "ttc_safe": "" if st["hi"] is None else st["hi"],
                    "ttc_star": "" if st["hi"] is None else st["hi"], "unsafe_verdict": st["lo_verdict"],
                    "non_monotonic": st["nonmono"]})
    write_csv(out, RES / f"cutin_boundary_{a.config}.csv")
    n_bis = sum(1 for o in out if o["mode"] == "bisect")
    print(f"{len(out)} pairs, {n_bis} bisected, refine runs {len(refine_rows)}, non-monotonic {sum(o['non_monotonic'] for o in out)}")
    _ = (BASELINE, replace, CUTIN_DV_KPH, CUTIN_TTC_S, CUTIN_VLAT_MPS)


if __name__ == "__main__":
    main()
