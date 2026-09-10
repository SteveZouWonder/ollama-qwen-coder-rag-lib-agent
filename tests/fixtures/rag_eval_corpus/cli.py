"""Lumen 命令行入口（评测语料，非真实实现）。"""
from __future__ import annotations

import argparse
import json
import sys

VERSION = "2.4.0"


def build_parser() -> argparse.ArgumentParser:
    """构造 ``lumen`` 的参数解析器，注册 run / enqueue / status / purge / dead 五个子命令。"""
    parser = argparse.ArgumentParser(prog="lumen", description="Lumen 任务调度")
    parser.add_argument("--config", help="lumen.toml 路径")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    parser.add_argument("--version", action="version", version=f"lumen {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="启动 Worker（内嵌调度器）")
    run.add_argument("--workers", type=int, help="覆盖 max_workers")
    run.add_argument("--queues", help="逗号分隔的队列名")
    run.add_argument("--no-scheduler", action="store_true", help="不参与选主")

    enq = sub.add_parser("enqueue", help="手动入队一个任务")
    enq.add_argument("task", help="可导入路径，如 myapp.tasks.send_email")
    enq.add_argument("--arg", action="append", default=[], help="key=value，可重复")
    enq.add_argument("--priority", type=int, default=1)

    sub.add_parser("status", help="打印队列长度 / 活跃 Worker / 领导者")

    purge = sub.add_parser("purge", help="清理已完成且过期的任务记录")
    purge.add_argument("--older-than", type=int, help="保留秒数，默认取 job_ttl")
    purge.add_argument("--dry-run", action="store_true")

    dead = sub.add_parser("dead", help="死信队列管理")
    dead_sub = dead.add_subparsers(dest="dead_command", required=True)
    dead_sub.add_parser("list")
    dead_sub.add_parser("replay").add_argument("job_id")
    dead_sub.add_parser("purge")
    return parser


def cmd_status(backend, as_json: bool = False) -> int:
    """打印各队列长度、活跃 Worker 数与当前领导者；Redis 不可达时输出 E101 并返回 2。"""
    try:
        info = backend.status()
    except ConnectionError:
        print("E101 cannot connect to redis", file=sys.stderr)
        return 2
    if as_json:
        print(json.dumps(info, ensure_ascii=False))
    else:
        for queue, length in info["queues"].items():
            print(f"{queue:<20} {length}")
        print(f"workers: {info['workers']}  leader: {info.get('leader') or '-'}")
    return 0


def cmd_purge(backend, older_than: int | None, dry_run: bool, job_ttl: int = 86400) -> int:
    """删除完成时间早于 ``older_than``（默认 ``job_ttl``）秒的任务记录；``dry_run`` 只统计。"""
    threshold = older_than if older_than is not None else job_ttl
    count = backend.count_finished_older_than(threshold)
    if not dry_run:
        backend.delete_finished_older_than(threshold)
    print(f"{'将删除' if dry_run else '已删除'} {count} 条记录（保留 {threshold} 秒内）")
    return 0


def main(argv: list[str] | None = None) -> int:
    from storage import open_backend

    args = build_parser().parse_args(argv)
    backend = open_backend("")
    if args.command == "status":
        return cmd_status(backend, args.json)
    if args.command == "purge":
        return cmd_purge(backend, args.older_than, args.dry_run)
    print(f"命令 {args.command} 在评测语料中未实现")
    return 1
