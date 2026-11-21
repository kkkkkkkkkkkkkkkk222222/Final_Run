# FinalRun2 配套与离线验证

2026-11-22（上海时间）。独立源码从封存 `Final_task@24c7dab93368bf9e46cf7366f0a9a9ca466b611b` 建立，本次公开交付分支为 **`FinalRun2-material-push200`**；原FinalRun和先前配套分支保留。

当前配套为 [FinalRun2-upper · 02b8a81](https://github.com/kkkkkkkkkkkkkkkk222222/Final_Run/tree/02b8a812e8ab471ec8c54b8bfa3a2383d7e0ac91)。[版本锁](contracts/finalrun2_pose_delivery.json)保存上位提交、源码哈希和报文样例。下位仓库中的 upper_changes 为上次交付的 2fd77f9 快照。

## 开局保持开爪与原货复看

- 稳定开局暂存审核如实回报非空。开爪时两侧合计只有伤员，拒绝 GRAB；匹配的 U=5（A=0、B=12000、同 task 的新 action，带审核源帧）直接进入 SEARCH。相同动作重发复用结果。原空爪 U=5、材料合爪和混抓识别/分离仍按各自入口执行。
- 红蓝从实际审核请求开始，经 Python 比赛规划器、C 解析、Task 和 CRC 回包验证。纯伤员回 SEARCH，继续看纯伤员时保持开爪，随后看到混合堆才向材料发接近命令；单普通材料仍能合爪。另测较旧帧、相同帧、重复 U=5、双侧纯伤员，以及对普通或混合堆误发 U=5 的拒绝。
- 红蓝 W1 扫障后，实报文推进到找回观察位，模拟相机角度、漏检和延迟画面。错误视角、重复或过期图不作接近依据；新图重新看到目标时进入 APPROACH，连续三张有效新图无目标时返回 SEARCH。上位定向检查 10 项，另复跑下方距离、投送、扫障、弃批、暂停和重发回归。
- 联测使用模拟传感器、相机和执行器。现场实际软件版本、机械动作和碰撞情况待实车验证。本轮未部署、未烧录。

## 修改点

1. 独立FinalRun2构建、ELF/HEX/BIN及DAPLink入口。WWW与独立目录均可配置；关闭自动备份，避免构建影响封存版。
2. 名义前段从170改为200mm，末段仍270mm，总470mm；按实际位置计算到970/1240mm的剩余距离。ENTER明确携带前段/末段距离。一次受理锁存；前段结束先完成83°原机构行程，再执行末段。重复包和暂停恢复保留轮程，参数改变仍用原拒绝回包，不重开推送。实际出发位置已扣侧挤量，不再重复抵扣。
3. 非视觉安全区正对改为≤1°。旧视觉控制保留旧阈值；横扫A点转向不套用起推的1°门槛。
4. 新STAGE NAV动作立即清旧完成位；D=0完成后同action迟到的正距离不能重新运动，补位用新action。
5. 允许真实定位ALIGN完成后执行侧挤，以及持载保持围栏朝向横移A。横扫后退支持160mm；既有步号、重复/暂停/完成机制保持。

6. 单伤员也不正式投送；分类、数量和左右侧仍如实上报。材料/伤员混装保材料分离；只剩伤员沿原张爪、后退300mm和原转向/返搜。伤员识别、判障/扫障、开局临时移堆保留。

上位路线及具体说明见[可直接阅读的上位文档](../upper_changes/docs/POSE_DELIVERY_20261122.md)。路线按已确认方案变化；封存FinalRun路线无变化。

## 验证

| 检查 | 结果 |
| --- | --- |
| 生产Task与机构代码、硬件替身 | 8组推进长度；红蓝1°、83°等待、暂停/重发/改参/旧action、新NAV/迟到D、侧挤三段及重复抵扣、旧ENTER、会话重置通过 |
| 新上位→生产C解析/Task→CRC状态回包 | 14个距离边界；8条正常/20mm补位投送，含门前审核与确认/未确认退出；4条危险物/伤员挡路的W1扫障；4条红蓝抓取点/门前单伤员弃批通过 |
| 既有实际报文兼容 | 九类载荷、左右分离、单侧/弃批、禁用旧预转轻撞、抓后真实单伤员拒绝运输；左右混装保材料、开局临时移堆以及原确认/未确认出口通过 |
| ARM固件 | FinalRun2编译链接通过；身份与文件哈希以最终构建记录为准 |
| 设备、实车 | 未连接串口、未烧录、未发车；actual未知 |

迟到正距离重开已完成NAV的问题有修前失败、修后通过的直接用例。没有新增高频巡检、时间资格、FAULT或自动发车。

下面的宿主检查不会打开设备。在本目录执行，Python需能导入上位决策模块依赖：

```powershell
gcc -std=c11 -O2 -ffunction-sections -fdata-sections -DAPP_FINALS_SIDE_ONLY_SEPARATION=1 -DAPP_ENABLE_FINALS_CLAW_TIGHTEN=1 -DAPP_ENABLE_FINAL_PUSH_LIFT=1 -DAPP_FINALS_DELIVERY_CONFIRMATION=1 -DAPP_ENABLE_CARGO_LIFT_FILTER=0 -Itools/test_support -IMain/Inc tools/test_finalrun2_pose.c Main/Src/pid.c '-Wl,--gc-sections' -lm -o build/host/pose_test.exe
build/host/pose_test.exe
gcc -std=c11 -O2 -ffunction-sections -fdata-sections -DAPP_FINALS_SIDE_ONLY_SEPARATION=1 -DAPP_ENABLE_FINALS_CLAW_TIGHTEN=1 -DAPP_ENABLE_FINAL_PUSH_LIFT=1 -DAPP_FINALS_DELIVERY_CONFIRMATION=1 -DAPP_ENABLE_CARGO_LIFT_FILTER=0 -Itools/test_support -IMain/Inc tools/test_finals_wire.c Main/Src/vision.c Main/Src/pid.c '-Wl,--gc-sections' -lm -o build/host/paired_wire.exe
python tools/check_finalrun2_pose_pair.py ../tmp/FinalRun2_upper_handoff build/host/paired_wire.exe
python tools/check_finals_rdk_pair.py ../tmp/FinalRun2_upper_handoff build/host/paired_wire.exe
```

轮程、机械角和画面输入是模拟的。未覆盖真实定位漂移、制动、轮滑、相机失联恢复、全部物料排列和碰撞；失败回包不等于完成，编译与这些检查不保证现场永不卡住。
