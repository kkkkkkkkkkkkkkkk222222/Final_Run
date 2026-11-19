# FinalRun 与正式 RDK 28deaa6 的分阶段离线验证

配套基线为 [shijue_fangan-finals/main@28deaa6](https://github.com/danmo-teng/shijue_fangan-finals/tree/28deaa6861c0208adf4b00c125d213c687bd2a95)。本轮只改固件端与交付说明。普通分离要求明确 SIDE_VALID，动作参数 A、B、U 为零，禁用预转和轻撞。RELEASE_BOTH 弃批不需要保留侧。本版不需要另贴旧上位补丁。

| 环节 | 实际验证了什么 | 验证边界 |
| --- | --- | --- |
| 发车、首放与返回 | 正式 CONFIG 字节经下位解析，任务进入发车倒退，核对距离；上位进攻逐段 DONE、防守放下后直接返①的路径回归 | 模拟位置与机构，无实车首放 |
| 搜索和换站 | 上位①③搜索、540°切换；下位接收 step13 正距离／D=0，回当次 ACCEPT／DONE | 上位的转正后取新图用例需带相机角度和采集时刻 |
| 接近、重选 | 上位远目标区内复看、聚堆测距、空爪丢目标；上位 U=5 帧经下位进入 SEARCH，重复请求仍回应同一动作 | 没有相机推理／测距实物 |
| 审核、合爪、分离 | 九种真实协议载荷在两端对比；明确左右分离及重复包，旧试转、转中刹停、无侧及轻撞被拒；合爪前目标核心，闭爪后实际单橙，模拟合爪、复审并进入可运输状态 | 实际角度、夹持力未测；另用机构替身核对 16 组普通保留爪组合 |
| 持载、避障 | 上位核对载荷变化、原物找回失败出口、侧挤仅一次及轮程抵扣；上位侧挤和扫障命令经实际解包并被下位状态机接受 | 接受入口和路线逻辑通过，未声称所有扫障机械步骤已串成一趟实跑 |
| 推入、送达、重推 | 普通 ENTER 和有抵扣 ENTER 的 400 mm／83°／670 mm 切换；两三件重推资格、三件重推中和退出边界；上位 COMPLETE U=0 和 U=1 均收到下位开爪退出回包，回送上位后验证错配不记、超时不记、正确确认只记一次 | 舵机／轮程是模拟值，未测实际推板高度、轮滑或整批是否进区 |
| 暂停、故障、恢复 | 上位保局暂停、失目标恢复、旧回包；下位确认原因与重发；故障优先级以完整创建的 planner 单独复验。预热停车优先及子进程退出在原控制函数、模拟进程下复验 | Linux 操作面板整程序、实体按键和设备未在 Windows 上运行 |

**测试结果。** 真实配对使用发布版上位构帧、下位生产 CRC／解包、Task 与状态编码。检查返回的任务号、动作号、已接受操作码、回包 CRC、审核与完成位；对送达回包还调用上位登记函数。协议单测 29 项通过。上位原始定向用例 34 项中 31 项直接通过，另 3 项原样未通过：换站样本缺当前视角和采集时刻，故障用例绕过 planner 的构造函数，预热用例导入 Linux 本地接口。分别补齐样本、正常构造对象及隔离预热控制函数，三项行为分别通过。后者并不代表原始用例全部通过。

**复现真实报文联测**（在下位仓库执行，上位源码参数须为 28deaa6；Python 环境须满足该上位决策模块的依赖）：

```powershell
gcc -std=c11 -O2 -ffunction-sections -fdata-sections -DAPP_FINALS_SIDE_ONLY_SEPARATION=1 -DAPP_ENABLE_FINALS_CLAW_TIGHTEN=1 -DAPP_ENABLE_FINAL_PUSH_LIFT=1 -DAPP_FINALS_DELIVERY_CONFIRMATION=1 -DAPP_ENABLE_CARGO_LIFT_FILTER=0 -Itools/test_support -IMain/Inc tools/test_finals_wire.c Main/Src/vision.c Main/Src/pid.c '-Wl,--gc-sections' -lm -o build/F405/FinalRun/paired_wire.exe
python tools/check_finals_rdk_pair.py ../Finals_RDK build/F405/FinalRun/paired_wire.exe
```
