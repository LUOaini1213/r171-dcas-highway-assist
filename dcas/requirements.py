"""Requirement registry: clause -> requirement -> test (traceability.csv is generated from it).

source / clause   official document and clause number (dcas/regulations.py lists the documents read)
tests             selectors resolved by scripts/make_traceability.py:
                    "suite:<suite>"          every case of a result suite (results/<suite>.csv)
                    "case:<id>[,<id>]"       named cases
                    "check:<REQ>"            rows of results/checks.csv produced by dcas/verify.py for this ID
                    "unit"                   pytest functions whose docstring has a "REQ: <ID>" line
na                if not verified here: why, and where it would be verified
Kinds: 功能 / 性能 / HMI / 试验条件 / 设计目标.  IDs: R171-*, NCAP-*, PRJ-*.
"""
from __future__ import annotations

from dataclasses import dataclass, field

R171 = "UN R171 01 系列（OJ L 2025/1899）"
AD = "Euro NCAP AD v1.2（2026-07）"
VA = "Euro NCAP VA v1.2（2026-07）"
PRJ = "本项目设计目标"


@dataclass(frozen=True)
class Req:
    rid: str
    source: str
    clause: str
    text: str
    kind: str
    tests: list = field(default_factory=list)
    na: str = ""


REQS: list[Req] = [
    # ------------------------------------------------------------------ general
    Req("R171-GEN-01", R171, "5.1.1, 5.5.4.2", "系统应确保驾驶员保持对驾驶任务的投入（监测视觉与动作脱离并报警）", "功能",
        ["check:R171-GEN-01"]),
    Req("R171-GEN-02", R171, "5.1.4, 5.5.3.4", "驾驶员可随时安全地超越或关闭系统", "功能", ["check:R171-GEN-02"]),
    Req("R171-GEN-03", R171, "5.1.5", "装备 DCAS 的车辆至少装有 AEBS，以及 LDWS 或 LDPS", "功能",
        na="整车配置要求，仿真不建模；AEB 的法规场景测试见 P5（R152）"),
    Req("R171-GEN-04", R171, "5.2.1", "DCAS 处于 active 时不得关闭或抑制已激活 AEBS 的纵向功能", "功能",
        na="本项目没有 AEB 模型（DCAS 纵向权限止于 5 m/s²，超出部分只做分类，见 R171-LON-06）；需在整车架构与 HIL 中验证"),
    # ------------------------------------------------------------------ longitudinal
    Req("R171-LON-01", R171, "5.3.2.2, 5.3.7.2.5.1 (b); 附件 4 4.2.5.2.6", "相邻车道车辆切入：避免碰撞（附件 4 Type 1/Type 2 基础试验及扩展参数）", "性能",
        ["suite:cutin_official", "suite:cutin_grid", "suite:cutin_refine"]),
    Req("R171-LON-02", R171, "5.3.7.2.5.1 (a); 附件 4 4.2.5.2.5", "前车切出后露出静止车辆：避免碰撞（TTC 3 s 基础试验及扩展）", "性能",
        ["suite:cutout"]),
    Req("R171-LON-03", R171, "5.3.7.2.5.1 (c); 附件 4 4.2.5.2.4", "前车减速（基础试验 50 km/h、4 m/s²，扩展：更大减速度、不同车速）：避免碰撞", "性能",
        ["suite:leadbrake"]),
    Req("R171-LON-04", R171, "5.3.6.3.1, 5.3.7.2.5.2", "加减速度对驾驶员和周围交通可控；跟车距离被打断后不急刹地恢复（除非需要紧急制动）", "性能",
        ["check:R171-LON-04"]),
    Req("R171-LON-05", R171, "5.3.2.3, 5.3.7.5.1.1", "保持适当跟车距离；持续显示时距设置，首次激活且时距 <2 s 时提示", "功能/HMI",
        ["check:R171-LON-05"]),
    Req("R171-LON-06", R171, "2.16", "纵向权限：5 m/s² 以内由 DCAS 处理；需要 >5 m/s² 的情形属“即将碰撞”，应交给紧急系统", "设计目标",
        ["check:R171-LON-06", "unit"]),
    # ------------------------------------------------------------------ lateral
    Req("R171-LAT-01", R171, "5.3.7.1.1, 5.3.7.1.2", "在申报的最大横向加速度（2.5 m/s²）以内，不得无意越过车道线", "性能",
        ["check:R171-LAT-01"]),
    Req("R171-LAT-02", R171, "5.3.7.1.2", "系统产生的横向加速度 ≤ 申报值 + 0.3 m/s²（且 ≤3 m/s²）；≤2 s 的时段内 ≤3.3 m/s²", "性能",
        ["suite:curve", "check:R171-LAT-02", "unit"]),
    Req("R171-LAT-03", R171, "5.3.7.1.2.1", "系统产生的横向冲击度 0.5 s 滑动平均 ≤5 m/s³", "性能", ["check:R171-LAT-03"]),
    Req("R171-LAT-04", R171, "5.3.7.1.1.1; 附件 4 4.2.5.1.1.1.2", "系统应能按道路曲率调整车速以留在车道内", "功能", ["check:R171-LAT-04"]),
    Req("R171-LAT-05", R171, "5.3.7.1.4", "到达边界且前轮开始越线时，继续尽力提供转向辅助，并给出光学 + 声/触觉警告", "功能/HMI",
        ["check:R171-LAT-05"]),
    # ------------------------------------------------------------------ boundaries
    Req("R171-BND-01", R171, "5.3.5.1", "检测到超出系统边界：转入 stand-by、立即通知驾驶员、以可控方式终止辅助", "功能",
        ["check:R171-BND-01"]),
    Req("R171-BND-02", R171, "5.3.5.5", "接近系统边界时提前足够时间告知驾驶员", "HMI", ["check:R171-BND-02"]),
    Req("R171-BND-03", R171, "5.3.5.1.1", "避免 stand-by 与 active 之间的快速来回切换", "功能", ["check:R171-BND-03"]),
    # ------------------------------------------------------------------ driver engagement
    Req("R171-ENG-01", R171, "5.5.4.2.4, 5.5.4.2.6.1.1", "车速 >10 km/h：脱手 >5 s 时最迟发出 HOR；视线在相关区域时可推迟 ≤5 s", "功能",
        ["check:R171-ENG-01"]),
    Req("R171-ENG-02", R171, "5.5.4.2.6.1.2", "HOR 发出后最迟 10 s 升级，升级后的 HOR 含声和/或触觉", "功能", ["check:R171-ENG-02"]),
    Req("R171-ENG-03", R171, "5.5.4.2.5.1, 5.5.4.2.6.2.1", "车速 >10 km/h：视觉脱离 5 s 时最迟发出 EOR（视觉 + 另一种方式）", "功能",
        ["check:R171-ENG-03"]),
    Req("R171-ENG-04", R171, "5.5.4.2.5.2", "仪表板不属于驾驶任务相关区域（注视仪表板计为视觉脱离）；后视镜属于相关区域", "功能",
        ["check:R171-ENG-04", "unit"]),
    Req("R171-ENG-05", R171, "5.5.4.2.5.2.1", "视线回到相关区域至少 200 ms 才算重新投入", "功能", ["check:R171-ENG-05"]),
    Req("R171-ENG-06", R171, "5.5.4.2.6.2.2", "EOR 确认后 2 s 内再次脱离 ≥1 s：立即发出 EOR", "功能", ["check:R171-ENG-06"]),
    Req("R171-ENG-07", R171, "5.5.4.2.5.3", "对多次连续短时视线偏离要有对策（如立即 EOR）", "功能", ["check:R171-ENG-07"]),
    Req("R171-ENG-08", R171, "5.5.4.2.6.2.3", "EOR 后持续脱离：最迟 3 s 升级，升级后含声和/或触觉", "功能", ["check:R171-ENG-08"]),
    Req("R171-ENG-09", R171, "5.5.4.2.6.3.1, 5.5.4.2.3.3.1", "EOR 升级后最迟 5 s 发出 DCA（视觉 + 另一种方式）", "功能", ["check:R171-ENG-09"]),
    Req("R171-ENG-10", R171, "5.5.4.2.6.4.1, 5.3.7.3.1", "首次升级请求或 DCA 后最迟 10 s 启动驾驶员不可用响应，以风险减缓功能安全停车", "功能",
        ["check:R171-ENG-10"]),
    Req("R171-ENG-11", R171, "5.5.4.2.3.3.2", "驾驶员接管（无持续横向辅助）即视为确认 DCA", "功能", ["check:R171-ENG-11"]),
    Req("R171-ENG-12", R171, "5.5.4.2.8.1, 5.5.4.2.8.2", "投入不足（1 次不可用响应 / 2 次 DCA / 30 min 内 3 次升级）时禁用系统 ≥30 min", "功能",
        ["check:R171-ENG-12"]),
    Req("R171-ENG-13", R171, "5.5.4.2.1.2", "视觉脱离判定暂时不可用时，系统不得使车辆离开本车道", "功能",
        na="本系统没有换道或其他会离开本车道的机动功能（R171-MAN-01），该条通过设计范围满足，无需仿真"),
    Req("R171-ENG-14", R171, "5.5.3.2.3 (b)", "只有能监测驾驶员脱离时才允许进入 active", "功能", ["check:R171-ENG-14"]),
    # ------------------------------------------------------------------ HMI / activation / override
    Req("R171-HMI-01", R171, "5.5.3.1, 5.5.3.2.2", "每次上电默认 off；off→on 只能由驾驶员有意操作", "HMI", ["check:R171-HMI-01", "unit"]),
    Req("R171-HMI-02", R171, "5.5.3.2.3 (a)(c)(d)", "激活前提：系好安全带、无失效、未超出系统边界", "功能", ["check:R171-HMI-02"]),
    Req("R171-HMI-03", R171, "5.5.4.1.4", "多条提示同时出现时按紧迫度排序，安全相关提示优先", "HMI", ["unit"]),
    Req("R171-OVR-01", R171, "5.5.3.4.1.1, 5.5.3.4.1.1.1", "驾驶员制动产生更大减速度时中止纵向辅助，且不经驾驶员另行操作不得恢复", "功能",
        ["check:R171-OVR-01"]),
    Req("R171-OVR-02", R171, "5.5.3.4.1.3", "驾驶员踩加速踏板超越纵向控制；松开后按当前最高车速恢复", "功能", ["check:R171-OVR-02"]),
    Req("R171-OVR-03", R171, "5.5.3.4.1.4", "转向输入超越横向控制，所需转向操纵力 ≤50 N", "功能", ["check:R171-OVR-03", "unit"]),
    Req("R171-OVR-04", R171, "5.5.3.3.1", "驾驶员可随时把系统切换到 off", "功能", ["check:R171-OVR-04"]),
    Req("R171-FLT-01", R171, "5.4.2.1", "影响整个系统的失效：终止辅助后切换到 off，并给出光学失效警告", "功能", ["check:R171-FLT-01"]),
    Req("R171-MAN-01", R171, "5.3.7.2, 6.2", "驾驶员确认 / 系统发起的机动（换道等）要求", "功能",
        na="本项目的功能范围不含换道和系统发起的机动；如扩展该功能，需按 5.3.7.2.4（含 EOR 后 7 s 内不得发起）补测"),
    Req("R171-SPD-01", R171, "5.3.7.4", "限速辅助：识别并持续显示道路限速，当前最高车速不超过限速", "功能",
        na="没有交通标志 / 地图限速模型；巡航设定速度视为当前最高车速。需在带限速数据的场景中验证"),
    Req("R171-VAL-01", R171, "附件 3 附录 4；附件 4 3.1.6.2", "申报的能力须在 ≥90 % 的对应试验中表现出来；基础试验至少跑 2 次", "试验条件",
        ["check:R171-VAL-01"]),
    # ------------------------------------------------------------------ Euro NCAP
    Req("NCAP-AD-01", AD, "2.3.2.1", "DSM 不能工作时：不能进入辅助模式；运行中 ≤10 s 退出", "功能", ["check:NCAP-AD-01"]),
    Req("NCAP-AD-02", AD, "2.3.2.2", "辅助模式下长时分心报警阈值放宽不超过 150 %（3 s 基准 → ≤4.5 s）", "功能",
        ["check:NCAP-AD-02", "unit"]),
    Req("NCAP-AD-03", AD, "2.3.2.3（加分项）", "30 min 内重复 [3] 次分心后，以可控方式锁止辅助模式", "功能", ["check:NCAP-AD-03"]),
    Req("NCAP-AD-04", AD, "4.2.1, 4.2.2", "微睡眠 / 睡眠：视觉 + 声或触觉警告，并加大 ACC 时距", "功能", ["check:NCAP-AD-04"]),
    Req("NCAP-AD-05", AD, "4.2.3", "驾驶员无响应：紧急功能保持转向并把车辆停住", "功能", ["check:NCAP-AD-05"]),
    Req("NCAP-AD-06", AD, "4.3.1", "安全后备：切入 TTC −1.5 s（50/10）、0.5 s（120/70），切出 TTC 2.0 s（70/50、90/70）", "性能",
        ["case:OFF-CI-NCAPAD-1,OFF-CI-NCAPAD-2,OFF-CO-NCAPAD-1,OFF-CO-NCAPAD-2"]),
    Req("NCAP-VA-01", VA, "2（ACC 性能）", "ACC 只在减速度 ≤5 m/s²（500 ms 滑动平均 +10 %）范围内评价", "性能", ["check:NCAP-VA-01"]),
    Req("NCAP-VA-02", VA, "2.1.4", "ACC 切入：TTC 0.0 s（50/10）、1.5 s（120/70）", "性能", ["case:OFF-CI-NCAPVA-1,OFF-CI-NCAPVA-2"]),
    Req("NCAP-VA-03", VA, "2.1.5", "ACC 切出：TTC 3.0 s（70/50、90/70）", "性能", ["case:OFF-CO-NCAPVA-1,OFF-CO-NCAPVA-2"]),
    Req("NCAP-VA-04", VA, "2.1.3", "ACC CCRb：55/50 km/h，前车 −4 m/s²，最近跟车距离", "性能", ["case:OFF-LB-NCAPVA"]),
    # ------------------------------------------------------------------ project design targets
    Req("PRJ-01", PRJ, "evaluate.py", "安全余量：路径内目标的最小 TTC ≥1.0 s（判定准则，事先写入代码）", "设计目标", ["check:PRJ-01"]),
    Req("PRJ-02", PRJ, "scripts/tradeoff.py", "非威胁横向接近（不进入本车道）的误制动率 ≤10 %（权衡约束，事先写入代码）", "设计目标",
        ["suite:latprobe", "suite:tradeoff"]),
]


def by_id() -> dict[str, Req]:
    return {r.rid: r for r in REQS}
