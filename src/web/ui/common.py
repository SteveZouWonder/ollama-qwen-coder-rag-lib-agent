"""页面复用件：页头、二步确认按钮、只读表格、结果区。"""  # pragma: no cover
from __future__ import annotations

from typing import Any, Callable, List, Optional, Sequence

import gradio as gr


def page_title(title: str, desc: str = "") -> None:  # pragma: no cover
    """页面标题 + 一句说明。"""
    html = f"<h2>{title}</h2>" + (f"<p>{desc}</p>" if desc else "")
    gr.HTML(html, elem_classes=["cb-page-title"])


def section(title: str) -> None:  # pragma: no cover
    """页内小节标题。"""
    gr.HTML(f'<div class="cb-side-title"><h3>{title}</h3></div>')


def result_md(value: str = "", classes: Optional[Sequence[str]] = None) -> gr.Markdown:  # pragma: no cover
    return gr.Markdown(value, elem_classes=["cb-result", *(classes or [])])


def table(  # pragma: no cover
    headers: List[str],
    value: Optional[List[List[Any]]] = None,
    *,
    label: Optional[str] = None,
    max_height: int = 360,
    search: bool = True,
    column_widths: Optional[List[str]] = None,
) -> gr.Dataframe:
    """只读数据表（``type="array"``，便于按行索引取值）。"""
    return gr.Dataframe(
        headers=headers,
        value=value or [],
        type="array",
        datatype="str",
        interactive=False,
        wrap=True,
        max_height=max_height,
        show_search="search" if search else "none",
        label=label,
        show_label=bool(label),
        column_widths=column_widths,
    )


def pick_cell(column: int = 0) -> Callable:  # pragma: no cover
    """生成 ``Dataframe.select`` 处理器：返回选中行第 ``column`` 列的值。"""

    def _pick(data, evt: gr.SelectData):
        try:
            row = evt.index[0] if isinstance(evt.index, (list, tuple)) else int(evt.index)
            return str(data[row][column])
        except Exception:  # noqa: BLE001
            return ""

    return _pick


class Confirm:  # pragma: no cover
    """二步确认按钮：点击后原地展开「确认？ [确定] [取消]」，避免误触危险操作。

    用法::

        clear = Confirm("清空索引", "确认清空全部索引？此操作不可撤销。")
        clear.bind(handler, inputs, outputs)

    可选 ``on_open=(fn, inputs, outputs)`` 在展开确认条时先执行（如预览待删除项）。
    """

    def __init__(
        self,
        label: str,
        prompt: Optional[str] = None,
        *,
        variant: str = "stop",
        size: Optional[str] = None,
        min_width: int = 140,
        scale: int = 0,
        ok_label: str = "确定",
    ):
        with gr.Column(scale=scale, min_width=min_width, elem_classes=["cb-confirm-wrap"]):
            self.trigger = gr.Button(label, variant=variant, size=size, elem_classes=["cb-btn"])
            with gr.Row(visible=False, elem_classes=["cb-confirm"]) as self.row:
                self.prompt = gr.Markdown(prompt or f"确认{label}？")
                self.ok = gr.Button(ok_label, variant="stop", size="sm", elem_classes=["cb-btn"])
                self.cancel = gr.Button("取消", size="sm", elem_classes=["cb-btn"])
        self._open_hook: Optional[tuple] = None
        self.cancel.click(self._reset, None, [self.trigger, self.row], show_progress="hidden")

    @staticmethod
    def _open():
        return gr.update(visible=False), gr.update(visible=True)

    @staticmethod
    def _reset():
        return gr.update(visible=True), gr.update(visible=False)

    def on_open(self, fn: Callable, inputs=None, outputs=None) -> "Confirm":
        """展开确认条时先执行 ``fn``（例如把预览文案写入 ``outputs``）。"""
        self._open_hook = (fn, inputs, outputs)
        return self

    def bind(self, fn: Callable, inputs=None, outputs=None):
        """绑定确认后的动作；执行完自动收起确认条。返回事件依赖对象。"""
        ev = self.trigger.click(self._open, None, [self.trigger, self.row], show_progress="hidden")
        if self._open_hook:
            hook_fn, hook_in, hook_out = self._open_hook
            ev.then(hook_fn, hook_in, hook_out)
        dep = self.ok.click(fn, inputs, outputs)
        dep.then(self._reset, None, [self.trigger, self.row], show_progress="hidden")
        return dep


def toggle_visible(*flags: bool):  # pragma: no cover
    """把布尔列表映射为等长的 visible 更新。"""
    return tuple(gr.update(visible=bool(f)) for f in flags)
