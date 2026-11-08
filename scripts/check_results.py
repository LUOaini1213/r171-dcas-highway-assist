"""Pin the headline numbers to the committed result files, and compare a fresh Python-backend run with them.

Static check (default, no simulation, about 1 s):
    python -X utf8 -I scripts/check_results.py
  Recomputes every number shown in the README results table, the main findings and the English summary from
  results/*.csv, results/summary*.json, requirements.csv, traceability.csv and scenarios/, checks that the
  summary files agree with the CSVs, and that README.md contains each number in the expected wording.

Fresh-run comparison (after re-running the suites with the pure-Python backend):
    cp -r results <committed>                     # copy of the committed results, taken first
    python -X utf8 -I scripts/run_all.py --backend python --workers 2
    python -X utf8 -I scripts/run_all.py --backend python --workers 2 --config proposed
    python -X utf8 -I scripts/check_results.py --compare <committed>
  Every per-case verdict of the 8 primary suites (baseline and proposed) must equal the committed esmini verdict,
  latprobe false braking must be 19/48 and 0/48, and the requirement checks may differ from the committed ones
  only in the documented row (KNOWN_BACKEND_DIFF below): baseline 126/4/12 under esmini becomes 127/3/12.

Exit code 1 on any mismatch; each mismatch is printed.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
sys.path.insert(0, str(ROOT))

from dcas.evaluate import is_safe  # noqa: E402

PRIMARY = ("cutin_official", "cutin_grid", "cutout", "leadbrake", "curve", "engagement", "functional", "latprobe")
# The one requirement-check row that differs between the backends (documented in README and report section 12):
# a noise-seed robustness row of the Euro NCAP AD slow cut-in that sits on the 90 % threshold.
KNOWN_BACKEND_DIFF = {("", "R171-VAL-01", "OFF-CI-NCAPAD-1")}

ERR = []


def load(name, base=RES):
    with open(base / f"{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def jload(name, base=RES):
    return json.loads((base / name).read_text(encoding="utf-8"))


def expect(what, got, want):
    if got != want:
        ERR.append(f"{what}: got {got!r}, expected {want!r}")


def safe_counts(rows):
    return sum(is_safe(r["verdict"]) for r in rows), sum(r["verdict"] == "FAIL_COLLISION" for r in rows), len(rows)


def check_counts(s):
    out = {}
    for name in PRIMARY:
        out[name] = load(name + s)
    summ = jload(f"summary{s}.json")
    for name in PRIMARY:
        expect(f"summary{s}.json suites.{name}", summ["suites"][name], len(out[name]))
    fb = sum(r["false_brake"] == "True" for r in out["latprobe"])
    expect(f"summary{s}.json latprobe_false_brake", summ["latprobe_false_brake"], fb)
    checks = load("checks" + s)
    c = {"total": len(checks), "pass": sum(r["verdict"] == "通过" for r in checks),
         "fail": sum(r["verdict"] == "不通过" for r in checks), "info": sum(r["verdict"] == "信息" for r in checks)}
    expect(f"summary{s}.json checks", summ["checks"], c)
    return out, summ, fb, c


def static_check():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    tables = (RES / "tables.md").read_text(encoding="utf-8")
    b, sb, fb_b, cb = check_counts("")
    p, sp, fb_p, cp = check_counts("_proposed")
    need = []   # (what, substring that must be in README.md)

    # evaluate.py hash recorded by both batch runs
    h = hashlib.sha256((ROOT / "dcas" / "evaluate.py").read_bytes()).hexdigest()
    expect("summary.json evaluate_py_sha256", sb["evaluate_py_sha256"], h)
    expect("summary_proposed.json evaluate_py_sha256", sp["evaluate_py_sha256"], h)
    need.append(("evaluate.py hash prefix", h[:12]))

    # cut-in grid, lead braking, cut-out, latprobe
    gs, gc, gn = safe_counts(b["cutin_grid"])
    ps, pc, pn = safe_counts(p["cutin_grid"])
    need += [("grid size", f"{gn} 个有效点"), ("grid baseline", f"| {gs} 安全，{gc} 碰撞 |"),
             ("grid proposed", f"| {ps} 安全，{pc} 碰撞 |")]
    expect("grid size baseline = proposed", pn, gn)
    ls_b, _, ln = safe_counts(b["leadbrake"])
    ls_p, _, _ = safe_counts(p["leadbrake"])
    need += [("leadbrake", f"前车急减速网格（{ln} 次） | {ls_b} 次安全 | {ls_p} 次安全 |"),
             ("leadbrake finding", f"安全次数从 {ls_b} 增到 {ls_p}")]
    cs_b, _, cn = safe_counts(b["cutout"])
    cs_p, _, _ = safe_counts(p["cutout"])
    need.append(("cutout", f"切出露出静止车（{cn} 次） | {cs_b} 次安全 | {cs_p} 次安全 |"))
    ln_ = len(b["latprobe"])
    need.append(("latprobe", f"非威胁横向接近（{ln_} 例，种子 0）误制动 | {fb_b} 次 | {fb_p} 次 |"))

    # curves
    cv = b["curve"]
    ay = max(float(r["peak_ay"]) for r in cv)
    jy = max(float(r["peak_jy_500ms"]) for r in cv)
    need.append(("curve peaks", f"弯道 {len(cv)} 次：系统横向加速度峰值 / 0.5 s 横向冲击度峰值 | {ay:.2f} m/s² / {jy:.2f} m/s³"))
    dep_b = sum(r["lane_departure"] == "True" and r["case_id"].endswith("-csa") for r in cv)
    dep_p = sum(r["lane_departure"] == "True" and r["case_id"].endswith("-csa") for r in p["curve"])
    need.append(("curve departures with speed adaptation", f"开弯道限速仍越线 | {dep_b} 次"))
    expect("curve departures with speed adaptation (proposed)", dep_p, 0)

    # driver-engagement timeline (EG-06)
    eg = {(r["req_id"], r["case_id"]): r["measured"] for r in load("checks")}
    eor = eg[("R171-ENG-03", "EG-06-unresponsive")].split()[0]
    esc = eg[("R171-ENG-08", "EG-06-unresponsive")].split()[0]
    dca = eg[("R171-ENG-09", "EG-06-unresponsive")].split()[0]
    rmf = eg[("R171-ENG-10", "EG-06-unresponsive")].split()[0]
    need.append(("engagement timeline",
                 f"驾驶员投入时间线（{len(b['engagement'])} 例） | EOR {eor} s、升级 +{float(esc):.1f} s、"
                 f"DCA +{float(dca):.1f} s、升级后 +{float(rmf):.1f} s 启动风险减缓"))

    # requirement checks
    need += [("checks baseline", f"需求检查（{cb['total']} 条） | {cb['pass']} 通过、{cb['fail']} 不通过、{cb['info']} 信息 |"),
             ("checks proposed", f"| {cp['pass']} 通过、{cp['fail']} 不通过、{cp['info']} 信息 |")]

    # official points
    off = {r["case_id"]: r for name in ("cutin_official", "cutout", "leadbrake") for r in b[name]}
    offp = {r["case_id"]: r for name in ("cutin_official", "cutout", "leadbrake") for r in p[name]}
    groups = {"R171": ["OFF-CI-R171-T1", "OFF-CI-R171-T2", "OFF-CO-R171", "OFF-LB-R171"],
              "VA": ["OFF-CI-NCAPVA-1", "OFF-CI-NCAPVA-2", "OFF-CO-NCAPVA-1", "OFF-CO-NCAPVA-2", "OFF-LB-NCAPVA"],
              "AD": ["OFF-CI-NCAPAD-1", "OFF-CI-NCAPAD-2", "OFF-CO-NCAPAD-1", "OFF-CO-NCAPAD-2"]}
    g = {k: (sum(is_safe(off[i]["verdict"]) for i in v), sum(is_safe(offp[i]["verdict"]) for i in v), len(v))
         for k, v in groups.items()}
    vimp = lambda d, i: f"{float(d[i]['v_rel_impact_kph']):.1f} km/h"  # noqa: E731
    need += [("R171 official", f"| {g['R171'][0]}/{g['R171'][2]} 安全 | {g['R171'][1]}/{g['R171'][2]} 安全 |"),
             ("VA official", f"| {g['VA'][0]}/{g['VA'][2]} 安全（CCRb 最近跟车距离碰撞 {vimp(off, 'OFF-LB-NCAPVA')}） | "
                             f"{g['VA'][1]}/{g['VA'][2]} 安全 |"),
             ("AD official", f"| {g['AD'][0]}/{g['AD'][2]} 安全（切出 90/70、TTC 2 s 碰撞 {vimp(off, 'OFF-CO-NCAPAD-2')}） | "
                             f"{g['AD'][1]}/{g['AD'][2]} 安全（另有切入 50/10、TTC −1.5 s 碰撞 {vimp(offp, 'OFF-CI-NCAPAD-1')}） |"),
             ("CCRb fixed", f"该点 TTC {float(offp['OFF-LB-NCAPVA']['min_ttc_s']):.2f} s 无碰撞")]
    expect("CCRb proposed collision", offp["OFF-LB-NCAPVA"]["collision"], "False")

    # failure boundary (table 4) and unsafe-run classification (table 3)
    bd = {(float(r["dv_kph"]), float(r["vlat_mps"])): float(r["ttc_star"]) for r in load("cutin_boundary_baseline")}
    need += [("boundary 50/1", f"基线 TTC* = {bd[(50.0, 1.0)]:+.2f} s".replace("-", "−")),
             ("boundary 60/2", f"TTC* = {bd[(60.0, 2.0)]:+.2f} s")]
    m = re.search(r"\| 基线 \| (\d+) \| (\d+) \| (\d+) \| (\d+) \|", tables.split("### 表 3", 1)[1])
    expect("tables.md table 3 unsafe = grid unsafe", int(m.group(1)), gn - gs)
    need.append(("unsafe split", f"不安全的 {m.group(1)} 次里，{m.group(2)} 次"))
    need.append(("unsafe split 2", f"{m.group(3)} 次是反应链"))

    # trade-off
    tr = load("tradeoff")
    sel = [r for r in tr if r["selected"] == "True"]
    expect("tradeoff: exactly one selected", len(sel), 1)
    tsel = jload("tradeoff_selected.json")["t_pred_s"]
    expect("tradeoff selected t_pred", float(sel[0]["t_pred_s"]), tsel)
    expect("tradeoff selected G = proposed grid safe", int(sel[0]["G_grid_safe"]), ps)
    for r in tr:
        expect(f"tradeoff grid_n t_pred={r['t_pred_s']}", int(r["grid_n"]), gn)
    g0, g1 = int(tr[0]["G_grid_safe"]), int(tr[-1]["G_grid_safe"])
    f0, f1, fn = int(tr[0]["FB_false_brake"]), int(tr[-1]["FB_false_brake"]), int(tr[0]["FB_n"])
    need += [("tradeoff candidates", f"0–{float(tr[-1]['t_pred_s']):.1f} s 共 {len(tr)} 档"),
             ("tradeoff G", f"（{g0} → {g1}）"), ("tradeoff FB", f"从 {f0}/{fn} 升到 {f1}/{fn}"),
             ("tradeoff selected", f"选中 {tsel:g} s")]

    # cross-check, time step, robustness
    xc = sb["crosscheck"]
    expect("crosscheck rows", len(load("backend_crosscheck")), xc["n"])
    expect("crosscheck all same verdict", xc["same_verdict"], xc["n"])
    need.append(("crosscheck", f"{xc['n']} 个抽查用例的状态序列和判定全部一致，最小间距最多差 {Decimal(str(xc['max_d_min_gap_m'])).quantize(Decimal('0.001'), ROUND_HALF_UP)} m"))
    dt = [r for r in load("dt_sensitivity") if r["case_id"].startswith(("OFF-CI", "OFF-CO", "OFF-LB"))]
    same = sum(r["verdict_20ms"] == r["verdict_10ms"] for r in dt)
    need.append(("dt sensitivity", f"{len(dt)} 个官方纵向点判定一致 {same} 个"))

    # requirements, traceability, scenarios, tests
    reqs = load("requirements", ROOT)
    need.append(("requirements", f"{len(reqs)} 条"))
    with open(ROOT / "traceability.csv", encoding="utf-8", newline="") as f:
        n_trace = sum(1 for _ in csv.DictReader(f))
    need.append(("traceability rows", f"（{n_trace} 行，"))
    spec = importlib.util.spec_from_file_location("mt", ROOT / "scripts" / "make_traceability.py")
    mt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mt)
    n_cases = len(mt.grid_index())
    need.append(("OpenSCENARIO cases", f"共 {n_cases} 个用例"))
    n_tests = sum(len(re.findall(r"^def test_", p.read_text(encoding="utf-8"), re.M)) for p in (ROOT / "tests").glob("test_*.py"))
    need.append(("unit tests", f"pytest {n_tests} 项"))

    # English summary at the top of the README uses the same numbers
    need += [("EN cases", f"{n_cases} OpenSCENARIO cases"), ("EN reqs", f"{len(reqs)} clause-tagged requirements"),
             ("EN grid", f"{gs}/{gn} cut-in grid points safe at baseline"),
             ("EN tradeoff", f"{gs} → {ps}"), ("EN latprobe", f"{fb_b}/{ln_} → {fb_p}/{ln_}"),
             ("EN leadbrake", f"{ls_b} → {ls_p} of {ln}"),
             ("EN checks", f"{cb['pass']}/{cb['fail']} → {cp['pass']}/{cp['fail']}")]

    for what, sub in need:
        if sub not in readme:
            ERR.append(f"README.md does not contain [{what}]: {sub!r}")
    return len(need)


def compare(committed: Path):
    n = 0
    for sfx in ("", "_proposed"):
        for name in PRIMARY:
            old = {r["case_id"]: r["verdict"] for r in load(name + sfx, committed)}
            new = {r["case_id"]: r["verdict"] for r in load(name + sfx)}
            expect(f"{name}{sfx}: case ids", sorted(new), sorted(old))
            for cid, v in old.items():
                n += 1
                if new.get(cid) != v:
                    ERR.append(f"{name}{sfx} {cid}: fresh verdict {new.get(cid)!r}, committed {v!r}")
        old_fb = jload(f"summary{sfx}.json", committed)["latprobe_false_brake"]
        expect(f"latprobe false braking{sfx}", jload(f"summary{sfx}.json")["latprobe_false_brake"], old_fb)
        key = lambda r: (sfx, r["req_id"], r["case_id"])  # noqa: E731
        old_c = {(key(r), r["item"]): r["verdict"] for r in load("checks" + sfx, committed)}
        new_c = {(key(r), r["item"]): r["verdict"] for r in load("checks" + sfx)}
        expect(f"checks{sfx}: rows", sorted(new_c), sorted(old_c))
        diff = {k[0] for k in old_c if new_c.get(k) != old_c[k]}
        expect(f"checks{sfx}: rows that differ between backends", diff, KNOWN_BACKEND_DIFF if sfx == "" else set())
    got = jload("summary.json")["checks"]
    expect("python-backend baseline checks", (got["pass"], got["fail"], got["info"]), (127, 3, 12))
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compare", metavar="COMMITTED_RESULTS_DIR",
                    help="compare the current results/ (fresh Python-backend run) with a copy of the committed results")
    a = ap.parse_args()
    if a.compare:
        n = compare(Path(a.compare))
        label = f"{n} per-case verdicts compared with {a.compare}"
    else:
        n = static_check()
        label = f"{n} README numbers recomputed from results/"
    if ERR:
        print("check_results: FAIL")
        for e in ERR:
            print("  -", e)
        return 1
    print(f"check_results: OK ({label})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
