# 可直接阅读的上位修改代码

上位提交 `2fd77f918278b2e3814c1873b7fedb199a791cbd`，基线 `28deaa6861c0208adf4b00c125d213c687bd2a95`。本目录完整保存本轮相对基线修改过的 11 个文件；路径与正式上位仓库一致，可直接打开源码阅读，不必先展开补丁。

- [业务决策、200+270与单伤员弃批](competition_rescue/state_machine.py)
- [任务/动作号发布及恢复](competition_rescue/run_competition_rescue.py)
- [报文协议](competition_rescue/protocol.py)
- [分段运输](competition_rescue/delivery_route.py) / [W1清障路线](competition_rescue/obstacle_route.py)
- [修改说明与验证](docs/POSE_DELIVERY_20261122.md) / [上位定向用例](competition_rescue/tests/test_pose_delivery.py)

这是完整修改文件的只读交付镜像，不是独立可运行的整个上位工程。未变化的依赖仍来自基线；仓库docs/contracts内的完整补丁按顺序应用即可得到同一代码树。没有复制模型权重、设备日志、会话或个人地图文件。源码哈希见[source_manifest.json](source_manifest.json)。下位完整工程位于本分支根目录。本次未部署、烧录或发车。
