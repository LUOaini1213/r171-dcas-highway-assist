# L2 高速辅助（ACC + 车道居中）按 UN R171 / Euro NCAP 2026 做闭环验证

> 文中的 P5 / P7 指作者的其他公开仓库：P5 = [r152-aeb-scenario-tests](https://github.com/LUOaini1213/r152-aeb-scenario-tests)，P7 = [dms-distraction-warning-tests](https://github.com/LUOaini1213/dms-distraction-warning-tests)。

自己写一个 DCAS 类功能（自适应巡航 + 车道居中 + 模式管理 + 驾驶员投入监测），放进 esmini（OpenSCENARIO / OpenDRIVE）闭环，按 UN R171（DCAS，01 系列）和 Euro NCAP 2026 辅助驾驶相关规程逐条测试。流程是：**官方条款 → 需求（55 条，带 ID 和条款号）→ 参数化场景 → 判定 → 失效边界 → 根因 → 参数权衡 → 改进后再验证**，并做双向追溯。驾驶员监测复用 P7 的 DMS 检测器（原样复制）。

> 本项目在 AI 编码助手（Claude）辅助下完成。所有结果都是玩具模型的仿真数据，结论只在本模型内成立（模型内）；**不声称**任何功能符合 UN R171、Euro NCAP 或其他法规。数字全部来自脚本输出（`results/tables.md`），完整说明见 [report.md](report.md)。

## 结果一览

基线 = 设计初稿；改进 = 基线 + 两处根因修正 + 权衡选出的切入预测时域。DCAS 自身纵向权限 5 m/s²（R171 2.16），不含 AEB。

| 项目 | 基线 | 改进 |
|---|---|---|
| R171 附件 4 基础试验：切入 Type 1/Type 2、切出 TTC 3 s、前车 4 m/s² 减速 | 4/4 安全 | 4/4 安全 |
| Euro NCAP VA（ACC 性能）切入 2 点、切出 2 点、CCRb | 4/5 安全（CCRb 最近跟车距离碰撞 2.1 km/h） | 5/5 安全 |
| Euro NCAP AD（安全后备，评价时含 AEB）切入 2 点、切出 2 点 | 3/4 安全（切出 90/70、TTC 2 s 碰撞 20.7 km/h） | 2/4 安全（另有切入 50/10、TTC −1.5 s 碰撞 14.8 km/h） |
| 切入网格（120 km/h，TTC × 横向速度 × 相对速度，347 个有效点） | 258 安全，73 碰撞 | 242 安全，86 碰撞 |
| 前车急减速网格（34 次） | 12 次安全 | 26 次安全 |
| 切出露出静止车（35 次） | 25 次安全 | 25 次安全 |
| 弯道 51 次：系统横向加速度峰值 / 0.5 s 横向冲击度峰值 | 2.80 m/s² / 3.92 m/s³ 以内（限值 3.3 / 5） | 同左 |
| 开弯道限速仍越线 | 1 次（R250、130 km/h，越线前已发 DCA） | 0 次 |
| 非威胁横向接近（48 例，种子 0）误制动 | 19 次 | 0 次 |
| 驾驶员投入时间线（13 例） | EOR 3.28 s、升级 +2.0 s、DCA +4.0 s、风险减缓停车 +8.0 s（R171 最迟 5 / 3 / 5 / 10 s） | 同左 |
| 需求检查（142 条） | 126 通过、4 不通过、12 信息 | 128 通过、2 不通过、12 信息 |

## 主要发现

1. **切入失效边界**：网格加二分（每对横向速度 × 相对速度二分 4 次）。例如相对速度 50 km/h、平均横向速度 1 m/s 时，基线 TTC* = −0.06 s（换道结束时 TTC 高于它就安全）；横向速度 2 m/s、相对速度 60 km/h 时 TTC* = +1.44 s。R171 Type 2 基础试验（TTC 1.5 s）离边界有余量。不安全的 89 次里，31 次在目标被选中时所需减速度已超过 5 m/s²（属于 AEB 范围），53 次是反应链（感知确认 + 时延 + 执行器滞后）太慢。
2. **根因 1：前车制动时控制律不看前车减速度。** Euro NCAP VA 的 CCRb（55/50 km/h，−4 m/s²，最近跟车距离）基线以 2.1 km/h 碰撞：前 1 s 只按舒适限值 2.5 m/s² 制动，等运动学需求超过阈值才升级。把前车减速度加进需求后，该点 TTC 2.38 s 无碰撞；前车急减速网格安全次数从 12 增到 26。
3. **根因 2：切出露出静止车时被遮挡加确认延迟用掉了时间。** 90/70 km/h、TTC 2 s 时，静止车 1.12 s 后才被确认，此时运动学需求 4.03 m/s²，再加执行器滞后就超出 5 m/s²。只有把权限提到 9 m/s²（相当于 AEB）才能避免，说明这类场景应交给紧急制动（R171 2.16），不应靠 DCAS 调参。
4. **根因 3：弯道限速规划用了控制器自己的减速上限。** 速度跟踪有滞后，R250 弯道 130 km/h 进弯偏快而越线；规划减速度 1.5 → 1.0 m/s² 后不再越线。
5. **参数权衡（规则事先写入代码）**：切入预测时域 0–2.5 s 共 6 档。预测越长，切入网格安全点越多（242 → 265），但误制动从 5/144 升到 76/144。按“误制动 ≤10 %”的约束选中 0 s。代价也写明：Euro NCAP AD 的慢速切入（50/10、TTC −1.5 s）在 DCAS 单独仿真中由安全变为碰撞 14.8 km/h，该点在实车评价中依赖 AEB。

## 怎么做的

- **要求只来自官方文本**：
  - R171 读的是 EUR-Lex 合并文本 OJ L 2025/1899（到 01 系列，2025-09-26 生效）。版本状态按联合国条约库的 6 份保存人通知核对：01 系列之后已生效的修订还有 WP.29/2025/65、2025/143、2025/144（其文本未读到，见“未核实”）。unece.org 对抓取工具返回 403。
  - Euro NCAP 读的是 Assisted Driving v1.2 和 Vehicle Assistance v1.2（2026-07）；Driver Engagement 的数值沿用 P7 的整理。
- **需求**：`dcas/requirements.py`，55 条（R171 43、Euro NCAP 10、项目设计目标 2），其中 5 条写明不在本项目验证的理由；导出为 `requirements.csv`。
- **功能**（`dcas/`）：
  - ACC：定时距跟车、多目标取最严、切入预测、舒适 / 临界两档限值；
  - 车道居中：曲率前馈 + 状态反馈，横向加速度 / 冲击度限幅；弯道限速；
  - 模式管理：OFF / STANDBY / ACTIVE / DRIVER_OVERRIDE / TAKEOVER_REQUEST / MRM，15 个带编号的转换；
  - 驾驶员投入：P7 的 LongGlance / Vats / Drowsiness / Availability 加上 R171 的 EOR / HOR / DCA 升级和锁止。
- **场景与闭环**：9 个参数化 `.xosc`，加 13 个 OpenSCENARIO ParameterValueDistribution 网格（含两个二分点网格，共 775 个用例）。esmini v3.10.2 通过 `esminiLib.dll`（ctypes）无界面运行，步长 20 ms；本车交给 ExternalController，由 Python 闭环控制；其他车辆按 storyboard 运动。
- **判定准则在第一次批量运行前写入 `dcas/evaluate.py`**（碰撞、最小 TTC ≥1 s、500 ms 平均减速度 ≤5.5 m/s²、横向偏移 ≤0.5 m），文件哈希记录在 `results/summary.json`，前 12 位 05c0735f0540。
- **可信度**：
  - 纯 Python 后端复现 esmini 的 storyboard 语义（先用探针测出），78 个抽查用例的状态序列和判定全部一致，最小间距最多差 0.054 m；
  - 20 ms 与 10 ms 步长：13 个官方纵向点判定一致 11 个，不一致的 2 个都贴在阈值上；
  - 官方点各跑 10 个噪声种子；
  - pytest 27 项通过（没有 esmini 时 25 项通过、2 项跳过）。

## 复现

```powershell
# 在本项目根目录下运行；$L 指向 esmini v3.10.2 官方发行包里的 bin\esminiLib.dll
$L = "<esmini 解压目录>\bin\esminiLib.dll"
python -X utf8 -I scripts/check_vendor.py; python -X utf8 -I scripts/make_scenarios.py
python -X utf8 -I scripts/run_all.py --esmini-lib $L --workers 2                      # 约 1 分钟
python -X utf8 -I scripts/boundary_search.py --esmini-lib $L --config baseline --workers 2
python -X utf8 -I scripts/root_cause.py --esmini-lib $L
python -X utf8 -I scripts/tradeoff.py --esmini-lib $L --workers 2                     # 约 3 分钟
python -X utf8 -I scripts/run_all.py --esmini-lib $L --workers 2 --config proposed
python -X utf8 -I scripts/boundary_search.py --esmini-lib $L --config proposed --workers 2
$env:ESMINI_LIB = $L; python -X utf8 -B -I -m pytest -q tests -p no:cacheprovider --junitxml=results/pytest_junit.xml
python -X utf8 -I scripts/make_tables.py; python -X utf8 -I scripts/make_figures.py; python -X utf8 -I scripts/make_traceability.py
```

- 没有 esmini 时把 `--esmini-lib $L` 换成 `--backend python`。
- esmini 打不开含中文的绝对路径，脚本以 `scenarios/` 为工作目录、用相对路径调用它（同 P5）。
- 依赖：Python 3.13、matplotlib（画图）、pytest（测试）。随机数都固定种子，重复运行结果一致。

## 文件

```
dcas/             regulations / requirements / params / road / xosc / scenarios / backends / perception /
                  acc / lcc / boundary / engagement / state_machine / driver / vehicle / closed_loop /
                  evaluate（判定准则）/ verify（需求检查）/ runner
vendor/p7_dms/    从 P7 原样复制的 DMS 检测器（SOURCE.md 记录 SHA-256，scripts/check_vendor.py 核对）
scenarios/        5 个 .xodr（含 R171 附件 4 的 S 弯）、9 个参数化 .xosc、13 个网格文件
scripts/          make_scenarios / run_all / boundary_search / root_cause / tradeoff /
                  make_tables / make_figures / make_traceability / check_vendor
tests/            27 项 pytest（文档字符串里的 REQ: 行把测试挂到需求上）
results/          各套件 CSV、checks*.csv、tables.md、summary*.json、traceability_summary.md、
                  timeseries/、figures/（图 1–5）
requirements.csv  需求注册表导出（55 条）
traceability.csv  条款 → 需求 → 场景 / 测试 → 结果（1637 行，前后向完整）
report.md         完整报告
```

## 局限

- 车辆、执行器、感知都是玩具模型：点质量纵向 + 运动学单轨横向，没有轮胎、坡度、风；感知只有视场、遮挡、确认、时延和噪声。
- DCAS 单独评估，没有 AEB；Euro NCAP AD 安全后备项在实车上是 ACC 与 AEB 一起评价的。
- 驾驶员是脚本，反应时间是假设值；误制动率依赖人为设计的非威胁接近集合，绝对值不能外推。
- 目标车换道用 esmini 的正弦横向轨迹，不是法规写的两段等半径圆弧（时长相同，峰值横向加速度不同）。
- 没有换道 / 系统发起的机动、限速辅助和整车 HMI 声学评价。

## 需要下载才能做的事（本项目未下载）

用真实切入分布加权网格：NGSIM（data.transportation.gov 数据集 8ect-6jqj，“Next Generation Simulation (NGSIM) Vehicle Trajectories and Supporting Data”，11,850,526 行 × 25 列）。导出地址 `https://data.transportation.gov/api/views/8ect-6jqj/rows.csv?accessType=DOWNLOAD`；门户元数据没有给出文件大小，按行数粗估在 GB 量级（未核实）。高速路段子集是附件 `US-101-LosAngeles-CA.zip` 和 `I-80-Emeryville-CA.zip`。

## 未核实

- R171 01 系列之后已生效的 WP.29/2025/65、2025/143、2025/144 的文本（二手来源称后两者增加 DETA 数据交换附件）；02 系列（WP.29/2026/86）据称 2026-06 通过、尚未生效。
- R171 引用的 R79 04 系列风险减缓功能（RMF）的具体要求（减速度、危险报警灯时序）：本项目用设计值。
- R171 附件 4 表格的若干读法：切出试验中 VUT 70 km/h 是否指设定车速、Type 1 切入 “TTC = 0 s” 的含义。
- ISO 15622 / ISO 22179 中的 ACC 舒适限值（没有查阅原文，项目里的加减速度限值都是设计假设）。
- 全部 28 项设计假设（DA-01…DA-28；参数类见 `results/parameters.csv`，DA-26 / DA-27 见 `dcas/boundary.py`、`dcas/driver.py`）。

完整清单见 report.md 第 12 节。
