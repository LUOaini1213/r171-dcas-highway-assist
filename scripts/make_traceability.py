"""Build traceability.csv (clause -> requirement -> scenario / test -> result) and check completeness:
  forward : every requirement has at least one test row, or an explicit N/A reason
  backward: every case of every OpenSCENARIO grid file traces to at least one requirement; every pytest function
            with a "REQ:" line and every requirement check names existing requirement IDs
Run:  python -X utf8 -I scripts/make_traceability.py     (exit code 1 if a trace is missing)
"""
import ast
import csv
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dcas.requirements import REQS, by_id  # noqa: E402
from dcas.scenarios import SCEN_DIR, read_grid  # noqa: E402

RES = ROOT / "results"
CONFIGS = (("", "基线"), ("_proposed", "改进"))
SUITE_FILES = {"cutin_official": "cutin_official", "cutin_grid": "cutin_grid", "cutout": "cutout",
               "leadbrake": "leadbrake", "curve": "curve", "latprobe": "latprobe", "engagement": "engagement",
               "functional": "functional"}
VZH = {"PASS": "通过", "PASS_HARSH": "通过（制动 >3.5 m/s²）", "FAIL_COLLISION": "不通过（碰撞）",
       "FAIL_TTC": "不通过（TTC<1 s）", "FAIL_DECEL": "不通过（减速度）", "FAIL_LATERAL": "不通过（横向）",
       "BOUNDARY_HANDLED": "通过（到达边界，DCA 早于越线）", "-": "见需求检查"}


def load(name):
    p = RES / name
    return list(csv.DictReader(open(p, encoding="utf-8"))) if p.exists() else []


def grid_index():
    idx = {}
    for p in sorted(SCEN_DIR.glob("*.xosc")):
        root = ET.parse(p).getroot()
        if root.find("ParameterValueDistribution") is None:
            continue
        scen, sets = read_grid(p.name)
        for s in sets:
            idx[s["CaseId"]] = (p.name, s.get("ScenarioFile", scen))
    return idx


def unit_tests():
    out = []
    for f in sorted((ROOT / "tests").glob("test_*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                doc = ast.get_docstring(node) or ""
                if "REQ:" in doc:
                    ids = [x.strip() for x in doc.split("REQ:")[1].split(",")]
                    out.append((f"{f.name}::{node.name}", ids, doc.split("REQ:")[0].strip()))
    return out


def junit_verdicts():
    p = RES / "pytest_junit.xml"
    if not p.exists():
        return {}
    out = {}
    for tc in ET.parse(p).getroot().iter("testcase"):
        name = f"{tc.get('classname').split('.')[-1]}.py::{tc.get('name')}"
        if tc.find("failure") is not None or tc.find("error") is not None:
            out[name] = "不通过"
        elif tc.find("skipped") is not None:
            out[name] = "跳过"
        else:
            out[name] = "通过"
    return out


def case_result(r: dict) -> str:
    fam = r.get("family", "")
    if fam in ("CutIn", "CutOut", "LeadBrake"):
        ttc = r.get("min_ttc_s") or "-"
        return (f"碰撞 {r['collision']}（{r['v_rel_impact_kph']} km/h），最小 TTC {ttc} s，"
                f"500 ms 减速度峰值 {r['peak_decel_500ms']} m/s²")
    if fam.startswith("Curve") or fam == "SBend":
        return (f"系统 a_y 峰值 {r['peak_ay']} m/s²，0.5 s 冲击度 {r['peak_jy_500ms']} m/s³，最大偏移 {r['max_abs_d']} m，"
                f"越线 {r['lane_departure']}，最低车速 {r['v_min_kph']} km/h")
    if fam == "LatProbe":
        return f"对探测车最大指令减速度 {r['brake_on_object'] or '0'}，速度损失 {float(r['v0_kph']) - float(r['v_min_kph']):.2f} km/h"
    return r.get("states", "")


def main() -> int:
    gidx = grid_index()
    units = unit_tests()
    junit = junit_verdicts()
    suites = {}
    for key, base in SUITE_FILES.items():
        for suf, cfg in CONFIGS:
            suites.setdefault(key, []).extend((cfg, r) for r in load(f"{base}{suf}.csv"))
    for suf, cfg in (("baseline", "基线"), ("proposed", "改进")):
        suites.setdefault("cutin_refine", []).extend((cfg, r) for r in load(f"cutin_refine_{suf}.csv"))
    checks = [("基线", r) for r in load("checks.csv")] + [("改进", r) for r in load("checks_proposed.csv")]
    trade = load("tradeoff.csv")
    by_case = defaultdict(list)
    for key, rows in suites.items():
        for cfg, r in rows:
            by_case[r["case_id"]].append((key, cfg, r))
    rows = []

    def add(req, test_type, test_id, cfg, result, verdict, note=""):
        g = gidx.get(test_id, ("-", "-"))
        rows.append({"req_id": req.rid, "source": req.source, "clause": req.clause, "requirement": req.text,
                     "kind": req.kind, "test_type": test_type, "test_id": test_id, "grid_file": g[0],
                     "scenario_file": g[1], "config": cfg, "result": result, "verdict": verdict, "note": note})

    for req in REQS:
        for sel in req.tests:
            if sel.startswith("suite:"):
                key = sel.split(":", 1)[1]
                if key == "tradeoff":
                    for t in trade:
                        add(req, "参数权衡", f"t_pred={t['t_pred_s']}", "权衡候选",
                            f"切入网格安全 {t['G_grid_safe']}/{t['grid_n']}，误制动 {t['FB_false_brake']}/{t['FB_n']}",
                            t["status"])
                    continue
                for cfg, r in suites.get(key, []):
                    if key == "latprobe":
                        v = "误制动" if r.get("false_brake") == "True" else "无误制动"
                    else:
                        v = VZH.get(r["verdict"], r["verdict"])
                    add(req, "仿真用例", r["case_id"], cfg, case_result(r), v, r.get("label", ""))
            elif sel.startswith("case:"):
                for cid in sel.split(":", 1)[1].split(","):
                    for key, cfg, r in by_case.get(cid, []):
                        add(req, "仿真用例", cid, cfg, case_result(r), VZH.get(r["verdict"], r["verdict"]), r.get("label", ""))
            elif sel.startswith("check:"):
                rid = sel.split(":", 1)[1]
                for cfg, c in checks:
                    if c["req_id"] == rid:
                        add(req, "需求检查", c["case_id"], cfg, f"{c['item']}：{c['measured']}（限值 {c['limit']}）", c["verdict"],
                            c.get("note", ""))
        for name, ids, title in units:           # every pytest function that names this requirement in "REQ:"
            if req.rid in ids:
                add(req, "单元测试", name, "-", title, junit.get(name, "未运行"))
        if req.na:
            add(req, "N/A", "-", "-", "本项目未验证", "N/A", req.na)

    problems = []
    traced = defaultdict(list)
    for r in rows:
        traced[r["req_id"]].append(r)
    for req in REQS:
        real = [r for r in traced[req.rid] if r["test_type"] != "N/A"]
        if not real and not req.na:
            problems.append(f"forward: {req.rid} has no test and no N/A reason")
    reg = by_id()
    for name, ids, _t in units:
        for i in ids:
            if i not in reg:
                problems.append(f"backward: {name} names unknown requirement {i}")
    for _cfg, c in checks:
        if c["req_id"] not in reg:
            problems.append(f"backward: check row names unknown requirement {c['req_id']}")
    traced_ids = {r["test_id"] for r in rows}
    for cid, (grid, _scen) in gidx.items():
        if cid not in traced_ids:
            problems.append(f"backward: case {cid} ({grid}) traces to no requirement")
    with open(ROOT / "traceability.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with open(ROOT / "requirements.csv", "w", newline="", encoding="utf-8-sig") as f:     # registry export
        w = csv.DictWriter(f, fieldnames=["req_id", "source", "clause", "requirement", "kind", "verification", "n_rows", "na_reason"])
        w.writeheader()
        for req in REQS:
            types = sorted({r["test_type"] for r in traced[req.rid]})
            w.writerow({"req_id": req.rid, "source": req.source, "clause": req.clause, "requirement": req.text,
                        "kind": req.kind, "verification": "、".join(types), "n_rows": len(traced[req.rid]),
                        "na_reason": req.na})
    # summary for report.md
    L = ["<!-- generated by scripts/make_traceability.py -->", "",
         "| 需求 | 来源条款 | 验证方式 | 行数 | 判定计数 |", "|---|---|---|---:|---|"]
    for req in REQS:
        rs = traced[req.rid]
        types = sorted({r["test_type"] for r in rs})
        cnt = defaultdict(int)
        for r in rs:
            cnt[r["verdict"]] += 1
        L.append(f"| {req.rid} | {req.clause} | {'、'.join(types)} | {len(rs)} | "
                 f"{'，'.join(f'{k} {v}' for k, v in sorted(cnt.items()))} |")
    L += ["", f"完整性检查：{'通过（每条需求都有测试或 N/A 理由；每个 OpenSCENARIO 用例、每个带 REQ 标注的单元测试都能追溯到需求）' if not problems else '；'.join(problems)}",
          f"总行数 {len(rows)}；需求 {len(REQS)} 条；OpenSCENARIO 用例 {len(gidx)} 个；带 REQ 标注的单元测试 {len(units)} 个。"]
    (RES / "traceability_summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"{len(rows)} rows, {len(REQS)} requirements, {len(gidx)} OpenSCENARIO cases, {len(units)} unit tests; "
          f"problems: {problems or 'none'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
