#!/usr/bin/env python3
"""
项目桌面图标生成脚本

设计含义 (契合 Ollama qwen2.5-coder RAG + ReAct Agent + Multi-Agent 项目):
  - 深色科技圆角底盘   : 本地大模型推理底座 (Ollama)
  - 中央发光核心 </>    : 统一 LLM 内核 (qwen2.5-coder)
  - 围绕核心的 5 个节点 : Code / RAG / Test / Doc / Audit 多 Agent 协作
  - 节点连线           : MessageBus 消息总线 / RAG 检索连接
  - 青->蓝->品红渐变    : 明亮的科技感与智能流动

用法:
    python scripts/generate_icons.py

产物 (写入 assets/):
    icon_<size>.png   多尺寸 PNG (16/32/48/64/128/256/512/1024)
    icon.icns         macOS 应用图标
    icon.ico          Windows 图标
    icon.png          1024 主图 (= icon_1024.png)
"""
from __future__ import annotations

import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

# 主绘制分辨率 (高分辨率绘制后再降采样, 保证清晰)
BASE = 1024

# 颜色 (RGB)
C_BG_TOP = (14, 27, 58)
C_BG_BOT = (6, 11, 31)
C_CYAN = (34, 225, 255)
C_BLUE = (59, 130, 246)
C_MAGENTA = (168, 85, 247)
C_WHITE = (234, 246, 255)

# 5 个 Agent 节点 (角度, 颜色) —— 以中心为基准
NODES = [
    ((512, 218), C_CYAN),        # 顶  Code
    ((792, 408), (79, 141, 255)),  # 右上 RAG
    ((700, 760), (124, 92, 255)),  # 右下 Test
    ((324, 760), C_MAGENTA),       # 左下 Doc
    ((232, 408), (39, 198, 230)),  # 左上 Audit
]
CENTER = (512, 512)


def _lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _vertical_gradient(size, top, bottom):
    """生成竖直渐变背景 (用于圆角底盘)。"""
    grad = Image.new("RGB", (1, size), 0)
    for y in range(size):
        grad.putpixel((0, y), _lerp(top, bottom, y / max(1, size - 1)))
    return grad.resize((size, size))


def _rounded_mask(size, radius):
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def _radial_glow(size, color, alpha=235):
    """中心径向光晕 (RGBA)。"""
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    cx = cy = size / 2
    maxr = size / 2
    steps = 60
    for i in range(steps, 0, -1):
        r = maxr * i / steps
        a = int(alpha * (1 - i / steps) ** 1.6)
        d.ellipse([cx - r, cy - r, cy + r, cy + r], fill=color + (a,))
    return glow


def render_base() -> Image.Image:
    """以 BASE 分辨率绘制完整图标 (RGBA)。"""
    img = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))

    # --- 圆角底盘 (带竖直渐变) ---
    pad = 40
    inner = BASE - 2 * pad
    radius = 220
    grad = _vertical_gradient(inner, C_BG_TOP, C_BG_BOT)
    mask = _rounded_mask(inner, radius)
    plate = Image.new("RGBA", (inner, inner), (0, 0, 0, 0))
    plate.paste(grad, (0, 0), mask)
    img.paste(plate, (pad, pad), plate)

    draw = ImageDraw.Draw(img)

    # 底盘描边 (渐变近似: 用青到品红的两段)
    draw.rounded_rectangle(
        [pad, pad, BASE - pad, BASE - pad], radius=radius,
        outline=C_CYAN + (90,), width=6,
    )

    # --- 协作连线: 核心 -> 各节点 ---
    line_layer = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    ld = ImageDraw.Draw(line_layer)
    for (pt, col) in NODES:
        ld.line([CENTER, pt], fill=col + (150,), width=12)
    # 节点环形连线
    poly = [pt for pt, _ in NODES]
    ld.line(poly + [poly[0]], fill=C_BLUE + (90,), width=7, joint="curve")
    img.alpha_composite(line_layer)

    # --- 中央核心光晕 ---
    glow_r = 230
    glow = _radial_glow(glow_r * 2, C_CYAN, alpha=210)
    glow = glow.filter(ImageFilter.GaussianBlur(18))
    img.alpha_composite(glow, (CENTER[0] - glow_r, CENTER[1] - glow_r))

    # --- 中央核心 (径向渐变近似: 青->蓝->品红 同心圆) ---
    core_layer = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    cd = ImageDraw.Draw(core_layer)
    R = 150
    steps = R
    for i in range(steps, 0, -1):
        t = 1 - i / steps  # 0 中心 -> 1 边缘
        if t < 0.5:
            col = _lerp(C_CYAN, C_BLUE, t / 0.5)
        else:
            col = _lerp(C_BLUE, C_MAGENTA, (t - 0.5) / 0.5)
        r = R * i / steps
        cd.ellipse([CENTER[0] - r, CENTER[1] - r, CENTER[0] + r, CENTER[1] + r],
                   fill=col + (255,))
    cd.ellipse([CENTER[0] - R, CENTER[1] - R, CENTER[0] + R, CENTER[1] + R],
               outline=C_WHITE + (220,), width=6)
    img.alpha_composite(core_layer)

    # --- 核心内代码符号 </> ---
    draw = ImageDraw.Draw(img)
    w = 22
    draw.line([(470, 470), (422, 512), (470, 554)], fill=C_WHITE + (255,),
              width=w, joint="curve")
    draw.line([(554, 470), (602, 512), (554, 554)], fill=C_WHITE + (255,),
              width=w, joint="curve")
    draw.line([(538, 452), (486, 572)], fill=C_WHITE + (255,), width=w)

    # --- 5 个 Agent 节点 ---
    for (pt, col) in NODES:
        nr = 62
        # 轻微外发光
        ng = _radial_glow(nr * 3, col, alpha=120).filter(ImageFilter.GaussianBlur(10))
        img.alpha_composite(ng, (pt[0] - nr * 3 // 2, pt[1] - nr * 3 // 2))
        nd = ImageDraw.Draw(img)
        nd.ellipse([pt[0] - nr, pt[1] - nr, pt[0] + nr, pt[1] + nr], fill=col + (255,))
        nd.ellipse([pt[0] - nr, pt[1] - nr, pt[0] + nr, pt[1] + nr],
                   outline=C_WHITE + (230,), width=5)

    return img


def main():
    ASSETS.mkdir(exist_ok=True)
    base = render_base()

    sizes = [16, 32, 48, 64, 128, 256, 512, 1024]
    png_paths = {}
    for s in sizes:
        im = base.resize((s, s), Image.LANCZOS)
        p = ASSETS / f"icon_{s}.png"
        im.save(p)
        png_paths[s] = p
        print(f"  PNG  {p.relative_to(ROOT)}")

    # 主图
    main_png = ASSETS / "icon.png"
    base.resize((1024, 1024), Image.LANCZOS).save(main_png)
    print(f"  PNG  {main_png.relative_to(ROOT)}")

    # --- Windows .ico ---
    ico_path = ASSETS / "icon.ico"
    base.save(ico_path, format="ICO",
              sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"  ICO  {ico_path.relative_to(ROOT)}")

    # --- macOS .icns ---
    icns_path = ASSETS / "icon.icns"
    if sys.platform == "darwin" and _has(["iconutil"]):
        _build_icns_macos(base, icns_path)
    else:
        try:
            base.save(icns_path, format="ICNS")
            print(f"  ICNS {icns_path.relative_to(ROOT)} (Pillow)")
        except Exception as e:  # noqa: BLE001
            print(f"  [skip] .icns 生成失败: {e}")

    print("\n完成。图标资源位于 assets/")


def _has(cmd):
    from shutil import which
    return which(cmd[0]) is not None


def _build_icns_macos(base: Image.Image, out: Path):
    """使用 macOS iconutil 生成高质量 .icns。"""
    with tempfile.TemporaryDirectory() as td:
        iconset = Path(td) / "icon.iconset"
        iconset.mkdir()
        spec = [
            (16, "icon_16x16.png"), (32, "icon_16x16@2x.png"),
            (32, "icon_32x32.png"), (64, "icon_32x32@2x.png"),
            (128, "icon_128x128.png"), (256, "icon_128x128@2x.png"),
            (256, "icon_256x256.png"), (512, "icon_256x256@2x.png"),
            (512, "icon_512x512.png"), (1024, "icon_512x512@2x.png"),
        ]
        for size, name in spec:
            base.resize((size, size), Image.LANCZOS).save(iconset / name)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)],
                       check=True)
    print(f"  ICNS {out.relative_to(ROOT)} (iconutil)")


if __name__ == "__main__":
    main()
