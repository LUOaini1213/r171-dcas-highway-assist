"""Run every suite with the BASELINE DCAS parameters and write results/*.csv, results/checks.csv, summary.json.

Suites: cut-in (official points + grid), cut-out, decelerating lead, curves, driver-engagement timelines,
functional cases, non-threatening lateral approaches (false-braking baseline).  Plus: Python-backend cross-check,
time-step sensitivity (20 ms vs 10 ms) and noise robustness of the official points (10 seeds, R171 Annex 3 App. 4).

Run:  python -X utf8 -I scripts/run_all.py --esmini-lib <...>/esminiLib.dll --workers 2
      (without esmini: --backend python)
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dcas import verify  # noqa: E402
from dcas.evaluate import false_brake, is_safe, lateral_verdict, longitudinal_verdict  # noqa: E402
from dcas.params import BASELINE, FIXES, parameter_rows  # noqa: E402

OV, SUFFIX = None, ""   # config overrides and file suffix (--config)
from dcas.runner import RES, allowed_workers, row, run_many, sha256, write_csv, write_series  # noqa: E402
from dcas.scenarios import (curve_cases, cutin_grid_cases, cutin_official_cases, cutout_cases, engagement_cases,  # noqa: E402
                            functional_cases, latprobe_cases, leadbrake_cases)


def verdict_of(case, r):
    if case.family.startswith("Curve") or case.family == "SBend":
        return lateral_verdict(r)
    if case.family == "Highway":
        return "-"
    return longitudinal_verdict(r)


def run_suite(name, cases, kind, lib, workers, record_ids=(), log_ids=()):
    jobs = [(c, OV, c.case_id in record_ids, (f"{kind}_{c.case_id}{SUFFIX}" if c.case_id in log_ids else None), 0) for c in cases]
    t0 = time.time()
    rs = run_many(jobs, kind, lib, workers)
    trip = []
    rows = []
    for c, r in zip(cases, rs):
        v = verdict_of(c, r)
        extra = {}
        if c.family == "LatProbe":
            extra["false_brake"] = false_brake(r)
        rows.append(row(r, c, v, **extra))
        trip.append((c, r, v))
        if r.series is not None:
            write_series(r, RES / "timeseries" / f"{c.case_id}{SUFFIX}.csv")
    write_csv(rows, RES / f"{name}{SUFFIX}.csv")
    n_safe = sum(1 for _c, _r, v in trip if is_safe(v) or v in ("BOUNDARY_HANDLED", "-"))
    print(f"{name:16s} {len(cases):4d} runs  {time.time() - t0:6.1f} s  ok/safe {n_safe}", flush=True)
    return trip


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--esmini-lib")
    ap.add_argument("--backend", default="esmini", choices=["esmini", "python"])
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--config", default="baseline", choices=["baseline", "proposed"])
    a = ap.parse_args()
    global OV, SUFFIX
    if a.config == "proposed":
        sel = json.loads((RES / "tradeoff_selected.json").read_text(encoding="utf-8"))
        OV, SUFFIX = {**FIXES, "t_pred_s": sel["t_pred_s"]}, "_proposed"
    workers = allowed_workers(a.workers)
    kind, lib = a.backend, a.esmini_lib
    RES.mkdir(exist_ok=True)
    t_start = time.time()
    crit_hash = sha256(ROOT / "dcas" / "evaluate.py")
    results = {}
    off_ci = cutin_official_cases()
    results["cutin_official"] = run_suite("cutin_official", off_ci, kind, lib, workers,
                                          record_ids={c.case_id for c in off_ci}, log_ids={"OFF-CI-R171-T2"})
    results["cutin_grid"] = run_suite("cutin_grid", cutin_grid_cases(), kind, lib, workers)
    write_csv([{"case_id": c.case_id, "ttc": c.meta["ttc"], "vlat": c.meta["vlat"], "dv_kph": c.meta["dv_kph"],
                "g_start_m": round(c.meta["g_start"], 3)} for c in cutin_grid_cases(True) if not c.meta["valid"]],
              RES / f"cutin_invalid{SUFFIX}.csv")
    co = cutout_cases()
    results["cutout"] = run_suite("cutout", co, kind, lib, workers, record_ids={c.case_id for c in co if c.meta.get("official")},
                                  log_ids={"OFF-CO-R171"})
    lb = leadbrake_cases()
    results["leadbrake"] = run_suite("leadbrake", lb, kind, lib, workers, record_ids={c.case_id for c in lb if c.meta.get("official")})
    cv = curve_cases()
    results["curve"] = run_suite("curve", cv, kind, lib, workers,
                                 record_ids={c.case_id for c in cv if c.meta.get("official") or c.case_id in
                                             ("CV-R374-v120-csa", "CV-R374-v120-nocsa", "CV-Sbend-v130-nocsa")})
    eg = engagement_cases()
    results["engagement"] = run_suite("engagement", eg, kind, lib, workers, record_ids={c.case_id for c in eg})
    fn = functional_cases()
    results["functional"] = run_suite("functional", fn, kind, lib, workers, record_ids={c.case_id for c in fn})
    lp = latprobe_cases()
    results["latprobe"] = run_suite("latprobe", lp, kind, lib, workers)
    n_fb = sum(1 for _c, r, _v in results["latprobe"] if false_brake(r))
    print(f"latprobe false braking: {n_fb}/{len(lp)}")

    # ------------------------------------------------------------ cross-checks
    rng = random.Random(1)
    grid = cutin_grid_cases()
    sample = off_ci + rng.sample(grid, 40) + co[:5] + lb[:2] + [c for c in cv if c.meta.get("official")] + eg + fn
    xrows = []
    if kind == "esmini":
        py = run_many([(c, OV, False, None, 0) for c in sample], "python", None, workers)
        ref = {r.case_id: r for trip in results.values() for _c, r, _v in trip}
        for c, rp in zip(sample, py):
            re = ref[c.case_id]
            xrows.append({"case_id": c.case_id, "same_states": re.states == rp.states,
                          "same_collision": re.collision == rp.collision,
                          "esmini_collision_flag_agrees": (re.backend_collision == re.collision),
                          "d_min_ttc_s": round(abs((re.min_ttc_s if re.min_ttc_s != float("inf") else 99) -
                                                   (rp.min_ttc_s if rp.min_ttc_s != float("inf") else 99)), 4),
                          "d_min_gap_m": round(abs((re.min_gap_m if re.min_gap_m != float("inf") else 9999) -
                                                   (rp.min_gap_m if rp.min_gap_m != float("inf") else 9999)), 4),
                          "d_peak_decel": round(abs(re.peak_decel - rp.peak_decel), 4),
                          "d_v_min_kph": round(abs(re.v_min_kph - rp.v_min_kph), 4),
                          "same_verdict": verdict_of(c, re) == verdict_of(c, rp)})
        write_csv(xrows, RES / f"backend_crosscheck{SUFFIX}.csv")
    # time step: 20 ms vs 10 ms on the official longitudinal points
    offs = off_ci + [c for c in co if c.meta.get("official")] + [c for c in lb if c.meta.get("official")]
    r10 = run_many([(c, {**(OV or {}), "dt": 0.01}, False, None, 0) for c in offs], kind, lib, workers)
    ref = {r.case_id: r for trip in results.values() for _c, r, _v in trip}
    drows = []
    for c, r in zip(offs, r10):
        r20 = ref[c.case_id]
        drows.append({"case_id": c.case_id, "verdict_20ms": verdict_of(c, r20), "verdict_10ms": verdict_of(c, r),
                      "min_ttc_20ms": round(r20.min_ttc_s, 3) if r20.min_ttc_s != float("inf") else "",
                      "min_ttc_10ms": round(r.min_ttc_s, 3) if r.min_ttc_s != float("inf") else "",
                      "v_impact_20ms": round(r20.v_rel_impact_kph, 2), "v_impact_10ms": round(r.v_rel_impact_kph, 2),
                      "peak_decel_20ms": round(r20.peak_decel, 3), "peak_decel_10ms": round(r.peak_decel, 3)})
    write_csv(drows, RES / f"dt_sensitivity{SUFFIX}.csv")
    # noise robustness of the official points (10 seeds)
    rob_cases = offs + [c for c in cv if c.meta.get("official")]
    seeds = list(range(1, 11))
    rr = run_many([(c, OV, False, None, s) for c in rob_cases for s in seeds], kind, lib, workers)
    rob = {}
    rrows = []
    for i, c in enumerate(rob_cases):
        vs = [verdict_of(c, r) for r in rr[i * len(seeds):(i + 1) * len(seeds)]]
        rob[c.case_id] = vs
        rs = rr[i * len(seeds):(i + 1) * len(seeds)]
        rrows.append({"case_id": c.case_id, "label": c.meta.get("label", ""), "n": len(vs),
                      "n_safe_or_handled": sum(1 for v in vs if is_safe(v) or v in ("BOUNDARY_HANDLED",)),
                      "verdicts": " ".join(vs),
                      "min_ttc_min": round(min(r.min_ttc_s for r in rs), 3) if min(r.min_ttc_s for r in rs) != float("inf") else "",
                      "v_impact_max": round(max(r.v_rel_impact_kph for r in rs), 2)})
    write_csv(rrows, RES / f"robustness{SUFFIX}.csv")

    # ------------------------------------------------------------ requirement checks
    by_id = {r.case_id: r for name in ("engagement", "functional") for _c, r, _v in results[name]}
    checks = verify.engagement_checks(by_id)
    checks += verify.suite_checks({k: v for k, v in results.items() if k in ("cutin_official", "cutin_grid", "cutout",
                                                                             "leadbrake", "curve", "engagement", "functional")})
    checks += verify.robustness_checks({k: [v if v != "BOUNDARY_HANDLED" else "PASS" for v in vs] for k, vs in rob.items()})
    write_csv(checks, RES / f"checks{SUFFIX}.csv")
    from dataclasses import replace
    write_csv(parameter_rows(replace(BASELINE, **(OV or {}))), RES / f"parameters{SUFFIX}.csv")
    n_runs = sum(len(v) for v in results.values()) + len(xrows) + len(drows) + len(rr)
    summary = {"config": a.config, "overrides": OV or {}, "backend": kind, "workers": workers, "evaluate_py_sha256": crit_hash,
               "runs_total": n_runs, "wall_time_s": round(time.time() - t_start, 1),
               "suites": {k: len(v) for k, v in results.items()},
               "latprobe_false_brake": n_fb,
               "checks": {"total": len(checks), "pass": sum(1 for c in checks if c["verdict"] == "通过"),
                          "fail": sum(1 for c in checks if c["verdict"] == "不通过"),
                          "info": sum(1 for c in checks if c["verdict"] == "信息")}}
    if xrows:
        summary["crosscheck"] = {"n": len(xrows), "same_states": sum(x["same_states"] for x in xrows),
                                 "same_verdict": sum(x["same_verdict"] for x in xrows),
                                 "max_d_min_gap_m": max(x["d_min_gap_m"] for x in xrows if x["d_min_gap_m"] < 1000),
                                 "max_d_peak_decel": max(x["d_peak_decel"] for x in xrows),
                                 "esmini_collision_flag_agrees": sum(x["esmini_collision_flag_agrees"] for x in xrows)}
    (RES / f"summary{SUFFIX}.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
