# 存储后端

Lumen 的存储层抽象为 `Backend` 接口，提供 `enqueue / lease / ack / nack / heartbeat` 五个原语。
目前有两个实现。

## Redis 后端（生产推荐）

- 类：`RedisBackend`，需要 Redis 7+（依赖 `ZADD` 的 `GT` 选项与 `Lua` 脚本原子性）。
- 队列用有序集合（Sorted Set）实现，score 为任务的可执行时间戳；键名为 `{queue_prefix}queue:{priority}`。
- 租约用 `SET ... NX PX` 实现，键名 `{queue_prefix}lease:{job_id}`。
- 选主锁键名 `{queue_prefix}leader`。
- 所有"取任务 + 加租约"操作在一个 Lua 脚本中完成，保证原子性。

## SQLite 后端（开发 / 单机）

- 类：`SQLiteBackend`，于 **2.3** 版本引入。
- 数据存放在单个文件，默认 `./lumen.db`；任务表名为 **`lumen_jobs`**，租约表名为 `lumen_leases`。
- 打开数据库时启用 **WAL 模式**（`PRAGMA journal_mode=WAL`）以允许读写并发。
- 不支持跨进程选主，多个 Worker 进程共用同一文件时以 `BEGIN IMMEDIATE` 事务串行化取任务。

## 选择后端

`open_backend(url)` 根据 URL scheme 选择实现：

| URL | 后端 |
|---|---|
| `redis://…` / `rediss://…` | `RedisBackend` |
| `sqlite:///path/to/file.db` | `SQLiteBackend` |
| 空字符串 | `SQLiteBackend`（`./lumen.db`） |

不支持的 scheme 会抛出 `lumen.errors.ConfigError`。
