# 指标与监控

Lumen 内置 Prometheus 文本格式的指标导出器（2.2 引入），由 `metrics_port` 控制（默认 **9464**，0 关闭）。

## 指标列表

| 指标 | 类型 | 标签 | 含义 |
|---|---|---|---|
| `lumen_jobs_total` | Counter | `queue`, `status`（succeeded / failed / dead） | 任务完成计数 |
| `lumen_job_duration_seconds` | Histogram | `queue` | 任务执行耗时，桶：0.1 / 0.5 / 1 / 5 / 30 / 300 秒 |
| `lumen_queue_length` | Gauge | `queue`, `priority` | 当前队列长度 |
| `lumen_lease_expired_total` | Counter | `queue` | 租约过期次数（对应错误码 E204） |
| `lumen_scheduler_is_leader` | Gauge | `instance` | 该实例是否为领导者（1 / 0） |
| `lumen_retries_total` | Counter | `queue` | 重试次数 |

## 推荐告警

- `rate(lumen_lease_expired_total[5m]) > 0`：租约频繁过期，检查 `heartbeat_interval` / `lease_ttl`。
- `lumen_queue_length > 1000` 持续 10 分钟：消费能力不足，增加 `max_workers` 或 Worker 进程。
- `sum(lumen_scheduler_is_leader) != 1`：没有或有多个领导者，检查 Redis 锁。

## Grafana

仓库 `contrib/grafana/lumen.json` 提供了一个面板模板，包含队列长度、P95 耗时、失败率三张图。
