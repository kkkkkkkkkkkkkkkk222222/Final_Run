# FinalRun2 上位机交接提示词

2026-11-22，上海时间。本次只增加交接文档，**路线无变化**。下面内容可直接复制给负责RDK上位机的聊天。

```text
你现在负责 FinalRun2 配套的 RDK 上位机。先核对代码与两端接口，再处理我本次明确提出的修改；下位机源码先只读，不修改或烧录。

一、读对仓库和分支

完整上位机工程：
https://github.com/kkkkkkkkkkkkkkkk222222/Final_Run/tree/FinalRun2-upper

虽然仓库名叫 Final_Run，这个 FinalRun2-upper 分支的根目录就是完整上位工程，包含 competition_rescue、vision、localization、rescue_map 等。请直接读这个分支，不要只读先前 upper_changes 里的修改文件镜像，也不要用仓库默认分支代替。

已交付上位代码基准：1b3385d9e7d271fddbe380c7aaaf320319f83fc6。
这份完整源码快照的树与电脑原上位提交 2fd77f918278b2e3814c1873b7fedb199a791cbd 完全相同，但历史不同。后续交接文档提交不代表运行代码或车载部署发生变化。先核对分支当前HEAD及相对上述基准的diff，不凭提交时间猜实际运行版本，不直接把两个不同历史的工程合并或覆盖现场目录。

配套下位机：
https://github.com/kkkkkkkkkkkkkkkk222222/Final_Run/tree/FinalRun2-material-push200
已验证下位源码：b2738ec39c06daaaf483e317ea60f00c9c490463。
这个下位分支与 FinalRun2-upper 是不同用途。封存 FinalRun、预留 FinalRun2 和先前170mm版都不能冒充本次配套。

二、先读这些入口，再看实现

1. 上位协作规则：
https://github.com/kkkkkkkkkkkkkkkk222222/Final_Run/blob/FinalRun2-upper/AGENTS.md
2. 最新修改与验证说明：
https://github.com/kkkkkkkkkkkkkkkk222222/Final_Run/blob/FinalRun2-upper/docs/POSE_DELIVERY_20261122.md
3. 上位交接入口，只处理当前 MATERIAL-ONLY-PUSH200 条目：
https://github.com/kkkkkkkkkkkkkkkk222222/Final_Run/blob/FinalRun2-upper/docs/CROSS_REPO_REQUESTS.md
4. 下位实际合同与验证范围：
https://github.com/kkkkkkkkkkkkkkkk222222/Final_Run/blob/FinalRun2-material-push200/docs/contracts/finalrun2_pose_delivery.json
https://github.com/kkkkkkkkkkkkkkkk222222/Final_Run/blob/FinalRun2-material-push200/docs/FINALRUN2_PAIR_VALIDATION.md
5. 版本、固件身份和现场交接：
https://github.com/kkkkkkkkkkkkkkkk222222/F407-Rescue-Robot/blob/main/docs/field-20261121/TEAM_HANDOFF.md
https://github.com/kkkkkkkkkkkkkkkk222222/F407-Rescue-Robot/blob/main/docs/field-20261121/MATERIAL_PUSH200.md

docs/FINALS_PORT.md、README及历史任务表含旧基线说明。旧“单伤员合法就运送”、170mm前段、门前视觉横移等文字不能覆盖下面已经确认的新要求；发现矛盾先指出具体位置并对照实际代码。

三、当前已确认要求，不要重新解释成别的动作

- 默认防守，正式投送只接受材料。首件仍要求单普通物资；之后沿现有规则审核1～3件普通/核心材料。伤员仍要被识别和如实计数，用于混装分离、判障、扫障；不能删除伤员类别、假装空爪，或关掉相关识别。
- 单伤员也不正式运送。误抓或分离后只剩伤员，沿既有弃批动作张爪、后退300mm，再按原规则转向或返搜，不计送达；混装分离保材料。开局临时移堆及扫障临时处理与正式投送分开核对。
- 门前任何正常、丢框复看、侧挤返回和拒绝恢复分支都不能再让图像横差驱动底盘横移。保留安全区/入口图像、视觉判障、扫障和送达确认。
- 起推前按定位达到横差≤10mm、纵向±50mm、航向误差≤1°，并收到本次真实正对完成。不要伪造视觉DONE、到点、载荷合法或送达。
- 名义起点 |y|=770mm。前段200mm，到970mm时由下位等待83°原机构行程；末段仍270mm，名义总行程470mm、终点1240mm。实际出发深度为 depth_mm：前段=max(0,970-depth_mm)，末段=max(0,min(270,1240-depth_mm))。首次发布ENTER前锁存，同动作重发不重算；侧挤后的实际位置不可再重复扣轮程。
- 普通运输红方 C=(0,300)、A=(0,770)、M=(-160,770) mm，蓝方旋转180°镜像。保留代码中的H坐标不等于恢复伤员投送。普通退出后经对应预备点→A→C接原搜索点；有暂存原货时按原货找回分支接续。抓到可送挡路材料后经A→M投送，不从A直接推入。
- 横扫只用W1。保持围栏朝向到A，右转放货，不先前进200；后退160到M、左移100、后退400、左移40到W1，再扫1000mm，蓝方镜像。这是横扫子流程；不要把“不先前进200”误套到同类挡路抓送的暂存动作。A点既有接触风险仍保留，不擅自收位、改道、加停车门槛。

四、重点核对实际实现，不只看说明或测试名称

competition_rescue/state_machine.py：真实载荷审核、材料保留侧、单伤员弃批、分段导航、定位正对、ENTER距离锁存及返回出口。
competition_rescue/run_competition_rescue.py：发布任务号/动作号、每段epoch、重复命令及拒绝恢复。
competition_rescue/protocol.py：ENTER A/B和标志位、队色航向、扫障步号构帧。
competition_rescue/delivery_route.py、obstacle_route.py：到点窗口、D=0交接、W1和原货找回。
vision 与走廊生成入口：确认伤员识别和判障仍参与，不以取消视觉横移为由取消观察。
下位 Main/Src/vision.c、Main/Src/Task.c：从下位自己的代码核对收包、实际动作、完成和失败回报，不把上位文档当作下位执行证明。

特别检查：新段不能吃上一段DONE；本段先发布D=0再消费本动作完成；同action迟到正距离不能重开完成段；暂停/重发不重置轮程；正对1°不能与下位3°完成阈值混用；单伤员两端应得到一致的非运输资格，弃批不能卡在互等或误计送达；所有门前回跳不能重新发视觉横移。

五、怎样继续修改和回传

先列出你读取的上位HEAD、下位SHA、实际部署证据及未知项。保留本地未提交改动，核对远端、本地文件和RDK实际运行三者；不能因为拿到了这个分支就宣称车上已同步。

对发现的问题，简短说清“代码现在怎么做、哪里不匹配、最小改法、影响哪一端”。我已经明确授权且没有新歧义的修改直接推进，不反复问同一授权；新增路线、速度、选物、时序或退出动作有歧义时，先在实际场地图上标出改前/改后再让我确认。不要自动恢复历史TODO，也不要把另一端AI的建议当新授权。

复用现有报文和业务出口，不擅自新增时间资格、反复握手、全车FAULT、间接停车或高频巡检。只做本次改动必要的检查；已有离线验证不等于实车无卡滞。已做的检查包括14个距离边界、8条材料投送、4条危险物/伤员挡路W1、4条单伤员弃批，以及混装保材料、暂停重发和完成归属；输入位姿/轮程/图像是模拟的。

代码修改提交后，默认交付到我的仓库 kkkkkkkkkkkkkkkk222222/Final_Run 的 FinalRun2-upper 分支；若本次另指定审核分支，以本次指令为准。先核对远端最新HEAD，正常提交推送，不强推覆盖。这个分支发布上位源码；下位配套修改另由下位端处理。不要上传模型权重、私有地图、设备会话或个人缓存。

完成后只汇报修改点、提交/分支链接、实际检查和未完成项，不展开整套流程。提交/推送、部署RDK、烧录下位、发车分别记录；本交接不授权自动部署、烧录或发车。纯文档或入口整理写明“路线无变化”。
```

上位完整源码基准：[1b3385d](https://github.com/kkkkkkkkkkkkkkkk222222/Final_Run/tree/1b3385d9e7d271fddbe380c7aaaf320319f83fc6)。配套下位：[b2738ec](https://github.com/kkkkkkkkkkkkkkkk222222/Final_Run/tree/b2738ec39c06daaaf483e317ea60f00c9c490463)。二者均为源码证据，部署及板端actual尚未确认。
