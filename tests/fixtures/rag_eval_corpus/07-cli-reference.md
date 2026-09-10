# 命令行参考

`lumen` 命令由 `lumen.cli` 模块提供，全部子命令如下。

## `lumen run`

启动一个 Worker 进程（同时内嵌一个调度器实例）。

```bash
lumen run --workers 8 --queues default,billing
```

- `--workers N`：覆盖配置 `max_workers`。
- `--queues a,b`：只消费指定队列，默认消费全部。
- `--no-scheduler`：只做 Worker，不参与选主。

## `lumen enqueue`

手动入队一个任务，用于调试：

```bash
lumen enqueue myapp.tasks.send_email --arg to=alice@example.com --priority 1
```

## `lumen status`

打印各队列长度、活跃 Worker 数、当前领导者实例 ID。Redis 不可达时返回错误码 `E101`。

## `lumen purge`

删除已完成且超过保留期的任务记录：

```bash
lumen purge                      # 按配置 job_ttl（默认 86400 秒）清理
lumen purge --older-than 3600    # 只保留最近 1 小时
lumen purge --dry-run            # 仅统计不删除
```

## `lumen dead`

死信队列管理，子命令 `list` / `replay <job_id>` / `purge`，详见重试策略文档。

## 全局选项

- `--config PATH`：指定 `lumen.toml` 路径。
- `--json`：以 JSON 输出，便于脚本处理。
- `--version`：打印版本号。
