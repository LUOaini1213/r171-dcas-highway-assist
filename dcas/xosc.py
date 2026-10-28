"""OpenSCENARIO 1.2 templates of the scenario families (written to scenarios/ by scripts/make_scenarios.py).

Every family is a parameterised .xosc; concrete test cases are OpenSCENARIO ParameterValueDistribution files
(scenarios/*_grid.xosc).  The Ego is always handed to esmini's ExternalController (ExtCtrl = true) and moved
by the Python closed loop; all other vehicles follow the storyboard.

Families
  CutIn      target in lane TgtLane changes into the Ego lane (-2) at LcStart, sinusoidal, duration LcTime
  CutOut     lead in the Ego lane changes to lane -1 at CoStart (CoTime), revealing a stationary vehicle Stat
  LeadBrake  lead in the Ego lane brakes at DecelStart with LeadDecel (linear rate) to standstill
  LatProbe   adjacent vehicle moves towards the Ego lane by ProbeOffset (partial lane change, same lane),
             holds ProbeHold, returns: a non-threatening manoeuvre for the false-braking study
  Highway    lead at constant speed (driver-engagement and functional cases)
  Curve_*    Ego alone on a curved road (lane-centring cases)
"""
from __future__ import annotations

from xml.sax.saxutils import escape

TARGET_BB = dict(cx=1.3, length=4.0, width=1.8)
EGO_BB = dict(cx=1.4, length=4.6, width=1.85)


def _vehicle(name: str, model: str, bb: dict, external: bool = False) -> str:
    ctrl = ""
    if external:
        ctrl = """
      <ObjectController>
        <Controller name="DCAS_ExternalController">
          <Properties>
            <Property name="esminiController" value="ExternalController"/>
          </Properties>
        </Controller>
      </ObjectController>"""
    return f"""    <ScenarioObject name="{name}">
      <Vehicle name="{model}" vehicleCategory="car">
        <ParameterDeclarations/>
        <Performance maxSpeed="70.0" maxAcceleration="10.0" maxDeceleration="10.0"/>
        <BoundingBox>
          <Center x="{bb['cx']}" y="0.0" z="0.75"/>
          <Dimensions width="{bb['width']}" length="{bb['length']}" height="1.5"/>
        </BoundingBox>
        <Axles>
          <FrontAxle maxSteering="0.5" wheelDiameter="0.65" trackWidth="1.6" positionX="2.8" positionZ="0.325"/>
          <RearAxle maxSteering="0.0" wheelDiameter="0.65" trackWidth="1.6" positionX="0.0" positionZ="0.325"/>
        </Axles>
        <Properties/>
      </Vehicle>{ctrl}
    </ScenarioObject>"""


def _init(name: str, lane: str, s: str, speed: str, ext: bool = False) -> str:
    extra = """
          <PrivateAction>
            <ControllerAction>
              <ActivateControllerAction longitudinal="$ExtCtrl" lateral="$ExtCtrl"/>
            </ControllerAction>
          </PrivateAction>""" if ext else ""
    return f"""        <Private entityRef="{name}">
          <PrivateAction>
            <TeleportAction>
              <Position>
                <LanePosition roadId="1" laneId="{lane}" offset="0.0" s="{s}"/>
              </Position>
            </TeleportAction>
          </PrivateAction>
          <PrivateAction>
            <LongitudinalAction>
              <SpeedAction>
                <SpeedActionDynamics dynamicsShape="step" value="0.0" dynamicsDimension="time"/>
                <SpeedActionTarget>
                  <AbsoluteTargetSpeed value="{speed}"/>
                </SpeedActionTarget>
              </SpeedAction>
            </LongitudinalAction>
          </PrivateAction>{extra}
        </Private>"""


def _time_trigger(name: str, t: str) -> str:
    return f"""              <StartTrigger>
                <ConditionGroup>
                  <Condition name="{name}" delay="0" conditionEdge="none">
                    <ByValueCondition>
                      <SimulationTimeCondition value="{t}" rule="greaterOrEqual"/>
                    </ByValueCondition>
                  </Condition>
                </ConditionGroup>
              </StartTrigger>"""


def _lane_change_event(ev: str, target_lane_xml: str, duration: str, t: str, offset: str | None = None) -> str:
    off = f' targetLaneOffset="{offset}"' if offset is not None else ""
    return f"""            <Event name="{ev}" priority="override" maximumExecutionCount="1">
              <Action name="{ev}Action">
                <PrivateAction>
                  <LateralAction>
                    <LaneChangeAction{off}>
                      <LaneChangeActionDynamics dynamicsShape="sinusoidal" value="{duration}" dynamicsDimension="time"/>
                      <LaneChangeTarget>
                        {target_lane_xml}
                      </LaneChangeTarget>
                    </LaneChangeAction>
                  </LateralAction>
                </PrivateAction>
              </Action>
{_time_trigger(ev + "Start", t)}
            </Event>"""


def _brake_event(ev: str, rate: str, t: str) -> str:
    return f"""            <Event name="{ev}" priority="override" maximumExecutionCount="1">
              <Action name="{ev}Action">
                <PrivateAction>
                  <LongitudinalAction>
                    <SpeedAction>
                      <SpeedActionDynamics dynamicsShape="linear" value="{rate}" dynamicsDimension="rate"/>
                      <SpeedActionTarget>
                        <AbsoluteTargetSpeed value="0.0"/>
                      </SpeedActionTarget>
                    </SpeedAction>
                  </LongitudinalAction>
                </PrivateAction>
              </Action>
{_time_trigger(ev + "Start", t)}
            </Event>"""


def _maneuver_group(actor: str, events: list[str]) -> str:
    return f"""        <ManeuverGroup name="{actor}Group" maximumExecutionCount="1">
          <Actors selectTriggeringEntities="false">
            <EntityRef entityRef="{actor}"/>
          </Actors>
          <Maneuver name="{actor}Maneuver">
{chr(10).join(events)}
          </Maneuver>
        </ManeuverGroup>"""


def _document(description: str, comment: str, params: list[tuple[str, str, str]], road: str, entities: list[str],
              inits: list[str], groups: list[str]) -> str:
    decl = "\n".join(f'    <ParameterDeclaration name="{n}" parameterType="{t}" value="{v}"/>' for n, t, v in params)
    story = ""
    if groups:
        story = f"""
    <Story name="Story">
      <Act name="Act">
{chr(10).join(groups)}
        <StartTrigger>
          <ConditionGroup>
            <Condition name="ActStart" delay="0" conditionEdge="none">
              <ByValueCondition>
                <SimulationTimeCondition value="0.0" rule="greaterOrEqual"/>
              </ByValueCondition>
            </Condition>
          </ConditionGroup>
        </StartTrigger>
      </Act>
    </Story>"""
    else:
        story = ""          # no storyboard events (Ego only, or a lead at constant speed)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!--
{escape(comment)}
Generated by scripts/make_scenarios.py from dcas/xosc.py (do not edit by hand).  Speeds m/s, distances m, times s.
-->
<OpenSCENARIO>
  <FileHeader revMajor="1" revMinor="2" date="2026-10-28T00:00:00" description="{escape(description)}" author="Luo Wenjie (AI-assisted)"/>
  <ParameterDeclarations>
{decl}
  </ParameterDeclarations>
  <CatalogLocations/>
  <RoadNetwork>
    <LogicFile filepath="{road}"/>
  </RoadNetwork>
  <Entities>
{chr(10).join(entities)}
  </Entities>
  <Storyboard>
    <Init>
      <Actions>
{chr(10).join(inits)}
      </Actions>
    </Init>{story}
    <StopTrigger>
      <ConditionGroup>
        <Condition name="EndTime" delay="0" conditionEdge="none">
          <ByValueCondition>
            <SimulationTimeCondition value="$SimEndTime" rule="greaterThan"/>
          </ByValueCondition>
        </Condition>
      </ConditionGroup>
    </StopTrigger>
  </Storyboard>
</OpenSCENARIO>
"""


COMMON = [("EgoSpeed", "double", "33.333333"), ("EgoStartS", "double", "100.0"), ("SimEndTime", "double", "20.0"),
          ("ExtCtrl", "boolean", "false"), ("CaseId", "string", "default")]
EGO_LANE_STR = "-2"


def family_cutin() -> str:
    params = COMMON + [("TgtSpeed", "double", "19.444444"), ("TgtStartS", "double", "160.0"), ("TgtLane", "int", "-3"),
                       ("LcStart", "double", "4.0"), ("LcTime", "double", "3.086"),
                       ]
    ev = _lane_change_event("CutIn", f'<AbsoluteTargetLane value="{EGO_LANE_STR}"/>', "$LcTime", "$LcStart")
    return _document("Cut-in from the adjacent lane, parameterised",
                     "CutIn: a target in lane TgtLane performs a full lane change (3.5 m) into the Ego lane (-2).\n"
                     "R171 Annex 4 4.2.5.2.6 (01 series) / Euro NCAP VA v1.2 2.1.4: indicated TTC = TTC when the target has\n"
                     "finished the lane change (rear centre in the middle of the VUT lane).  The grid file sets TgtStartS and\n"
                     "LcStart so that this TTC equals the grid value if the Ego kept its initial speed (open-loop definition).\n"
                     "Project choice: sinusoidal lateral profile (esmini LaneChangeAction) instead of the two constant-radius arcs\n"
                     "of the regulation; the lane-change duration is matched, the peak lateral acceleration is not.",
                     params, "highway_straight.xodr",
                     [_vehicle("Ego", "VUT", EGO_BB, True), _vehicle("Target", "GVT", TARGET_BB)],
                     [_init("Ego", EGO_LANE_STR, "$EgoStartS", "$EgoSpeed", True), _init("Target", "$TgtLane", "$TgtStartS", "$TgtSpeed")],
                     [_maneuver_group("Target", [ev])])


def family_cutout() -> str:
    params = COMMON + [("LeadSpeed", "double", "13.888889"), ("LeadStartS", "double", "120.0"), ("StatS", "double", "300.0"),
                       ("CoStart", "double", "4.0"), ("CoTime", "double", "3.168")]
    ev = _lane_change_event("CutOut", '<AbsoluteTargetLane value="-1"/>', "$CoTime", "$CoStart")
    return _document("Cut-out of the lead vehicle revealing a stationary vehicle, parameterised",
                     "CutOut: the Ego follows Lead in lane -2; Lead changes to lane -1 at CoStart to avoid the stationary\n"
                     "vehicle Stat.  R171 Annex 4 4.2.5.2.5 / Euro NCAP VA 2.1.5: indicated TTC = TTC of the lead vehicle to the\n"
                     "stationary target when the lead starts the lane change.  Lane-change duration = lane change length / lead speed.",
                     params, "highway_straight.xodr",
                     [_vehicle("Ego", "VUT", EGO_BB, True), _vehicle("Lead", "SOV", TARGET_BB), _vehicle("Stat", "GVT", TARGET_BB)],
                     [_init("Ego", EGO_LANE_STR, "$EgoStartS", "$EgoSpeed", True), _init("Lead", EGO_LANE_STR, "$LeadStartS", "$LeadSpeed"),
                      _init("Stat", EGO_LANE_STR, "$StatS", "0.0")],
                     [_maneuver_group("Lead", [ev])])


def family_leadbrake() -> str:
    params = COMMON + [("LeadSpeed", "double", "13.888889"), ("LeadStartS", "double", "130.0"), ("LeadDecel", "double", "4.0"),
                       ("DecelStart", "double", "4.0")]
    ev = _brake_event("LeadBrake", "$LeadDecel", "$DecelStart")
    return _document("Decelerating lead vehicle, parameterised",
                     "LeadBrake: the Ego follows Lead at its steady-state time gap; Lead brakes with LeadDecel to standstill.\n"
                     "R171 Annex 4 4.2.5.2.4: 50 km/h, steady-state following, target decelerating up to 4 m/s2 (base test);\n"
                     "extended tests: larger deceleration, different speeds.  Euro NCAP VA 2.1.3 CCRb: 55/50 km/h, -4 m/s2.\n"
                     "Project choice: the deceleration is a step (linear rate from DecelStart).",
                     params, "highway_straight.xodr",
                     [_vehicle("Ego", "VUT", EGO_BB, True), _vehicle("Lead", "GVT", TARGET_BB)],
                     [_init("Ego", EGO_LANE_STR, "$EgoStartS", "$EgoSpeed", True), _init("Lead", EGO_LANE_STR, "$LeadStartS", "$LeadSpeed")],
                     [_maneuver_group("Lead", [ev])])


def family_latprobe() -> str:
    params = COMMON + [("AdjSpeed", "double", "25.0"), ("AdjStartS", "double", "150.0"), ("AdjLane", "int", "-3"),
                       ("ProbeOffset", "double", "0.8"), ("ProbeStart", "double", "4.0"), ("ProbeTime", "double", "2.0"),
                       ("ProbeBackStart", "double", "7.0")]
    out = _lane_change_event("ProbeOut", '<RelativeTargetLane entityRef="Adj" value="0"/>', "$ProbeTime", "$ProbeStart", "$ProbeOffset")
    back = _lane_change_event("ProbeBack", '<RelativeTargetLane entityRef="Adj" value="0"/>', "$ProbeTime", "$ProbeBackStart", "0.0")
    return _document("Non-threatening lateral approach of an adjacent vehicle (false-braking study), parameterised",
                     "LatProbe: a vehicle in lane AdjLane moves towards the Ego lane by ProbeOffset (positive = left) inside its\n"
                     "own lane (LaneChangeAction to the same lane with targetLaneOffset), then returns at ProbeBackStart.\n"
                     "It never enters the Ego lane by more than ProbeOffset - 0.85 m; any Ego braking for it is a false activation.",
                     params, "highway_straight.xodr",
                     [_vehicle("Ego", "VUT", EGO_BB, True), _vehicle("Adj", "GVT", TARGET_BB)],
                     [_init("Ego", EGO_LANE_STR, "$EgoStartS", "$EgoSpeed", True), _init("Adj", "$AdjLane", "$AdjStartS", "$AdjSpeed")],
                     [_maneuver_group("Adj", [out, back])])


def family_highway() -> str:
    params = COMMON + [("LeadSpeed", "double", "30.0"), ("LeadStartS", "double", "1100.0")]
    return _document("Straight highway with a lead vehicle at constant speed",
                     "Highway: driver-engagement timelines and functional cases (override, boundaries, failures).\n"
                     "Lead keeps LeadSpeed in the Ego lane; place it far ahead (LeadStartS) when not wanted.",
                     params, "highway_straight.xodr",
                     [_vehicle("Ego", "VUT", EGO_BB, True), _vehicle("Lead", "GVT", TARGET_BB)],
                     [_init("Ego", EGO_LANE_STR, "$EgoStartS", "$EgoSpeed", True), _init("Lead", EGO_LANE_STR, "$LeadStartS", "$LeadSpeed")],
                     [])


def family_curve(road_name: str, comment: str) -> str:
    return _document(f"Lane centring on {road_name}", comment, COMMON, f"{road_name}.xodr",
                     [_vehicle("Ego", "VUT", EGO_BB, True)], [_init("Ego", EGO_LANE_STR, "$EgoStartS", "$EgoSpeed", True)], [])
