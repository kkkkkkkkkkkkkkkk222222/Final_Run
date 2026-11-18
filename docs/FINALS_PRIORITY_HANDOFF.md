# 决赛伤员优先与送达确认交接

2026-11-19。决赛保留用户确认的伤员优先策略。本次已在下位接入未确认送达的超时撤离，按上位联调提交 `5c8937f` 完成定向联测。下位实现基于 `fd63ab7`，本次源码版本以本文所属提交为准。

| 项目 | 核对基准 |
| --- | --- |
| 决赛上位 | `danmo-teng/shijue_fangan-finals`，分支 `codex/finals-delivery-confirmation`，提交 `5c8937f559f727b48e233b33b5379b5468d7ebf6` |
| 决赛下位 | `kkkkkkkkkkkkkkkk222222/Final_Run`，分支 `Final_task`，本文所属提交，构建预设 `FinalRun` |
| 优先策略参照 | 初赛取消优先前的 `danmo-teng/shijue_fangan@dc4b9b0a056a94db498c340d609d25492e61d8dd` |
| 指定接口文档 | 决赛上位的 `FINALS_DELIVERY_CONFIRMATION.md` |

上位 `5c8937f` 已包含两种超时退出、重复完成回报去重，以及暂停和保局停车时的送达登记。配套部署使用该提交和本次 FinalRun 固件，RDK 实际启动版本与板端实际身份待现场读取。[上位接口及部署说明](https://github.com/danmo-teng/shijue_fangan-finals/blob/5c8937f559f727b48e233b33b5379b5468d7ebf6/docs/FINALS_DELIVERY_CONFIRMATION.md)

**决赛上位已保留原伤员优先。** 已逐函数对比 `_orange_only_search`、`_choose_search_target`、`_start_zone_observation`、`_choose_cluster_target` 和 `_post_first_preferred_keep_side`，它们与上述初赛参照版本一致。程序沿用的 `green_supply`、`core_black`、`injured_orange` 分别对应普通物资、核心物资、伤员。

- 首件阶段继续寻找并确认送达一件普通物资。确认首件后，伤员优先搜索轮次从 1 开始。
- 第 1～3 轮各自的前 360° 搜索只选伤员。该轮满 360° 后开放普通、核心目标。有符合条件的伤员时继续优先选伤员。第 4 轮起保留“有伤员优先”的选目标规则。
- 120° 安全区边缘观察和聚堆目标选择沿用同一优先策略。已锁定目标按原接近流程处理，最终运输去向由真实复审载荷决定。
- 原分离选侧优先保留可直接运输的单伤员侧。仅有伤员混装侧可尝试时，按原混装候选选侧。另一侧为可运的至少两件材料时，原逻辑会优先该材料组。这一例外也属于本次核对到的旧策略。之后按绿色数量、已锁定侧及原平局顺序选择。
- 快速重发保留 `orange_search_round` 和 `orange_search_turn_deg`。按新局开始时重新建立进度。

这些规则由上位机选目标和选侧实现，下位接收目标、侧别和真实载荷审核。保留优先策略时，沿用现有决赛函数及进度字段。[搜索与轮次](https://github.com/danmo-teng/shijue_fangan-finals/blob/77f0ef14f1d252e4fb141f7e3b20b6cce989dc60/competition_rescue/state_machine.py#L3686) · [分离选侧](https://github.com/danmo-teng/shijue_fangan-finals/blob/77f0ef14f1d252e4fb141f7e3b20b6cce989dc60/competition_rescue/state_machine.py#L3907) · [快速重发进度](https://github.com/danmo-teng/shijue_fangan-finals/blob/77f0ef14f1d252e4fb141f7e3b20b6cce989dc60/competition_rescue/round_resume.py)

**普通分离与取消自动滤除已有对应路径。** 下位 `FinalRun` 定义 `APP_ENABLE_POST_GRAB_FILTER=0`，首件单普通、单伤员以及首件后至少两个普通的原自动抬爪后退入口均被关闭，合法复审接原运输出口。决赛上位普通选侧分离和单侧释放使用 `U=0`，正式流程已停止触发 `U=8200` 特殊分离、门口横移滤除和首件撞堆。下位执行选侧动作后恢复 140° 画面、清掉旧审核，由实际剩余载荷决定后续运输。必要重新合爪沿原状态处理。[下位决赛预设](https://github.com/kkkkkkkkkkkkkkkk222222/Final_Run/blob/fd63ab7e62e97630ee4625facc3ad20e99278e6d/CMakeLists.txt#L55) · [上位普通分离构帧](https://github.com/danmo-teng/shijue_fangan-finals/blob/77f0ef14f1d252e4fb141f7e3b20b6cce989dc60/competition_rescue/state_machine.py#L2400)

**两种超时退出已完成下位配套。**

| 场景 | 上位 `5c8937f` 的行为 | 本次 FinalRun 行为 |
| --- | --- | --- |
| 视觉确认本次进区 | 发 `TASK_COMPLETE / U=0`。收到本任务、本动作的 ACCEPT 与 DONE、开爪且 mode16/17 后，登记一次送达 | 接受 U=0，开爪完成后进入 mode16，并设置首件完成。正式首件仍须经过单普通审核 |
| mode15 原 1 秒观察超时 | 发 `TASK_COMPLETE / U=1`，重复同动作继续 U=1。首件、已送数和伤员搜索轮次沿用此前值 | 接受 U=1，锁存未确认退出，沿原开爪、撤离动作进入 mode16。首件标志和搜索方向沿用此前值 |
| 下位前段累计 4 秒本地超时 | 识别原 ENTER 的匹配 DONE、开爪及 mode16/17，按未确认退出接返程 | 保留原 ENTER 的任务、动作归属，开爪后撤离。首件标志和搜索方向沿用此前值 |
| 视觉确认请求与本地超时先后到达 | 按实际已取得退出动作归属的一方处理 | 原退出原因锁存。晚到确认、同动作改 U 或另起完成动作都不能覆盖已接受原因 |

原 TYPE=0x18、opcode=0x06 和 0x1D/0x1E 配对沿用。A、B 为 0，flags 为 VALID 加阵营，U=0/1 表达本次退出原因。同一动作重发应保持同一个 U。上位 `_register_confirmed_delivery` 已将首件成立限定为已审核载荷恰好一件普通且目的地为物资区。首次确认后才启动伤员优先轮次，随后每次确认送达再推进轮次。尚未确认首件的超时撤离继续找普通物资，已确认首件之后的超时撤离继续原伤员搜索阶段。[上位送达登记](https://github.com/danmo-teng/shijue_fangan-finals/blob/77f0ef14f1d252e4fb141f7e3b20b6cce989dc60/competition_rescue/state_machine.py#L5538) · [下位 U 校验](../Main/Src/Task.c) · [下位退出标记](../Main/Src/Task.c)

本次采用 `APP_FINALS_DELIVERY_CONFIRMATION=1` 在 FinalRun 预设启用新语义。两种超时在首件尚未确认和已经确认时均已定向验证。上位实际构帧经下位解析、任务和机构模拟执行后，上位能识别匹配回报并保持正确进度。重复请求、晚到确认、完成去重和默认预设对照均已通过。[下位实现](../Main/Src/Task.c) · [定向回归](../tools/test_audit_handshake.c)

**单件运输是另一项待两端同步实施的范围。** 上位指定版本的默认 `max_batch_count=3`、材料审核和下位 `task_audit_semantic` 仍允许首件后两三件材料。下位对已判合法的批次会拒绝分离。开局暂存和扫障取货另有非空审核入口。上位单件适配草案需要覆盖这些入口，并以本次用户确认的伤员优先要求约束选目标和选侧。当前“另一侧多件材料优先于伤员混装”的例外，在收敛为单件运输时需按新载荷资格重新核对。此项当前状态为待配套。[上位单件适配草案](https://github.com/danmo-teng/shijue_fangan-finals/blob/77f0ef14f1d252e4fb141f7e3b20b6cce989dc60/docs/FINALS_SINGLE_ITEM_PLAN.md) · [当前下位合法性](https://github.com/kkkkkkkkkkkkkkkk222222/Final_Run/blob/fd63ab7e62e97630ee4625facc3ad20e99278e6d/Main/Src/Task.c#L790)

当前主流程为开局处理 → 搜索目标 → 抓前审核及必要分离 → 合爪后 140° 复审 → 导航到预备点 → 运输复审与对准 → 检查通道并推进 → 按视觉确认或超时原因开爪撤离 → 返回搜索点。合法抓后复审直接接原运输，非法载荷按现有选侧分离后再复审。确认首件前继续找单普通，确认后按伤员优先轮次搜索。每个搜索点累计 540° 无目标时沿原①、③换点流程接续。

本次软件配套和必要联测已完成，现场烧录、板端身份读取及实物送达效果待验证。单件运输仍按上一段所列范围待两端统一实施。
