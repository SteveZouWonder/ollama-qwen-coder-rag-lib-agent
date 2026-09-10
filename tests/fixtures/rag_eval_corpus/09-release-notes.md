# 发布说明

## 2.4.0（2026-05-12）

- **新增**：优先级队列。配置项 `priority_levels`（默认 3），CLI `--priority`，API `enqueue(job, priority=)`。
- **新增**：`lumen purge --dry-run`。
- **改进**：`compute_backoff` 的抖动范围由 0–100% 收窄为 50%–100%，避免退避时间过短。
- **修复**：夏令时切换日 `next_run_time` 可能跳过 02:xx 的任务。

## 2.3.0（2026-01-20）

- **新增**：SQLite 后端（`SQLiteBackend`），开发环境不再需要 Redis。任务表 `lumen_jobs`，启用 WAL。
- **新增**：`open_backend(url)` 按 scheme 自动选择后端。
- **改进**：Redis 取任务 + 加租约合并为一个 Lua 脚本。

## 2.2.0（2025-09-03）

- **新增**：任务载荷 HMAC-SHA256 签名（`LUMEN_SIGNING_KEY`）。
- **新增**：Prometheus 指标导出（`metrics_port`，默认 9464）。
- **修复**：`misfire_grace` 内的任务重启后未补投。

## 2.1.0（2025-05-15）

- **新增**：死信队列与 `lumen dead` 子命令。
- **新增**：`NonRetryable` 异常。

## 2.0.0（2025-01-08）

- 重写存储层为 `Backend` 接口；配置文件由 `lumen.ini` 改为 `lumen.toml`（不兼容变更）。
- 最低 Python 版本提升到 3.11。
