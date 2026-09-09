# 调度器设计

## 职责

`CronScheduler` 负责三件事：解析 cron 表达式、维护"下次运行时间"堆、在每个 tick 把到期任务投递到队列。

## 选主（Leader Election）

多个调度器实例同时运行时只能有一个"领导者"投递任务，否则同一任务会被重复入队。
Lumen 用存储层的**分布式锁**选主：

- Redis 后端：`SET lumen:leader <instance_id> NX PX 30000`，锁 TTL 为 30 秒，领导者每 10 秒续期一次。
- SQLite 后端：单进程假设，不做选主，`acquire_leadership()` 恒返回 `True`。

领导者失联（未续期超过 30 秒）后，其他实例在下一个 tick 竞争加锁。切换期间最多有一个 tick 的投递延迟。

## Tick 循环

```
loop every tick_interval (默认 1.0 秒):
    if not acquire_leadership(): continue
    now = current time in LUMEN_TZ
    while heap.top.next_run <= now:
        job = heap.pop()
        enqueue(job)
        heap.push(job with next_run = next_run_time(job.cron, now))
```

## Misfire 策略

若调度器停机后重启，部分任务的触发时间已过。`misfire_grace`（默认 60 秒）内的任务**立即补投一次**；
超过 grace 的任务**跳过本次**，直接计算下一次运行时间。这样避免了停机数小时后"补跑上百次"的雪崩。

## 时区

cron 表达式按 `LUMEN_TZ` 解释（默认 UTC）。夏令时切换时，`next_run_time` 使用 `zoneinfo` 的
`fold` 语义，保证"每天 02:30"在不存在的时刻顺延到 03:30，而不是被跳过。
