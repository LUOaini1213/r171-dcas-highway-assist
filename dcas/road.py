"""Road geometry shared by the OpenDRIVE generator and the Python controller / Python backend.

A road is a list of segments along the reference line; curvature varies linearly inside a segment
(line: 0, arc: constant, spiral: clothoid from k0 to k1).  The SAME definition is written to OpenDRIVE
(.xodr, read by esmini) and evaluated in Python (curvature preview for lane centring and curve-speed
adaptation), so both sides use one geometry.

Lane layout (project choice): one carriageway, three driving lanes of 3.5 m on the right of the reference
line (OpenDRIVE lanes -1, -2, -3, traffic in +s).  The Ego drives in lane -2 (middle lane).

R171 Annex 4 para. 4.2.4.1 S-bend (EUR-Lex OJ L 2025/1899, 01 series), read as:
  1st turn: clothoid A 153.7 m, L 30.0 m -> arc R 787 m, L 57.1 m -> clothoid A 105.0 m, L 14.0 m
  2nd turn (opposite direction): clothoid A 98.6 m, L 26 m -> arc R 374 m, L 5.1 m -> clothoid A 120.8 m, L 39 m
  (A^2 = R * L holds for every clothoid: 153.7^2/30 = 787, 105^2/14 = 787, 98.6^2/26 = 374, 120.8^2/39 = 374.)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from xml.sax.saxutils import escape

LANE_WIDTH_M = 3.5                  # project choice (R171 Annex 4 4.2.5.1.2.1.1 uses 3.5 m as the example)
N_LANES = 3
EGO_LANE = -2                       # middle lane


def lane_center_t(lane_id: int) -> float:
    """Lateral position t of a lane centre (negative = right of the reference line)."""
    return -(abs(lane_id) - 0.5) * LANE_WIDTH_M


@dataclass(frozen=True)
class Segment:
    kind: str                       # "line" | "arc" | "spiral"
    length: float
    k0: float = 0.0
    k1: float = 0.0

    def curvature(self, u: float) -> float:
        if self.kind == "line":
            return 0.0
        if self.kind == "arc":
            return self.k0
        return self.k0 + (self.k1 - self.k0) * u / self.length


def spiral_from_A(A: float, length: float, k_from: float, sign_to: float) -> Segment:
    """Clothoid of parameter A and length L: |dk| = L / A^2.  sign_to is the sign of the curvature change."""
    dk = length / (A * A)
    return Segment("spiral", length, k_from, k_from + sign_to * dk)


@dataclass
class Road:
    name: str
    segments: list[Segment]

    def __post_init__(self):
        self.starts = []
        s = 0.0
        for seg in self.segments:
            self.starts.append(s)
            s += seg.length
        self.length = s

    def curvature(self, s: float) -> float:
        """Curvature of the reference line at s (1/m, > 0 = left turn)."""
        if s <= 0.0:
            return self.segments[0].curvature(0.0)
        for s0, seg in zip(self.starts, self.segments):
            if s < s0 + seg.length:
                return seg.curvature(s - s0)
        return self.segments[-1].curvature(self.segments[-1].length)

    def lane_curvature(self, s: float, t: float) -> float:
        """Curvature of a path at constant lateral offset t from the reference line."""
        k = self.curvature(s)
        return k / (1.0 - k * t)

    def max_abs_curvature(self, s0: float, s1: float, step: float = 2.0) -> float:
        n = max(1, int((s1 - s0) / step))
        return max(abs(self.curvature(s0 + i * (s1 - s0) / n)) for i in range(n + 1))

    # ------------------------------------------------------------------ OpenDRIVE
    def planview(self) -> list[tuple[float, float, float, float, Segment]]:
        """(s, x, y, hdg, segment) for every segment, integrating the reference line numerically."""
        out = []
        x = y = h = 0.0
        for s0, seg in zip(self.starts, self.segments):
            out.append((s0, x, y, h, seg))
            n = max(10, int(seg.length / 0.05))
            du = seg.length / n
            for i in range(n):                   # exact heading for linear curvature, position at mid-step heading
                ka, kb = seg.curvature(i * du), seg.curvature((i + 1) * du)
                h_mid = h + ka * du / 2.0 + (kb - ka) * du / 8.0
                x += math.cos(h_mid) * du
                y += math.sin(h_mid) * du
                h += 0.5 * (ka + kb) * du
        return out

    def to_xodr(self, description: str) -> str:
        geoms = []
        for s0, x, y, h, seg in self.planview():
            head = f'      <geometry s="{s0:.6f}" x="{x:.6f}" y="{y:.6f}" hdg="{h:.9f}" length="{seg.length:.6f}">'
            if seg.kind == "line":
                body = "        <line/>"
            elif seg.kind == "arc":
                body = f'        <arc curvature="{seg.k0:.9f}"/>'
            else:
                body = f'        <spiral curvStart="{seg.k0:.9f}" curvEnd="{seg.k1:.9f}"/>'
            geoms.append("\n".join([head, body, "      </geometry>"]))
        lanes = []
        for i in range(1, N_LANES + 1):
            mark = "solid" if i == N_LANES else "broken"
            lanes.append(f'''          <lane id="-{i}" type="driving" level="false">
            <link/>
            <width sOffset="0.0" a="{LANE_WIDTH_M}" b="0.0" c="0.0" d="0.0"/>
            <roadMark sOffset="0.0" type="{mark}" weight="standard" color="standard" width="0.15"/>
            <speed sOffset="0.0" max="130" unit="km/h"/>
          </lane>''')
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<!--
{escape(description)}
Generated by scripts/make_scenarios.py from dcas/road.py (do not edit by hand).
-->
<OpenDRIVE>
  <header revMajor="1" revMinor="5" name="{self.name}" version="1.0" date="2026-10-28T00:00:00"/>
  <road name="{self.name}" length="{self.length:.6f}" id="1" junction="-1">
    <link/>
    <type s="0.0" type="motorway">
      <speed max="130" unit="km/h"/>
    </type>
    <planView>
{chr(10).join(geoms)}
    </planView>
    <elevationProfile>
      <elevation s="0.0" a="0.0" b="0.0" c="0.0" d="0.0"/>
    </elevationProfile>
    <lateralProfile/>
    <lanes>
      <laneSection s="0.0">
        <center>
          <lane id="0" type="none" level="false">
            <link/>
            <roadMark sOffset="0.0" type="solid" weight="standard" color="standard" width="0.15"/>
          </lane>
        </center>
        <right>
{chr(10).join(lanes)}
        </right>
      </laneSection>
    </lanes>
  </road>
</OpenDRIVE>
'''


# ---------------------------------------------------------------------- the roads used in this project
def straight_road() -> Road:
    return Road("highway_straight", [Segment("line", 6000.0)])


SBEND_CLOTHOIDS = ((153.7, 30.0), (105.0, 14.0), (98.6, 26.0), (120.8, 39.0))   # (A, L) as printed in 4.2.4.1
SBEND_RADII_M = (787.0, 374.0)
SBEND_ARCS_M = (57.1, 5.1)
SBEND_START_S = 600.0


def sbend_r171() -> Road:
    """R171 Annex 4 4.2.4.1 S-bend; curvature is made exactly continuous (k = 1/R at the arc ends; the
    printed A values give the same radius to within 0.2 %, checked in tests/test_road_and_scenarios.py)."""
    k1, k2 = 1.0 / SBEND_RADII_M[0], 1.0 / SBEND_RADII_M[1]
    (_, l1), (_, l2), (_, l3), (_, l4) = SBEND_CLOTHOIDS
    return Road("sbend_r171", [Segment("line", SBEND_START_S),
                               Segment("spiral", l1, 0.0, k1), Segment("arc", SBEND_ARCS_M[0], k1, k1),
                               Segment("spiral", l2, k1, 0.0),
                               Segment("spiral", l3, 0.0, -k2), Segment("arc", SBEND_ARCS_M[1], -k2, -k2),
                               Segment("spiral", l4, -k2, 0.0),
                               Segment("line", 900.0)])


CURVE_SPIRAL_M = 100.0              # project choice: clothoid length of the constant-radius test curves
CURVE_ARC_M = 450.0                 # project choice: arc length (long enough for a steady state)
CURVE_START_S = 600.0


def curve_road(radius: float) -> Road:
    k = 1.0 / radius
    return Road(f"curve_R{int(radius)}", [Segment("line", CURVE_START_S), Segment("spiral", CURVE_SPIRAL_M, 0.0, k),
                                           Segment("arc", CURVE_ARC_M, k, k), Segment("spiral", CURVE_SPIRAL_M, k, 0.0),
                                           Segment("line", 1500.0)])


CURVE_RADII_M = (250.0, 374.0, 500.0)


def all_roads() -> dict[str, Road]:
    roads = {"highway_straight": straight_road(), "sbend_r171": sbend_r171()}
    for r in CURVE_RADII_M:
        rd = curve_road(r)
        roads[rd.name] = rd
    return roads
