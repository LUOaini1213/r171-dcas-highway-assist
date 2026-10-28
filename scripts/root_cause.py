"""Root-cause analysis of representative failures with single-change counterfactuals.

Which failures (rule): every OFFICIAL longitudinal test point (R171 Annex 4 / Euro NCAP VA / Euro NCAP AD) that
is unsafe with the BASELINE parameters; every lane-centring run that left the lane although curve-speed
adaptation was on; and from the cut-in grid the unsafe run with the highest TTC among those whose kinematic
demand at target selection was <= 5 m/s2 (the function had the braking authority but reacted too late;
ties -> higher relative speed).  The cut-in item was added after the first pass, which had found no failing
official cut-in point.  For each: a timeline of key instants from the recorded run, then the
same case re-run with ONE change at a time:
  perfect_perception  no noise, no latency, 1-cycle confirmation (occlusion kept)
  no_actuator_lag     longitudinal dead time 0, time constant 0.05 s
  lead_accel_ff       kinematic demand uses the estimated deceleration of a braking object
  t_pred_2s           lateral prediction horizon 2.0 s (earlier cut-in reaction)
  authority_9         braking authority 9 m/s2 (what an AEB could add; beyond R171 2.16 = not DCAS)
  a_curve_plan_1      curve-speed profile planned with 1.0 m/s2 instead of 1.5 m/s2
The root cause is the smallest change that makes the run safe (or the reason none does within DCAS limits).
Outputs: results/root_cause.csv, results/root_cause_timeline.csv, results/timeseries/RC-*.csv

Run:  python -X utf8 -I scripts/root_cause.py --esmini-lib <...>
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dcas.evaluate import is_safe, lateral_verdict, longitudinal_verdict  # noqa: E402
from dcas.runner import RES, read_csv, run_many, write_csv, write_series  # noqa: E402
from dcas.scenarios import case_index  # noqa: E402

VARIANTS = {
    "baseline": {},
    "perfect_perception": dict(sd_x_m=0.0, sd_y_m=0.0, sd_v_mps=0.0, obj_latency_s=0.0, obj_confirm_n=1),
    "no_actuator_lag": dict(long_dead_time_s=0.0, long_tau_s=0.05),
    "lead_accel_ff": dict(lead_accel_ff=True),
    "t_pred_2s": dict(t_pred_s=2.0),
    "authority_9": dict(a_authority=-9.0),
    "a_curve_plan_1": dict(a_curve_plan=1.0),
}


def verdict_of(c, r):
    return lateral_verdict(r) if (c.family.startswith("Curve") or c.family == "SBend") else longitudinal_verdict(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--esmini-lib")
    ap.add_argument("--backend", default="esmini", choices=["esmini", "python"])
    a = ap.parse_args()
    idx = case_index()
    failing = []
    for suite in ("cutin_official", "cutout", "leadbrake"):
        for r in read_csv(RES / f"{suite}.csv"):
            if r.get("official") == "True" and r["verdict"] not in ("PASS", "PASS_HARSH"):
                failing.append(r["case_id"])
    for r in read_csv(RES / "curve.csv"):
        if r["csa"] == "True" and r["lane_departure"] == "True":
            failing.append(r["case_id"])
    grid = [r for r in read_csv(RES / "cutin_grid.csv") if r["verdict"] not in ("PASS", "PASS_HARSH")
            and r["t_selected"] not in ("", None) and float(r["a_kin_at_selection"] or 99) <= 5.0]
    if grid:
        failing.append(max(grid, key=lambda r: (float(r["ttc"]), float(r["dv_kph"])))["case_id"])
    print("failures:", failing)
    jobs = [(idx[cid], ov, name == "baseline", None, 0) for cid in failing for name, ov in VARIANTS.items()]
    rs = run_many(jobs, a.backend, a.esmini_lib, 1)
    rows, tl = [], []
    for (c, ov, rec, _l, _s), name, r in zip(jobs, [n for _ in failing for n in VARIANTS], rs):
        v = verdict_of(c, r)
        rows.append({"case_id": c.case_id, "label": c.meta.get("label", ""), "variant": name, "verdict": v,
                     "safe": is_safe(v) or v == "PASS", "v_rel_impact_kph": round(r.v_rel_impact_kph, 2),
                     "min_ttc_s": round(r.min_ttc_s, 3) if r.min_ttc_s != float("inf") else "",
                     "peak_decel_500ms": round(r.peak_decel_500ms, 3), "t_selected": r.t_selected,
                     "t_brake": r.t_brake, "lane_departure": r.lane_departure, "v_min_kph": round(r.v_min_kph, 2),
                     "peak_ay": round(r.peak_ay, 3)})
        if name == "baseline":
            write_series(r, RES / "timeseries" / f"RC-{c.case_id}.csv")
            p = c.params
            start = {"CutIn": p.get("LcStart"), "CutOut": p.get("CoStart"), "LeadBrake": p.get("DecelStart")}.get(c.family)
            t_cross = t_intr = None
            if c.family == "CutIn":           # sinusoidal lane change: when the target's near edge reaches the lane line / 0.3 m
                import math
                T, t0 = float(p["LcTime"]), float(p["LcStart"])
                for intr, key in ((0.0, "cross"), (0.30, "intr")):
                    frac = (0.85 + intr) / 3.5     # near edge starts 3.5 - 0.9 - 1.75 = 0.85 m outside the line
                    tt = round(t0 + T * math.acos(1.0 - 2.0 * frac) / math.pi, 3)
                    t_cross, t_intr = (tt, t_intr) if key == "cross" else (t_cross, tt)
            tl.append({"case_id": c.case_id, "manoeuvre_start_s": start, "t_line_cross": t_cross, "t_intrusion_0p3": t_intr,
                       "t_confirmed": " ".join(f"{k}={v}" for k, v in r.t_confirmed.items()),
                       "t_selected": r.t_selected, "t_brake": r.t_brake, "a_kin_at_selection": r.a_kin_at_selection,
                       "t_collision": r.t_collision, "v_rel_impact_kph": round(r.v_rel_impact_kph, 2),
                       "min_ttc_s": round(r.min_ttc_s, 3) if r.min_ttc_s != float("inf") else "",
                       "first_boundary_approaching": r.first("boundary_approaching"),
                       "dca_lateral": r.first("dca_shown:lateral_limit"), "t_lane_departure": r.t_lane_departure,
                       "v_min_kph": round(r.v_min_kph, 2)})
    write_csv(rows, RES / "root_cause.csv")
    write_csv(tl, RES / "root_cause_timeline.csv")
    for cid in failing:
        fixes = [r["variant"] for r in rows if r["case_id"] == cid and r["variant"] != "baseline" and r["safe"]]
        print(f"{cid}: safe with {fixes}")


if __name__ == "__main__":
    main()
