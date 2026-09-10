# 常见问题

## 任务一直显示 running，不结束也不重试？

多半是 Worker 崩溃后租约未过期。等待 `lease_ttl`（默认 45 秒）后任务会被其他 Worker 接管。
若长期不恢复，检查 `heartbeat_interval` 是否被误设为大于 `lease_ttl`。

## 如何修改调度时区？

设置环境变量 `LUMEN_TZ`，例如 `LUMEN_TZ=Asia/Shanghai`。修改后需重启调度器；已计算的"下次运行时间"会在重启时按新时区重算。

## 指标在哪里看？

Worker 启动后在 `metrics_port`（默认 **9464**）暴露 Prometheus 文本格式指标，访问 `http://<host>:9464/metrics`。
设置 `metrics_port = 0` 可关闭。

## 同一任务被执行了两次？

Lumen 保证"至少一次"而非"恰好一次"。以下情况会重复执行：Worker 执行成功但在 `ack` 前崩溃；
或多个调度器实例未正确选主（检查 Redis 锁是否被手工删除）。任务代码应保持幂等。

## 能否在 Windows 上运行？

可以，但仅支持 SQLite 后端；Redis 后端依赖的 `fork` 语义在 Windows 上不可用。

## 死信任务会自动过期吗？

不会。死信队列不受 `job_ttl` 约束，需要手动执行 `lumen dead purge` 或 `lumen dead replay`。

## 如何给任务设置优先级？

2.4 起支持 `priority_levels` 个优先级（默认 3），数字越小越优先。入队时传 `--priority 1` 或在代码中
`enqueue(job, priority=1)`。
