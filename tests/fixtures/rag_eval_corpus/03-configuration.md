# 配置参考

Lumen 从 `lumen.toml` 读取配置，环境变量优先级高于配置文件。所有配置项如下表：

| 配置项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `max_workers` | int | `4` | 单个 Worker 进程内并发执行任务的线程数 |
| `retry_limit` | int | `3` | 任务失败后的最大重试次数，超过后进入死信队列 |
| `heartbeat_interval` | int（秒） | `15` | Worker 向存储层刷新租约的间隔 |
| `lease_ttl` | int（秒） | `45` | 租约有效期，通常设为心跳间隔的 3 倍 |
| `queue_prefix` | str | `"lumen:"` | Redis 键前缀，多个应用共用一个 Redis 时用于隔离 |
| `job_ttl` | int（秒） | `86400` | 已完成任务记录的保留时间（24 小时），`lumen purge` 依据此值清理 |
| `tick_interval` | float（秒） | `1.0` | 调度器检查到期任务的周期 |
| `misfire_grace` | int（秒） | `60` | 错过触发时间超过该值的任务按 misfire 策略处理 |
| `priority_levels` | int | `3` | 优先级队列数量（2.4 新增） |
| `metrics_port` | int | `9464` | Prometheus 指标导出端口，0 表示关闭 |

## 示例 `lumen.toml`

```toml
[lumen]
max_workers = 8
retry_limit = 5
heartbeat_interval = 10
lease_ttl = 30
queue_prefix = "billing:"
```

## 注意事项

- `lease_ttl` 必须大于 `heartbeat_interval`，否则 Worker 会在两次心跳之间丢失租约（错误码 `E204`）。
- 修改 `queue_prefix` 后旧队列中的任务不会自动迁移。
- `priority_levels` 取值范围 1–9；设为 1 等价于关闭优先级队列。
