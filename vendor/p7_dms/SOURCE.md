# 来源说明（vendor/p7_dms）

这 5 个文件从 P7 = 公开仓库 [dms-distraction-warning-tests](https://github.com/LUOaini1213/dms-distraction-warning-tests) 的 `dms/` 目录（提交 `39a022d51645bce9ea4824ac65bc38556b4c873e`）原样复制，未做任何修改：

| 文件 | 作用 | SHA-256 |
|---|---|---|
| `__init__.py` | 包说明 | 6d21590fa2dd5315949bf250850d21eebe3bdc91d3576e65ae86340715da13d6 |
| `labels.py` | 注视区域标签 | 28d91b485bc5292769ecd06c171394c52407948b4350333f5f8a1b4895d9c8e4 |
| `regulations.py` | ADDW / DDAW / Euro NCAP DE 等数值及条款 | 0425973aeec9dbd1e524cc1d1e947b20ba448b2dd01c9a2b2110529136198504 |
| `config.py` | DMS 参数（本项目只改实例的 dt 与中断容差，不改文件） | ac055e13517fee219f8e4544375642b9a4329d575c9aa7f5ba1b3fa333b1cf27 |
| `detectors.py` | LongGlance / Vats / Drowsiness / Availability 逐帧检测器 | 3ce216b8c53c91144d379430409663992a9adb62f50bec05891b1d39a5f3df0b |

- 本项目（r171-dcas-highway-assist）只用其中的检测器；R171 的报警升级、锁止、DMS 不可用处理写在 `dcas/engagement.py`。
- `scripts/check_vendor.py` 核对上表哈希；用 `--p7 <P7 仓库的克隆目录>` 时还会逐字节比对。
- P7 的 `warning.py`（ADDW 报警状态机）、`system.py`、场景与试验代码没有复制。
