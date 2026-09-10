# 安装指南

## 环境要求

- Python **3.11** 或更高版本（3.10 及以下不受支持，因为使用了 `tomllib` 与 `ExceptionGroup`）。
- 生产环境需要 **Redis 7** 或更高版本；开发环境可用内置 SQLite 后端，无需 Redis。
- 操作系统：Linux / macOS 均可；Windows 仅支持 SQLite 后端。

## 安装

```bash
pip install lumen-scheduler
```

安装可选依赖：

```bash
pip install "lumen-scheduler[redis]"      # Redis 后端
pip install "lumen-scheduler[metrics]"    # Prometheus 指标导出
```

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `LUMEN_REDIS_URL` | Redis 连接串，如 `redis://localhost:6379/0` | 空（使用 SQLite） |
| `LUMEN_LOG_LEVEL` | 日志级别：DEBUG / INFO / WARNING / ERROR | `INFO` |
| `LUMEN_TZ` | 调度器解释 cron 表达式时使用的时区 | `UTC` |
| `LUMEN_SIGNING_KEY` | 任务载荷 HMAC 签名密钥（见安全文档） | 空（不签名） |

## 验证安装

```bash
lumen --version
# lumen 2.4.0
lumen status
```

若 `lumen status` 报错 `E101`，说明 Redis 不可达，请检查 `LUMEN_REDIS_URL`。
