# 安全

## 载荷签名

2.2 起，任务载荷可用 **HMAC-SHA256** 签名，防止有权写入 Redis 的第三方注入伪造任务。

- 密钥由环境变量 **`LUMEN_SIGNING_KEY`** 提供；为空时不签名也不校验。
- 生产者入队时计算 `HMAC(key, canonical_json(payload))` 并写入 `sig` 字段；Worker 取到任务后先校验签名，
  不匹配则拒绝执行并记录错误码 `E410`，任务直接进入死信队列。
- 签名覆盖任务路径、参数与入队时间戳，不覆盖优先级（优先级允许运维调整）。

## 密钥轮换

建议每 **90 天**轮换一次密钥。轮换步骤：

1. 在所有 Worker 侧设置 `LUMEN_SIGNING_KEY_PREVIOUS=<旧密钥>`、`LUMEN_SIGNING_KEY=<新密钥>`，Worker 会同时接受两把密钥；
2. 更新所有生产者的 `LUMEN_SIGNING_KEY` 为新密钥；
3. 等待 `job_ttl`（默认 24 小时）后移除 `LUMEN_SIGNING_KEY_PREVIOUS`。

## Redis 访问控制

- 生产环境务必启用 Redis ACL，为 Lumen 创建只能访问 `{queue_prefix}*` 键的用户。
- 使用 `rediss://` 启用 TLS；Lumen 不会在日志中打印连接串中的密码。

## 任务代码执行边界

Lumen 通过可导入路径动态加载任务函数。为防止任意代码执行，可在配置中限定允许的模块前缀：

```toml
[lumen.security]
allowed_task_prefixes = ["myapp.tasks.", "billing.jobs."]
```

不在白名单内的任务路径会被拒绝入队（`ConfigError`）。
