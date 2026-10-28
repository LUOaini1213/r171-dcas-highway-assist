"""Figures for report.md (matplotlib, Agg).  English labels so the figures render with any font set (as in P7).
Colours: validated reference palette of the data-viz guide (categorical slots 1-2, status colours with labels).

Run:  python -X utf8 -I scripts/make_figures.py
"""
import csv
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
OUT = RES / "figures"
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e1e0d9"
S1, S2 = "#2a78d6", "#eb6834"
STATUS = {"PASS": "#0ca30c", "PASS_HARSH": "#fab219", "FAIL_TTC": "#ec835a", "FAIL_COLLISION": "#d03b3b"}
LABEL = {"PASS": "pass", "PASS_HARSH": "pass, braking > 3.5 m/s2", "FAIL_TTC": "no contact, min TTC < 1 s",
         "FAIL_COLLISION": "collision"}
plt.rcParams.update({"font.size": 8, "axes.edgecolor": "#c3c2b7", "axes.labelcolor": INK2, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.facecolor": SURF, "figure.facecolor": SURF, "savefig.facecolor": SURF,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
                     "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False})


def load(name):
    p = RES / name
    return list(csv.DictReader(open(p, encoding="utf-8"))) if p.exists() else []


def series(name):
    rows = load(f"timeseries/{name}.csv")
    if not rows:
        return None
    out = {k: [] for k in rows[0]}
    for r in rows:
        for k, v in r.items():
            try:
                out[k].append(float(v))
            except ValueError:
                out[k].append(v)
    return out


def fig_cutin_map():
    g = load("cutin_grid.csv")
    if not g:
        return
    bb = {(float(r["dv_kph"]), float(r["vlat_mps"])): r for r in load("cutin_boundary_baseline.csv")}
    bp = {(float(r["dv_kph"]), float(r["vlat_mps"])): r for r in load("cutin_boundary_proposed.csv")}
    vls = sorted({float(r["vlat"]) for r in g})
    ttcs = sorted({float(r["ttc"]) for r in g})
    dvs = sorted({float(r["dv_kph"]) for r in g})
    fig, axes = plt.subplots(2, 3, figsize=(10.5, 6.2), sharex=True, sharey=True)
    for ax, vl in zip(axes.flat, vls):
        for r in g:
            if float(r["vlat"]) != vl:
                continue
            x, y = ttcs.index(float(r["ttc"])), dvs.index(float(r["dv_kph"]))
            ax.add_patch(plt.Rectangle((x - 0.46, y - 0.44), 0.92, 0.88, color=STATUS[r["verdict"]], lw=0))
        for d, style, lab in ((bb, "-", "TTC* baseline"), (bp, "--", "TTC* proposed")):
            xs, ys = [], []
            for dv in dvs:
                r = d.get((dv, vl))
                if not r or r["mode"] != "bisect":
                    continue
                t = float(r["ttc_star"])
                # position on the categorical TTC axis (linear between grid values)
                i = max(k for k, v in enumerate(ttcs) if v <= t + 1e-9)
                frac = 0.0 if i == len(ttcs) - 1 else (t - ttcs[i]) / (ttcs[i + 1] - ttcs[i])
                xs.append(i + frac - 0.5)
                ys.append(dvs.index(dv))
            if xs:
                ax.plot(xs, ys, style, color=INK, lw=1.4, marker="o", ms=3, label=lab)
        ax.set_title(f"mean lateral speed {vl:g} m/s", fontsize=9, color=INK, loc="left")
        ax.set_xticks(range(len(ttcs)), [f"{t:g}" for t in ttcs])
        ax.set_yticks(range(len(dvs)), [f"{d:g}" for d in dvs])
        ax.set_xlim(-0.6, len(ttcs) - 0.4)
        ax.set_ylim(-0.6, len(dvs) - 0.4)
        ax.grid(False)
    for ax in axes[1]:
        ax.set_xlabel("cut-in TTC at end of lane change (s)")
    for ax in axes[:, 0]:
        ax.set_ylabel("relative speed (km/h)")
    handles = [Patch(color=STATUS[k], label=LABEL[k]) for k in STATUS]
    handles += axes.flat[-1].get_legend_handles_labels()[0][:2]
    fig.legend(handles=handles, loc="lower center", ncol=6, fontsize=8)
    fig.suptitle("Cut-in grid, VUT 120 km/h, baseline verdicts (model-internal); lines = failure boundary TTC* "
                 "(solid baseline, dashed proposed); blank = target would start < 5 m ahead (not run)",
                 x=0.01, ha="left", fontsize=9.5, color=INK)
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    fig.savefig(OUT / "fig1_cutin_map.png", dpi=160)
    plt.close(fig)


def fig_root_cause():
    tl = load("root_cause_timeline.csv")
    lon = [r for r in tl if not r["case_id"].startswith("CV-")]
    if not lon:
        return
    fig, axes = plt.subplots(len(lon), 2, figsize=(10.5, 2.4 * len(lon)), squeeze=False)
    for row, r in zip(axes, lon):
        s = series(f"RC-{r['case_id']}")
        if s is None:
            continue
        a0, a1 = row
        x0, x1 = max(0.0, float(r["manoeuvre_start_s"] or 0) - 1.5), s["t"][-1]
        a0.plot(s["t"], s["a_cmd"], color=S1, lw=1.6, label="commanded")
        a0.plot(s["t"], s["a"], color=S2, lw=1.6, label="achieved")
        a0.axhline(-5.0, color=INK2, lw=0.8, ls=":")
        a0.text(x0 + 0.1, -4.85, "DCAS authority -5 m/s2", fontsize=7, color=INK2, va="bottom")
        a0.set_ylabel("accel (m/s2)")
        gap = [g if g == g else None for g in s["gap"]]
        a1.plot(s["t"], gap, color=S1, lw=1.6)
        a1.set_ylabel("gap to object (m)")
        for ax in row:
            ax.set_xlim(x0, x1)
            for key, lab in (("manoeuvre_start_s", "start"), ("t_selected", "selected"), ("t_brake", "brake"), ("t_collision", "contact")):
                if r[key] and x0 <= float(r[key]) <= x1:
                    ax.axvline(float(r[key]), color=INK2, lw=0.7, ls="--")
                    ax.text(float(r[key]), ax.get_ylim()[1], f" {lab}", fontsize=6.5, color=INK2, va="top", rotation=90)
        a0.set_title(r["case_id"], fontsize=9, color=INK, loc="left")
        a0.legend(fontsize=7, loc="center right")
    axes[-1][0].set_xlabel("time (s)")
    axes[-1][1].set_xlabel("time (s)")
    fig.suptitle("Representative failures, baseline parameters (model-internal)", x=0.01, ha="left", fontsize=10, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(OUT / "fig2_root_cause.png", dpi=160)
    plt.close(fig)


def fig_tradeoff():
    tr = load("tradeoff.csv")
    if not tr:
        return
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    x = [100 * float(r["FB_share"]) for r in tr]
    y = [int(r["G_grid_safe"]) for r in tr]
    ax.plot(x, y, color=S1, lw=1.2, marker="o", ms=6)
    for i, (r, xi, yi) in enumerate(zip(tr, x, y)):
        dy = -12 if (r["selected"] == "True" or i % 2) else 5
        ax.annotate(f"t_pred {float(r['t_pred_s']):g} s", (xi, yi), textcoords="offset points", xytext=(-14 if i % 2 else 6, dy),
                    fontsize=7.5, color=INK, fontweight="bold" if r["selected"] == "True" else "normal")
        if r["selected"] == "True":
            ax.scatter([xi], [yi], s=160, facecolors="none", edgecolors=INK, lw=1.2)
    ax.axvline(10.0, color=INK2, lw=0.9, ls="--")
    ax.text(10.4, min(y), "constraint C1: false braking <= 10 %", fontsize=7.5, color=INK2, va="bottom")
    ax.set_xlabel("false braking on non-threatening lateral approaches (% of 144 runs)")
    ax.set_ylabel(f"safe cut-in grid points (of {tr[0]['grid_n']})")
    ax.set_title("Earlier cut-in reaction vs false braking (selection rule fixed before the run)", fontsize=9, color=INK, loc="left")
    fig.tight_layout()
    fig.savefig(OUT / "fig3_tradeoff.png", dpi=160)
    plt.close(fig)


def fig_engagement():
    s = series("EG-06-unresponsive")
    if s is None:
        return
    levels = ["", "HOR", "EOR", "HOR_ESC", "EOR_ESC", "DCA", "UNAVAILABLE"]
    states = ["OFF", "STANDBY", "ACTIVE", "DRIVER_OVERRIDE", "TAKEOVER_REQUEST", "MRM"]
    fig, axes = plt.subplots(4, 1, figsize=(8.5, 6.4), sharex=True)
    axes[0].plot(s["t"], s["vis_s"], color=S1, lw=1.6)
    axes[0].set_ylabel("visual\ndisengagement (s)")
    axes[0].axhline(3.3, color=INK2, lw=0.8, ls=":")
    axes[0].text(0.5, 3.5, "EOR threshold 3.3 s (R171 <= 5 s)", fontsize=7, color=INK2)
    lv = [levels.index(x) if x in levels else 0 for x in s["level"]]
    axes[1].step(s["t"], lv, where="post", color=S1, lw=1.6)
    axes[1].set_yticks(range(len(levels)), ["none", "HOR", "EOR", "HOR esc.", "EOR esc.", "DCA", "unavailable"])
    axes[1].set_ylabel("request")
    st = [states.index(x) if x in states else 0 for x in s["state"]]
    axes[2].step(s["t"], st, where="post", color=S1, lw=1.6)
    axes[2].set_yticks(range(len(states)), ["off", "stand-by", "active", "override", "take-over req.", "MRM"])
    axes[2].set_ylabel("mode")
    axes[3].plot(s["t"], [v * 3.6 for v in s["v"]], color=S1, lw=1.6)
    axes[3].set_ylabel("speed (km/h)")
    axes[3].set_xlabel("time (s); phone gaze from 10 s, driver never responds")
    for ax in axes:
        ax.axvline(10.0, color=INK2, lw=0.7, ls="--")
    fig.suptitle("EG-06: escalation EOR -> escalated EOR -> DCA -> risk-mitigation stop (model-internal)",
                 x=0.01, ha="left", fontsize=10, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(OUT / "fig4_engagement_timeline.png", dpi=160)
    plt.close(fig)


def fig_curve():
    a, b = series("CV-R374-v120-csa"), series("CV-R374-v120-nocsa")
    if a is None or b is None:
        return
    fig, axes = plt.subplots(3, 1, figsize=(8.5, 6.0), sharex=True)
    for s, col, lab in ((a, S1, "curve-speed adaptation on"), (b, S2, "adaptation off")):
        axes[0].plot(s["s"], [v * 3.6 for v in s["v"]], color=col, lw=1.6, label=lab)
        axes[1].plot(s["s"], s["d"], color=col, lw=1.6, label=lab)
        axes[2].plot(s["s"], [abs(x) for x in s["ay"]], color=col, lw=1.6, label=lab)
    axes[0].set_ylabel("speed (km/h)")
    axes[1].set_ylabel("lateral offset (m)")
    axes[1].axhline(-0.825, color=INK2, lw=0.8, ls=":")
    axes[1].text(a["s"][0], -0.8, "body edge on lane line", fontsize=7, color=INK2)
    axes[2].set_ylabel("|a_y| (m/s2)")
    axes[2].axhline(2.8, color=INK2, lw=0.8, ls=":")
    axes[2].text(a["s"][0], 2.85, "declared 2.5 + 0.3 (R171 5.3.7.1.2)", fontsize=7, color=INK2)
    st = b["state"]
    i_tor = next((i for i, x in enumerate(st) if x == "TAKEOVER_REQUEST"), None)
    i_drv = next((i for i, x in enumerate(st) if x == "STANDBY" and i_tor is not None and i > i_tor), None)
    for ax in axes:
        for i, lab in ((i_tor, "DCA (adaptation off)"), (i_drv, "driver steers")):
            if i is not None:
                ax.axvline(b["s"][i], color=INK2, lw=0.7, ls="--")
    for i, lab, ha in ((i_tor, "DCA (off case) ", "right"), (i_drv, " driver steers from here", "left")):
        if i is not None:
            axes[2].text(b["s"][i], 3.6, lab, fontsize=7, color=INK2, va="top", ha=ha)
    axes[2].set_xlabel("station along the road (m); curve R374 m starts at 600 m")
    axes[0].legend(fontsize=7.5, loc="lower left")
    fig.suptitle("Lane centring on R374 m at a set speed of 120 km/h, baseline (model-internal)", x=0.01, ha="left",
                 fontsize=10, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(OUT / "fig5_curve.png", dpi=160)
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fig_cutin_map()
    fig_root_cause()
    fig_tradeoff()
    fig_engagement()
    fig_curve()
    print("figures:", sorted(p.name for p in OUT.glob("*.png")))
    _ = json


if __name__ == "__main__":
    main()
