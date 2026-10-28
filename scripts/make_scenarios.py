"""Write the OpenDRIVE roads, the parameterised OpenSCENARIO families and the grid files into scenarios/.

Run:  python -X utf8 -I scripts/make_scenarios.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))          # -I does not add the project to sys.path

from dcas import xosc  # noqa: E402
from dcas.road import all_roads  # noqa: E402
from dcas.scenarios import SCEN_DIR, SUITES, curve_suite_files, cutin_grid_cases, read_grid, write_grid  # noqa: E402

DESC = {
    "highway_straight": "Straight 6 km motorway, three 3.5 m lanes (-1, -2, -3), traffic in +s.  Ego lane -2.",
    "sbend_r171": "R171 Annex 4 4.2.4.1 S-bend (01 series): clothoid A153.7 L30 / arc R787 L57.1 / clothoid A105 L14, "
                  "then the opposite turn clothoid A98.6 L26 / arc R374 L5.1 / clothoid A120.8 L39, after 600 m straight.",
    "curve_R250": "Constant-radius test curve R250 m (100 m clothoids, 450 m arc) after 600 m straight - project choice.",
    "curve_R374": "Constant-radius test curve R374 m (radius of the 2nd R171 S-bend turn), 100 m clothoids, 450 m arc.",
    "curve_R500": "Constant-radius test curve R500 m (100 m clothoids, 450 m arc) after 600 m straight - project choice.",
}


def main():
    SCEN_DIR.mkdir(exist_ok=True)
    for name, road in all_roads().items():
        (SCEN_DIR / f"{name}.xodr").write_text(road.to_xodr(DESC[name]), encoding="utf-8")
    fams = {"CutIn.xosc": xosc.family_cutin(), "CutOut.xosc": xosc.family_cutout(),
            "LeadBrake.xosc": xosc.family_leadbrake(), "LatProbe.xosc": xosc.family_latprobe(),
            "Highway.xosc": xosc.family_highway()}
    for fam, road in (("Curve_R250", "curve_R250"), ("Curve_R374", "curve_R374"), ("Curve_R500", "curve_R500"),
                      ("SBend", "sbend_r171")):
        fams[f"{fam}.xosc"] = xosc.family_curve(road, f"{fam}: Ego alone on {road}.xodr (lane centring, curve-speed adaptation).\n"
                                                    "R171 5.3.7.1 and Annex 4 4.2.5.1.1.")
    for f, text in fams.items():
        (SCEN_DIR / f).write_text(text, encoding="utf-8")
    for name, (fam, fn) in SUITES.items():
        cases = fn()
        write_grid(name, fam, cases)
    for name, (fam, cases) in curve_suite_files().items():
        write_grid(name, fam, cases)
    n_inv = len(cutin_grid_cases(True)) - len(cutin_grid_cases())
    for p in sorted(SCEN_DIR.glob("*_grid.xosc")) + sorted(SCEN_DIR.glob("*_official.xosc")) + sorted(SCEN_DIR.glob("*_cases.xosc")):
        scen, sets = read_grid(p.name)
        print(f"{p.name}: {len(sets)} cases of {scen}")
    print(f"cut-in combinations left out (target would start < 5 m ahead): {n_inv}")


if __name__ == "__main__":
    main()
