"""CLI 入口层子包（F10 P2-2 建包，P3-2 二次拆分）。

- ``state``：进程内共享状态（``HAS_RICH`` 等探测、``console``、``rag_engine`` / ``react_engine`` /
  ``last_*_sources`` / ``command_recommender``、``_progress_state``）——其他模块 ``from cli import state``
  后经 ``state.xxx`` 运行时取值；测试打桩目标 ``cli.state.<name>``
- ``parser``：``ParsedCommand`` / ``parse_command`` / ``classify_mode``（纯函数命令路由）
- ``help_text``：``TUTORIAL_TEXT`` / ``print_help(console, has_rich)``
- ``render``：横幅、教程、工具表、来源表、统计表、回答 Panel、流式面板、结构化提示
- ``callbacks``：``on_step_callback`` / ``on_confirm_callback`` / ``ask_progress_callback``
- ``rag_adapter``：``rag_pipeline`` 别名与薄封装、``_cli_ask_progress`` 终端进度渲染
- ``recommend``：命令推荐记录 / 展示、会话上下文与健康度提示
- ``engine_commands``：``handle_*(ctx, parsed)`` 引擎耦合命令、``_ENGINE_HANDLERS``、
  ``_build_cli_context`` / ``dispatch_command``
- ``handlers``：自包含命令处理器与 ``COMMAND_HANDLERS`` 命令表（经 ``CLIContext`` 注入）

``src/query_interface.py`` 只保留解释器自保护、日志、readline / 输入与 ``main``（argparse +
引擎装配 + REPL），并重导出上述全部公开名以兼容 ``from query_interface import X``。
"""
