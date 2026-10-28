"""Parameter trade-off: earlier cut-in reaction (longer lateral prediction horizon t_pred_s) versus false
braking on non-threatening lateral approaches.

SELECTION RULE - written into this file BEFORE the run (2026-10-28) and not changed afterwards:
  Candidates   t_pred_s in {0.0, 0.5, 1.0, 1.5, 2.0, 2.5} s; everything else = BASELINE + FIXES
               (dcas/params.py: lead_accel_ff, a_curve_plan from the root-cause analysis).
  Metrics      G  = safe runs in the cut-in grid (346 valid points, dcas/evaluate.py verdicts)
               O  = safe official cut-in points among R171 Type 1/Type 2 and Euro NCAP VA TTC 0.0/1.5 (4)
               FB = false-braking runs on the LatProbe set (48 cases x 3 noise seeds = 144 runs;
                    dcas/evaluate.false_brake: >= 1.0 m/s2 commanded on the probe vehicle or >= 3 km/h speed loss)
  Constraints  C1: FB / 144 <= 10 %   (design target PRJ-02)
               C2: O = 4               (the R171 base cut-in tests and the Euro NCAP VA cut-in tests are safe)
  Objective    maximise G
  Tie-break    smaller FB, then smaller t_pred_s
  Fallback     if no candidate meets C1 and C2: among candidates meeting C2, take the smallest FB (then the larger G),
               and report that the 10 % target is not reachable with this parameter alone.
All candidates, including the rejected ones, are written to results/tradeoff.csv.

Run:  python -X utf8 -I scripts/tradeoff.py --esmini-lib <...> --workers 2
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dcas.evaluate import false_brake, is_safe, longitudinal_verdict  # noqa: E402
from dcas.params import FIXES  # noqa: E402
from dcas.runner import RES, allowed_workers, row, run_many, write_csv  # noqa: E402
from dcas.scenarios import cutin_grid_cases, cutin_official_cases, latprobe_cases  # noqa: E402

CANDIDATES = (0.0, 0.5, 1.0, 1.5, 2.0, 2.5)
FB_MAX_SHARE = 0.10
SEEDS = (0, 1, 2)
OFFICIAL_C2 = ("OFF-CI-R171-T1", "OFF-CI-R171-T2", "OFF-CI-NCAPVA-1", "OFF-CI-NCAPVA-2")


def select(rows: list[dict]) -> tuple[dict, str]:
    ok = [r for r in rows if r["C1_fb_ok"] and r["C2_official_ok"]]
    if ok:
        best = max(ok, key=lambda r: (r["G_grid_safe"], -r["FB_false_brake"], -r["t_pred_s"]))
        return best, "rule"
    c2 = [r for r in rows if r["C2_official_ok"]]
    if not c2:
        raise SystemExit("no candidate satisfies C2")
    best = min(c2, key=lambda r: (r["FB_false_brake"], -r["G_grid_safe"], r["t_pred_s"]))
    return best, "fallback"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--esmini-lib")
    ap.add_argument("--backend", default="esmini", choices=["esmini", "python"])
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    workers = allowed_workers(a.workers)
    grid, off, lp = cutin_grid_cases(), cutin_official_cases(), latprobe_cases()
    rows, detail = [], []
    t0 = time.time()
    for tp in CANDIDATES:
        ov = {**FIXES, "t_pred_s": tp}
        jobs = [(c, ov, False, None, 0) for c in grid + off] + [(c, ov, False, None, s) for s in SEEDS for c in lp]
        rs = run_many(jobs, a.backend, a.esmini_lib, workers)
        n_g = len(grid)
        rg, ro, rl = rs[:n_g], rs[n_g:n_g + len(off)], rs[n_g + len(off):]
        vg = [longitudinal_verdict(r) for r in rg]
        vo = {c.case_id: longitudinal_verdict(r) for c, r in zip(off, ro)}
        fb = [false_brake(r) for r in rl]
        rec = {"t_pred_s": tp,
               "G_grid_safe": sum(is_safe(v) for v in vg), "G_grid_pass_comfort": sum(v == "PASS" for v in vg),
               "G_grid_collision": sum(v == "FAIL_COLLISION" for v in vg), "grid_n": n_g,
               "O_official_safe": sum(is_safe(vo[k]) for k in OFFICIAL_C2),
               "official_verdicts": " ".join(f"{k}:{v}" for k, v in vo.items()),
               "FB_false_brake": sum(fb), "FB_n": len(fb), "FB_share": round(sum(fb) / len(fb), 4),
               "probe_selected": sum(1 for r in rl if "Adj" in r.selected_objects)}
        rec["C1_fb_ok"] = rec["FB_share"] <= FB_MAX_SHARE
        rec["C2_official_ok"] = rec["O_official_safe"] == len(OFFICIAL_C2)
        rows.append(rec)
        for c, r, v in zip(grid, rg, vg):
            detail.append(row(r, c, v, t_pred_s=tp))
        for i, (c, r) in enumerate(zip(lp * len(SEEDS), rl)):
            detail.append(row(r, c, "FALSE_BRAKE" if fb[i] else "NO_FALSE_BRAKE", t_pred_s=tp, seed=SEEDS[i // len(lp)]))
        print(f"{time.time() - t0:6.0f}s t_pred={tp:.1f}: G={rec['G_grid_safe']}/{n_g} O={rec['O_official_safe']}/4 "
              f"FB={rec['FB_false_brake']}/{len(fb)}", flush=True)
    best, how = select(rows)
    for r in rows:
        r["selected"] = r is best
        r["status"] = "选中" if r is best else ("满足约束、目标较低" if (r["C1_fb_ok"] and r["C2_official_ok"]) else
                                                "不满足 C1" if not r["C1_fb_ok"] and r["C2_official_ok"] else
                                                "不满足 C2" if r["C1_fb_ok"] else "不满足 C1、C2")
    write_csv(rows, RES / "tradeoff.csv")
    write_csv(detail, RES / "tradeoff_runs.csv")
    (RES / "tradeoff_selected.json").write_text(json.dumps({"t_pred_s": best["t_pred_s"], "how": how,
                                                            "fixes": FIXES}, indent=2), encoding="utf-8")
    print("selected:", best["t_pred_s"], how)


if __name__ == "__main__":
    main()
