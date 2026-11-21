# FinalRun2 配套与离线验证

2026-11-22（上海时间）。独立源码从封存 `Final_task@24c7dab93368bf9e46cf7366f0a9a9ca466b611b` 建立，分支 `FinalRun2-pose-delivery`；原 Final_task 和封存镜像未改。新上位本地分支 `finals-pose-delivery`、提交 `228cecf37e6ad348679c5fcb5fd47fe37f256019`，正式上位仓库推送因当前账号无写权限返回403。完整两提交补丁已随本仓库交付：[上位补丁](contracts/rdk_pose_delivery_228cecf.patch)。精确版本与报文见 [配套锁](contracts/finalrun2_pose_delivery.json)。这份新锁不覆盖第一场冻结锁。

## 修改点

1. 独立FinalRun2构建、ELF/HEX/BIN及DAPLink入口。WWW与独立目录均可配置；关闭自动备份，避免构建影响封存版。
2. 支持ENTER明确携带前段/末段距离。一次受理锁存；前段结束先完成83°原机构行程，再执行末段。重复包和暂停恢复保留轮程，参数改变仍用原拒绝回包，不重开推送。实际出发位置已扣侧挤量，不再重复抵扣。
3. 非视觉安全区正对改为≤1°。旧视觉控制保留旧阈值；横扫A点转向不套用起推的1°门槛。
4. 新STAGE NAV动作立即清旧完成位；D=0完成后同action迟到的正距离不能重新运动，补位用新action。
5. 允许真实定位ALIGN完成后执行侧挤，以及持载保持围栏朝向横移A。横扫后退支持160mm；既有步号、重复/暂停/完成机制保持。

上位的具体路线、默认防守、材料主动搜索及图像用途见 补丁内的 `docs/POSE_DELIVERY_20261122.md`。路线按已确认方案变化；封存FinalRun路线无变化。

## 验证

| 检查 | 结果 |
| --- | --- |
| 生产Task与机构代码、硬件替身 | 8组推进长度；红蓝1°、83°等待、暂停/重发/改参/旧action、新NAV/迟到D、侧挤三段及重复抵扣、旧ENTER、会话重置通过 |
| 新上位→生产C解析/Task→CRC状态回包 | 14个距离边界；8条正常/20mm补位投送，含门前审核与确认/未确认退出；4条完整W1扫障至原货观察入口通过 |
| 既有实际报文兼容 | 九类载荷、左右分离、单侧/弃批、禁用旧预转轻撞、抓后真实单伤员、原确认/未确认出口通过 |
| ARM固件 | FinalRun2编译链接通过；身份与文件哈希以最终构建记录为准 |
| 设备、实车 | 未连接串口、未烧录、未发车；actual未知 |

迟到正距离重开已完成NAV的问题有修前失败、修后通过的直接用例。没有新增高频巡检、时间资格、FAULT或自动发车。

下面的宿主检查不会打开设备。在本目录执行，Python需能导入上位决策模块依赖：

```powershell
gcc -std=c11 -O2 -ffunction-sections -fdata-sections -DAPP_FINALS_SIDE_ONLY_SEPARATION=1 -DAPP_ENABLE_FINALS_CLAW_TIGHTEN=1 -DAPP_ENABLE_FINAL_PUSH_LIFT=1 -DAPP_FINALS_DELIVERY_CONFIRMATION=1 -DAPP_ENABLE_CARGO_LIFT_FILTER=0 -Itools/test_support -IMain/Inc tools/test_finalrun2_pose.c Main/Src/pid.c '-Wl,--gc-sections' -lm -o build/host/pose_test.exe
build/host/pose_test.exe
gcc -std=c11 -O2 -ffunction-sections -fdata-sections -DAPP_FINALS_SIDE_ONLY_SEPARATION=1 -DAPP_ENABLE_FINALS_CLAW_TIGHTEN=1 -DAPP_ENABLE_FINAL_PUSH_LIFT=1 -DAPP_FINALS_DELIVERY_CONFIRMATION=1 -DAPP_ENABLE_CARGO_LIFT_FILTER=0 -Itools/test_support -IMain/Inc tools/test_finals_wire.c Main/Src/vision.c Main/Src/pid.c '-Wl,--gc-sections' -lm -o build/host/paired_wire.exe
python tools/check_finalrun2_pose_pair.py ../Finals_RDK build/host/paired_wire.exe
python tools/check_finals_rdk_pair.py ../Finals_RDK build/host/paired_wire.exe
```

轮程、机械角和画面输入是模拟的。未覆盖真实定位漂移、制动、轮滑、相机失联恢复、全部物料排列和碰撞；失败回包不等于完成，编译与这些检查不保证现场永不卡住。
