# 决赛伤员优先与送达确认交接

2026-11-19。用户本轮明确要求决赛保留初赛取消优先前的伤员优先逻辑。决赛物块更易分离，继续按真实载荷选侧、分离和复审。本交接以用户指定的上位 `77f0ef1` 和本地下位 `fd63ab7` 核对源码，供决赛两端后续配套使用。

| 项目 | 核对基准 |
| --- | --- |
| 决赛上位 | `danmo-teng/shijue_fangan-finals@77f0ef14f1d252e4fb141f7e3b20b6cce989dc60` |
| 决赛下位 | `kkkkkkkkkkkkkkkk222222/Final_Run`，分支 `Final_task`，源码 `fd63ab7e62e97630ee4625facc3ad20e99278e6d`，构建预设 `FinalRun` |
| 优先策略参照 | 初赛取消优先前的 `danmo-teng/shijue_fangan@dc4b9b0a056a94db498c340d609d25492e61d8dd` |
| 指定接口文档 | 决赛上位的 `FINALS_DELIVERY_CONFIRMATION.md` |

上位远端 `main@a90c8f3` 相比指定提交仅追记两份文档。RDK 实际启动的源码版本与板端实际固件身份，待配套部署时读取并记录。[用户指定的送达确认文档](https://github.com/danmo-teng/shijue_fangan-finals/blob/77f0ef14f1d252e4fb141f7e3b20b6cce989dc60/docs/FINALS_DELIVERY_CONFIRMATION.md)

**决赛上位已保留原伤员优先。** 已逐函数对比 `_orange_only_search`、`_choose_search_target`、`_start_zone_observation`、`_choose_cluster_target` 和 `_post_first_preferred_keep_side`，它们与上述初赛参照版本一致。程序沿用的 `green_supply`、`core_black`、`injured_orange` 分别对应普通物资、核心物资、伤员。

- 首件阶段继续寻找并确认送达一件普通物资。确认首件后，伤员优先搜索轮次从 1 开始。
- 第 1～3 轮各自的前 360° 搜索只选伤员。该轮满 360° 后开放普通、核心目标。有符合条件的伤员时继续优先选伤员。第 4 轮起保留“有伤员优先”的选目标规则。
- 120° 安全区边缘观察和聚堆目标选择沿用同一优先策略。已锁定目标按原接近流程处理，最终运输去向由真实复审载荷决定。
- 原分离选侧优先保留可直接运输的单伤员侧。仅有伤员混装侧可尝试时，按原混装候选选侧。另一侧为可运的至少两件材料时，原逻辑会优先该材料组。这一例外也属于本次核对到的旧策略。之后按绿色数量、已锁定侧及原平局顺序选择。
- 快速重发保留 `orange_search_round` 和 `orange_search_turn_deg`。按新局开始时重新建立进度。

这些规则由上位机选目标和选侧实现，下位接收目标、侧别和真实载荷审核。保留优先策略时，沿用现有决赛函数及进度字段。[搜索与轮次](https://github.com/danmo-teng/shijue_fangan-finals/blob/77f0ef14f1d252e4fb141f7e3b20b6cce989dc60/competition_rescue/state_machine.py#L3686) · [分离选侧](https://github.com/danmo-teng/shijue_fangan-finals/blob/77f0ef14f1d252e4fb141f7e3b20b6cce989dc60/competition_rescue/state_machine.py#L3907) · [快速重发进度](https://github.com/danmo-teng/shijue_fangan-finals/blob/77f0ef14f1d252e4fb141f7e3b20b6cce989dc60/competition_rescue/round_resume.py)

**普通分离与取消自动滤除已有对应路径。** 下位 `FinalRun` 定义 `APP_ENABLE_POST_GRAB_FILTER=0`，首件单普通、单伤员以及首件后至少两个普通的原自动抬爪后退入口均被关闭，合法复审接原运输出口。决赛上位普通选侧分离和单侧释放使用 `U=0`，正式流程已停止触发 `U=8200` 特殊分离、门口横移滤除和首件撞堆。下位执行选侧动作后恢复 140° 画面、清掉旧审核，由实际剩余载荷决定后续运输。必要重新合爪沿原状态处理。[下位决赛预设](https://github.com/kkkkkkkkkkkkkkkk222222/Final_Run/blob/fd63ab7e62e97630ee4625facc3ad20e99278e6d/CMakeLists.txt#L55) · [上位普通分离构帧](https://github.com/danmo-teng/shijue_fangan-finals/blob/77f0ef14f1d252e4fb141f7e3b20b6cce989dc60/competition_rescue/state_machine.py#L2400)

**送达确认存在两处下位配套缺口，会影响首件和伤员搜索阶段。**

| 场景 | 上位 `77f0ef1` 的行为 | 下位 `fd63ab7` 的实际行为与待配套项 |
| --- | --- | --- |
| 视觉确认本次进区 | 发 `TASK_COMPLETE / U=0`。收到本任务、本动作的 ACCEPT 与 DONE、开爪且 mode16/17 后，登记一次送达 | 已接受 U=0 并沿原开爪撤离。首件成立需与上位已审核的单普通、物资区条件对应 |
| mode15 原 1 秒观察超时 | 发 `TASK_COMPLETE / U=1`，重复同动作继续 U=1。首件、已送数和伤员搜索轮次沿用此前值 | 当前接受入口要求 U=0，会拒绝 U=1。需在 FinalRun 接入未确认撤离原因，并复用原开爪、撤离动作 |
| 下位前段本地超时 | 上位识别原 ENTER 的匹配 DONE、开爪及 mode16/17，按未确认退出接返程 | 当前 `task_finish_delivery_exit` 会无条件设置 `first_delivery_done=true`。需让本地超时保留此前首件状态，避免两端首件进度分歧 |
| 视觉确认请求与本地超时先后到达 | 按实际已取得退出动作归属的一方处理 | 采用本次锁存的退出原因。本地超时先取得出口后，晚到的确认请求沿原归属检查处理 |

原 TYPE=0x18、opcode=0x06 和 0x1D/0x1E 配对沿用。A、B 为 0，flags 为 VALID 加阵营，U=0/1 表达本次退出原因。同一动作重发应保持同一个 U。上位 `_register_confirmed_delivery` 已将首件成立限定为已审核载荷恰好一件普通且目的地为物资区。首次确认后才启动伤员优先轮次，随后每次确认送达再推进轮次。尚未确认首件的超时撤离继续找普通物资，已确认首件之后的超时撤离继续原伤员搜索阶段。[上位送达登记](https://github.com/danmo-teng/shijue_fangan-finals/blob/77f0ef14f1d252e4fb141f7e3b20b6cce989dc60/competition_rescue/state_machine.py#L5538) · [下位 U 校验](https://github.com/kkkkkkkkkkkkkkkk222222/Final_Run/blob/fd63ab7e62e97630ee4625facc3ad20e99278e6d/Main/Src/Task.c#L8058) · [下位退出标记](https://github.com/kkkkkkkkkkkkkkkk222222/Final_Run/blob/fd63ab7e62e97630ee4625facc3ad20e99278e6d/Main/Src/Task.c#L4759)

上位提供的 `f405_finals_delivery_confirmation_fd63ab7.patch` 使用决赛预设开关接入上述语义。本轮已对本地基线执行补丁适用检查，通过。该补丁当前处于待实施、构建和配套部署状态。[配套补丁](https://github.com/danmo-teng/shijue_fangan-finals/blob/77f0ef14f1d252e4fb141f7e3b20b6cce989dc60/docs/contracts/f405_finals_delivery_confirmation_fd63ab7.patch)

**单件运输是另一项待两端同步实施的范围。** 上位指定版本的默认 `max_batch_count=3`、材料审核和下位 `task_audit_semantic` 仍允许首件后两三件材料。下位对已判合法的批次会拒绝分离。开局暂存和扫障取货另有非空审核入口。上位单件适配草案需要覆盖这些入口，并以本次用户确认的伤员优先要求约束选目标和选侧。当前“另一侧多件材料优先于伤员混装”的例外，在收敛为单件运输时需按新载荷资格重新核对。此项当前状态为待配套。[上位单件适配草案](https://github.com/danmo-teng/shijue_fangan-finals/blob/77f0ef14f1d252e4fb141f7e3b20b6cce989dc60/docs/FINALS_SINGLE_ITEM_PLAN.md) · [当前下位合法性](https://github.com/kkkkkkkkkkkkkkkk222222/Final_Run/blob/fd63ab7e62e97630ee4625facc3ad20e99278e6d/Main/Src/Task.c#L790)

本轮交付为源码核对和交接文档。后续配套需验证确认送达只登记一次并进入正确搜索阶段，同时核对 U=1 和本地超时沿原撤离且保留已确认进度，以及首件后的伤员优先搜索和普通分离按上述规则接续。固件构建结果、板端实际身份与实物送达效果在部署回执中分别记录。
