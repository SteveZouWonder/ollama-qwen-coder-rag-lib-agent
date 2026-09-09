"""CLI 入口层子包（F10 P2-2）。

- ``parser``：``ParsedCommand`` / ``parse_command`` / ``classify_mode``（纯函数命令路由）
- ``help_text``：``TUTORIAL_TEXT`` / ``HELP_TEXT`` / ``print_help``
- ``handlers``：自包含命令处理器与 ``COMMAND_HANDLERS`` 命令表

``src/query_interface.py`` 保留主循环、渲染与引擎耦合命令，并重导出上述公开名。
"""
