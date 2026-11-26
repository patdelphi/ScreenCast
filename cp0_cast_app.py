#!/usr/bin/env python3
"""
程序说明：CardputerZero 网页控台与无线投屏画面测试一体化服务（cp0_cast_app.py）。

核心功能：
1. 帧缓冲显示输出：自动探测 CardputerZero 的 ST7789v3 帧缓冲（/dev/fb0，320×170 小端 RGB565，108,800 字节），
   通过 mmap 零拷贝刷新屏幕；在无 /dev/fb0 的桌面开发机上自动回退为内存虚拟显存。
2. 网页控台与开放推送接口：默认监听 0.0.0.0:8787，支持局域网任意设备通过 POST /push 推送 PNG/JPEG/BMP/WebP/GIF
   或原始 RGB565 帧，并提供双栏网页控台实时预览屏幕真实 16-bit 量化效果与在线调参。
3. 内置 10 类屏幕评估样张：涵盖 5 类常用 App UI 模拟、2 类自然/光影测试图与 3 类屏幕硬件标定卡，支持中英双语（设备端小屏简称）。
4. 机身键盘交互（evdev）：支持 4/5 键切换样张、6 键切换色彩模式、7 键开关角标、8/L 键中英切换、短按 ESC 回待机页、长按 ESC 退出。
5. 极简依赖：仅依赖 Python 标准库与 Pillow（可选 evdev），兼容 Python 3.11–3.13+。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import mmap
import os
import random
import re
import signal
import socket
import sys
import threading
import time
import zlib
from array import array
from collections import deque
from datetime import datetime
from email.parser import BytesParser
from email.policy import default as default_email_policy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFont, ImageOps

SCREEN_WIDTH = 320
SCREEN_HEIGHT = 170
FB_BPP = 16
FRAME_BYTES = SCREEN_WIDTH * SCREEN_HEIGHT * (FB_BPP // 8)  # 108,800 字节
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 单次最大允许上传 20 MB

UI_LANGS = ("zh", "en")
COLOR_MODES = ("rgb565", "rgb565_dither", "gray", "mono_floyd", "mono_threshold")
FIT_MODES = ("contain", "cover", "stretch")
ROTATE_VALUES = (0, 90, 180, 270)
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
HOST_RE = re.compile(r"^[A-Za-z0-9.\-:]+$")

# 预计算 RGB888 <-> RGB565 256 项高低字节查表，打包与解包全程走 Pillow C 层算子（零大表初始化开销）
_R_HI_LUT = [i & 0xF8 for i in range(256)]
_G_HI_LUT = [i >> 5 for i in range(256)]
_G_LO_LUT = [(i << 3) & 0xE0 for i in range(256)]
_B_LO_LUT = [i >> 3 for i in range(256)]

_R8_FROM_HI = [(((i >> 3) & 0x1F) << 3) | (((i >> 3) & 0x1F) >> 2) for i in range(256)]
_G8_FROM_HI = [((i & 0x07) << 5) | ((i & 0x07) >> 1) for i in range(256)]
_G8_FROM_LO = [((i >> 5) & 0x07) << 2 for i in range(256)]
_B8_FROM_LO = [((i & 0x1F) << 3) | ((i & 0x1F) >> 2) for i in range(256)]

# 机身屏幕正下方物理按键 4..8 的水平对齐中心像素坐标（实机标定）
NAV_KEY_CENTERS_X = (49, 105, 161, 217, 273)

# 8x8 Bayer 有序抖动矩阵（0..63），通过 Pillow ImageChops C 算子消除 16-bit RGB565 渐变色带且零闪烁
_BAYER_8X8: tuple[tuple[int, ...], ...] = (
    (0, 32, 8, 40, 2, 34, 10, 42),
    (48, 16, 56, 24, 50, 18, 58, 26),
    (12, 44, 4, 36, 14, 46, 6, 38),
    (60, 28, 52, 20, 62, 30, 54, 22),
    (3, 35, 11, 43, 1, 33, 9, 41),
    (51, 19, 59, 27, 49, 17, 57, 25),
    (15, 47, 7, 39, 13, 45, 5, 37),
    (63, 31, 55, 23, 61, 29, 53, 21),
)


def _build_bayer_dither_images() -> tuple[Image.Image, Image.Image]:
    """
    预构建 320×170 Bayer 正向与负向偏移图：
    R/B 通道(步长8)加 0..7 减 3；G 通道(步长4)加 0..3 减 1。
    保证纯黑(0 -> <=4 -> 0)和纯白(255 -> >=252 -> 31/63)不产生杂点，仅平滑中间调色带。
    """
    pos_buf = bytearray(SCREEN_WIDTH * SCREEN_HEIGHT * 3)
    neg_buf = bytearray(SCREEN_WIDTH * SCREEN_HEIGHT * 3)
    idx = 0
    for y in range(SCREEN_HEIGHT):
        brow = _BAYER_8X8[y & 7]
        for x in range(SCREEN_WIDTH):
            b = brow[x & 7]
            prb = (b * 7) // 63
            pg = (b * 3) // 63
            pos_buf[idx] = prb
            pos_buf[idx + 1] = pg
            pos_buf[idx + 2] = prb
            neg_buf[idx] = 3
            neg_buf[idx + 1] = 1
            neg_buf[idx + 2] = 3
            idx += 3
    return (
        Image.frombytes("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), bytes(pos_buf)),
        Image.frombytes("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), bytes(neg_buf)),
    )


_BAYER_POS_IMG, _BAYER_NEG_IMG = _build_bayer_dither_images()

CONFIG_SECTIONS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "# [网络与安全]",
        (
            ("UI_LANG", "界面显示语言：zh（中文）| en（英文）"),
            ("LISTEN_HOST", "Web 控台与推送 API 监听地址（0.0.0.0 允许局域网访问）"),
            ("LISTEN_PORT", "Web 控台与推送 API 监听端口（1-65535）"),
            ("CAST_TOKEN", "可选推送鉴权口令（对应请求头 X-Cast-Token，留空不启用）"),
            ("CAST_TIMEOUT_SEC", "无新画面自动回退待机页秒数（0 表示常驻保留当前画面便于观察）"),
        ),
    ),
    (
        "# [色彩与画面适配]",
        (
            ("TARGET_FPS", "推流帧率控制：0 表示不限速全速显示，1-120 表示固定目标帧率上限（视频播放/游戏推流）"),
            ("COLOR_MODE", "色彩渲染模式：rgb565 | rgb565_dither | gray | mono_floyd | mono_threshold"),
            ("FIT_MODE", "缩放策略：contain（等比留边）| cover（等比裁切铺满）| stretch（拉伸铺满）"),
            ("ROTATE", "顺时针旋转角度：0 | 90 | 180 | 270"),
            ("BG_COLOR", "contain 留边背景色（#RRGGBB）"),
            ("BRIGHTNESS", "亮度百分比（20-200，100 为原始亮度）"),
            ("CONTRAST", "对比度百分比（20-200，100 为原始对比度）"),
            ("SATURATION", "饱和度百分比（0-200，100 为原始饱和度）"),
            ("THRESHOLD", "mono_threshold 硬二值化阈值（0-255）"),
            ("INVERT", "是否反相画面颜色（true / false）"),
            ("SHOW_OVERLAY", "是否在设备屏幕右上角叠加模式与帧率角标（true / false）"),
        ),
    ),
)


def default_config() -> dict[str, Any]:
    """返回默认运行配置字典。"""
    return {
        "UI_LANG": "zh",
        "LISTEN_HOST": "0.0.0.0",
        "LISTEN_PORT": 8787,
        "CAST_TOKEN": "",
        "CAST_TIMEOUT_SEC": 0,
        "TARGET_FPS": 0,
        "COLOR_MODE": "rgb565",
        "FIT_MODE": "contain",
        "ROTATE": 0,
        "BG_COLOR": "#000000",
        "BRIGHTNESS": 100,
        "CONTRAST": 100,
        "SATURATION": 100,
        "THRESHOLD": 128,
        "INVERT": False,
        "SHOW_OVERLAY": False,
    }


def _strip_inline_comment(raw_val: str) -> str:
    """剥离 .env 非引号值末尾的行内注释（注意保留颜色值开头的 #RRGGBB）。"""
    text = raw_val.strip()
    if not text:
        return ""
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    if text.startswith("#") and len(text) >= 7 and HEX_COLOR_RE.match(text[:7]):
        rest = text[7:].strip()
        if not rest or rest.startswith("#"):
            return text[:7]
    if text.startswith("#"):
        return ""
    for idx, ch in enumerate(text):
        if ch == "#" and idx > 0 and text[idx - 1].isspace():
            return text[:idx].strip()
    return text


def _parse_bool(val: Any, fallback: bool = False) -> tuple[bool, bool]:
    if isinstance(val, bool):
        return val, True
    s = str(val).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True, True
    if s in ("0", "false", "no", "off"):
        return False, True
    return fallback, False


def _parse_int_range(val: Any, low: int, high: int) -> tuple[int, bool]:
    if isinstance(val, bool):
        return 0, False
    try:
        num = int(str(val).strip())
        if low <= num <= high:
            return num, True
    except (TypeError, ValueError):
        pass
    return 0, False


def validate_and_normalize_config(payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """校验并规范化全部配置项，返回 (规范化字典, 错误字段映射)。"""
    cfg = default_config()
    errors: dict[str, str] = {}

    raw_lang = str(payload.get("UI_LANG", cfg["UI_LANG"])).strip().lower()
    if raw_lang in ("cn", "zh-cn", "zh_cn"):
        raw_lang = "zh"
    if raw_lang not in UI_LANGS:
        errors["UI_LANG"] = "语言必须为 zh 或 en"
    else:
        cfg["UI_LANG"] = raw_lang

    host = str(payload.get("LISTEN_HOST", cfg["LISTEN_HOST"])).strip()
    if not host or not HOST_RE.match(host):
        errors["LISTEN_HOST"] = "监听地址需为合法 IP 或主机名"
    else:
        cfg["LISTEN_HOST"] = host

    port, ok = _parse_int_range(payload.get("LISTEN_PORT", cfg["LISTEN_PORT"]), 1, 65535)
    if not ok:
        errors["LISTEN_PORT"] = "监听端口需为 1–65535 整数"
    else:
        cfg["LISTEN_PORT"] = port

    token = str(payload.get("CAST_TOKEN", cfg["CAST_TOKEN"]))
    if any(ord(c) < 32 or ord(c) == 127 for c in token):
        errors["CAST_TOKEN"] = "Token 不能包含换行或控制字符"
    else:
        cfg["CAST_TOKEN"] = token.strip()

    timeout_sec, ok = _parse_int_range(payload.get("CAST_TIMEOUT_SEC", cfg["CAST_TIMEOUT_SEC"]), 0, 86400)
    if not ok:
        errors["CAST_TIMEOUT_SEC"] = "回退超时需为 0–86400 整数"
    else:
        cfg["CAST_TIMEOUT_SEC"] = timeout_sec

    color_mode = str(payload.get("COLOR_MODE", cfg["COLOR_MODE"])).strip().lower()
    if color_mode not in COLOR_MODES:
        errors["COLOR_MODE"] = f"色彩模式必须属于 {', '.join(COLOR_MODES)}"
    else:
        cfg["COLOR_MODE"] = color_mode

    fit_mode = str(payload.get("FIT_MODE", cfg["FIT_MODE"])).strip().lower()
    if fit_mode not in FIT_MODES:
        errors["FIT_MODE"] = f"缩放模式必须属于 {', '.join(FIT_MODES)}"
    else:
        cfg["FIT_MODE"] = fit_mode

    rot_val, ok = _parse_int_range(payload.get("ROTATE", cfg["ROTATE"]), 0, 270)
    if not ok or rot_val not in ROTATE_VALUES:
        errors["ROTATE"] = "旋转角度需为 0、90、180 或 270"
    else:
        cfg["ROTATE"] = rot_val

    bg_color = str(payload.get("BG_COLOR", cfg["BG_COLOR"])).strip()
    if not HEX_COLOR_RE.match(bg_color):
        errors["BG_COLOR"] = "背景色需为 #RRGGBB 十六进制颜色"
    else:
        cfg["BG_COLOR"] = bg_color.upper()

    for key, label, low, high in (
        ("TARGET_FPS", "目标帧率", 0, 120),
        ("BRIGHTNESS", "亮度", 20, 200),
        ("CONTRAST", "对比度", 20, 200),
        ("SATURATION", "饱和度", 0, 200),
        ("THRESHOLD", "阈值", 0, 255),
    ):
        num, ok = _parse_int_range(payload.get(key, cfg[key]), low, high)
        if not ok:
            errors[key] = f"{label}需为 {low}–{high} 整数"
        else:
            cfg[key] = num

    for bkey, blabel in (("INVERT", "反相"), ("SHOW_OVERLAY", "角标开关")):
        bval, ok = _parse_bool(payload.get(bkey, cfg[bkey]), cfg[bkey])
        if not ok:
            errors[bkey] = f"{blabel}需为布尔值"
        else:
            cfg[bkey] = bval

    return cfg, errors


def load_env_config(env_path: Path) -> dict[str, Any]:
    """从 .env 文件读取配置，缺省或非法字段回退默认值。"""
    raw_map: dict[str, Any] = default_config()
    if env_path.is_file():
        text = env_path.read_text(encoding="utf-8-sig", errors="replace")
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("export "):
                stripped = stripped[7:].strip()
            if "=" not in stripped:
                continue
            k, v = stripped.split("=", 1)
            key = k.strip()
            if key in raw_map:
                raw_map[key] = _strip_inline_comment(v)
    normalized, errors = validate_and_normalize_config(raw_map)
    if errors:
        fallback = default_config()
        for err_key in errors:
            raw_map[err_key] = fallback[err_key]
        normalized, _ = validate_and_normalize_config(raw_map)
    return normalized


def save_env_config(env_path: Path, config: Mapping[str, Any]) -> None:
    """将配置以带对齐中文备注的无 BOM + CRLF 格式写回 .env。"""
    normalized, errors = validate_and_normalize_config(config)
    if errors:
        raise ValueError(f"配置存在非法字段: {errors}")

    lines: list[str] = ["# CardputerZero 网页控台与无线投屏测试服务配置文件 (.env)", ""]
    for section_title, items in CONFIG_SECTIONS:
        lines.append(section_title)
        for key, comment in items:
            val = normalized[key]
            val_str = ("true" if val else "false") if isinstance(val, bool) else str(val)
            lhs = f"{key}={val_str}"
            pad = " " * max(2, 29 - len(lhs))
            lines.append(f"{lhs}{pad}# {comment}")
        lines.append("")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    content = "\r\n".join(lines).rstrip("\r\n") + "\r\n"
    env_path.write_bytes(content.encode("utf-8"))


# ---------------------------------------------------------------------------
# 字体加载缓存（自动适配 CardputerZero Debian NotoSansCJK 与 Windows 雅黑）
# ---------------------------------------------------------------------------
_FONT_CACHE: dict[tuple[int, bool], ImageFont.ImageFont] = {}


def _find_font_path(mono: bool = False) -> Path | None:
    ui_candidates = (
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    mono_candidates = (
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc"),
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
        Path(r"C:\Windows\Fonts\consola.ttf"),
    ) + ui_candidates
    for p in (mono_candidates if mono else ui_candidates):
        if p.is_file():
            return p
    return None


def _get_font(size: int, mono: bool = False) -> ImageFont.ImageFont:
    key = (size, mono)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    fpath = _find_font_path(mono=mono)
    if fpath is not None:
        try:
            font = ImageFont.truetype(str(fpath), size)
            _FONT_CACHE[key] = font
            return font
        except Exception:
            pass
    font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


# ---------------------------------------------------------------------------
# RGB565 量化、Bayer 抖动与图像处理管线
# ---------------------------------------------------------------------------
def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    s = hex_str.lstrip("#")
    if len(s) != 6:
        return (0, 0, 0)
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def rgb888_to_rgb565_bytes(img: Image.Image, dither: bool = False) -> bytes:
    """
    将 PIL 图像转换为 320×170 小端序 16-bit RGB565 字节流（108,800 字节）。
    利用 Pillow C 层 point + ImageChops.add + LA 双通道合并直接生成 [lo, hi] 小端字节流，
    在 ARM64 Cortex-A53 上单帧仅需约 0.3 ms。
    """
    if img.size != (SCREEN_WIDTH, SCREEN_HEIGHT):
        img = img.resize((SCREEN_WIDTH, SCREEN_HEIGHT), Image.Resampling.LANCZOS)
    if img.mode != "RGB":
        img = img.convert("RGB")

    if dither:
        img = ImageChops.subtract(ImageChops.add(img, _BAYER_POS_IMG), _BAYER_NEG_IMG)

    r_ch, g_ch, b_ch = img.split()
    hi = ImageChops.add(r_ch.point(_R_HI_LUT), g_ch.point(_G_HI_LUT))
    lo = ImageChops.add(g_ch.point(_G_LO_LUT), b_ch.point(_B_LO_LUT))
    return Image.merge("LA", (lo, hi)).tobytes()


def rgb565_bytes_to_image(raw: bytes, width: int = SCREEN_WIDTH, height: int = SCREEN_HEIGHT) -> Image.Image:
    """将小端 RGB565 帧字节通过 Pillow C 层通道映射还原为 8-bit RGB 图像。"""
    expected = width * height * 2
    if len(raw) != expected:
        raise ValueError(f"RGB565 字节长度应为 {expected}，实际收到 {len(raw)}")
    lo, hi = Image.frombytes("LA", (width, height), raw).split()
    r8 = hi.point(_R8_FROM_HI)
    g8 = ImageChops.add(hi.point(_G8_FROM_HI), lo.point(_G8_FROM_LO))
    b8 = lo.point(_B8_FROM_LO)
    return Image.merge("RGB", (r8, g8, b8))


def _fit_to_screen(img: Image.Image, fit_mode: str, bg_rgb: tuple[int, int, int]) -> Image.Image:
    target = (SCREEN_WIDTH, SCREEN_HEIGHT)
    if img.size == target and fit_mode in ("contain", "cover", "stretch"):
        return img.convert("RGB")
    rgb_img = img.convert("RGB")
    if fit_mode == "stretch":
        return rgb_img.resize(target, Image.Resampling.LANCZOS)
    if fit_mode == "cover":
        return ImageOps.fit(rgb_img, target, method=Image.Resampling.LANCZOS)
    contained = ImageOps.contain(rgb_img, target, method=Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", target, bg_rgb)
    ox = (SCREEN_WIDTH - contained.width) // 2
    oy = (SCREEN_HEIGHT - contained.height) // 2
    canvas.paste(contained, (ox, oy))
    return canvas


def process_image_to_frame(
    src_img: Image.Image,
    config: Mapping[str, Any],
    overlay_text: str = "",
    include_preview_png: bool = True,
) -> tuple[bytes, bytes, str]:
    """
    执行完整图像处理管线：旋转 -> 缩放适配 -> 亮度/对比度/饱和度 -> 反相 -> 色彩模式 -> RGB565 打包。
    include_preview_png=False 时跳过 PNG 压缩，交由 /preview.png 按需惰性生成以消除高频推流 CPU 瓶颈。
    返回: (rgb565_bytes, preview_png_bytes, sha256_hex)
    """
    working = src_img if src_img.mode == "RGB" else src_img.convert("RGB")
    rot = int(config.get("ROTATE", 0))
    if rot in (90, 180, 270):
        working = working.rotate(-rot, expand=True)

    bg_rgb = _hex_to_rgb(str(config.get("BG_COLOR", "#000000")))
    if working.size != (SCREEN_WIDTH, SCREEN_HEIGHT):
        working = _fit_to_screen(working, str(config.get("FIT_MODE", "contain")), bg_rgb)

    brightness = int(config.get("BRIGHTNESS", 100))
    if brightness != 100:
        working = ImageEnhance.Brightness(working).enhance(brightness / 100.0)

    contrast = int(config.get("CONTRAST", 100))
    if contrast != 100:
        working = ImageEnhance.Contrast(working).enhance(contrast / 100.0)

    saturation = int(config.get("SATURATION", 100))
    if saturation != 100:
        working = ImageEnhance.Color(working).enhance(saturation / 100.0)

    if bool(config.get("INVERT", False)):
        working = ImageOps.invert(working)

    color_mode = str(config.get("COLOR_MODE", "rgb565")).lower()
    dither_565 = False
    if color_mode == "rgb565_dither":
        dither_565 = True
    elif color_mode == "gray":
        working = working.convert("L").convert("RGB")
    elif color_mode == "mono_floyd":
        working = working.convert("L").convert("1", dither=Image.Dither.FLOYDSTEINBERG).convert("RGB")
    elif color_mode == "mono_threshold":
        thresh = int(config.get("THRESHOLD", 128))
        lut = [0 if i < thresh else 255 for i in range(256)]
        working = working.convert("L").point(lut).convert("RGB")

    if overlay_text:
        if working is src_img:
            working = working.copy()
        draw = ImageDraw.Draw(working)
        f_small = _get_font(11)
        bbox = draw.textbbox((0, 0), overlay_text, font=f_small)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        bx0 = max(2, SCREEN_WIDTH - tw - 12)
        draw.rounded_rectangle((bx0, 3, SCREEN_WIDTH - 3, th + 9), radius=4, fill=(12, 16, 22), outline=(90, 110, 135))
        draw.text((bx0 + 5 - bbox[0], 6 - bbox[1]), overlay_text, font=f_small, fill=(230, 238, 248))

    rgb565_bytes = rgb888_to_rgb565_bytes(working, dither=dither_565)
    png_bytes = b""
    if include_preview_png:
        quantized_preview = rgb565_bytes_to_image(rgb565_bytes)
        png_buf = io.BytesIO()
        quantized_preview.save(png_buf, format="PNG", compress_level=1)
        png_bytes = png_buf.getvalue()
    sha256_hex = hashlib.sha256(rgb565_bytes).hexdigest()
    return rgb565_bytes, png_bytes, sha256_hex


# ---------------------------------------------------------------------------
# 内置 10 类 320×170 屏幕评估样张库（中英双语紧凑简称，适配 320×170 小屏）
# ---------------------------------------------------------------------------
SAMPLE_PATTERNS: tuple[dict[str, str], ...] = (
    {
        "id": "ui_launcher",
        "category": "app_ui",
        "title_zh": "启动器列表 UI",
        "title_en": "Launcher UI",
        "desc_zh": "顶栏 + 高亮列表 + 底部 4-8 键栏，测试行高与选中对比度",
        "desc_en": "Top bar, active list rows & 4-8 nav bar for row height & contrast",
    },
    {
        "id": "ui_dashboard",
        "category": "app_ui",
        "title_zh": "系统监控看板",
        "title_en": "SysMon UI",
        "desc_zh": "暗色卡片 + 4 路进度条 + 双圆环 + 折线图，测试多指标密度",
        "desc_en": "Dark cards, 4 progress bars, dual rings & sparkline density test",
    },
    {
        "id": "ui_terminal",
        "category": "app_ui",
        "title_zh": "SSH 终端日志",
        "title_en": "SSH Term UI",
        "desc_zh": "11px 多色命令行高亮与状态底栏，评估小屏终端可读行数",
        "desc_en": "11px ANSI colored logs & status bar for terminal readability",
    },
    {
        "id": "ui_radio_spectrum",
        "category": "app_ui",
        "title_zh": "频谱瀑布工具",
        "title_en": "SDR Spectrum",
        "desc_zh": "实时 FFT 频谱峰值曲线 + 伪彩色瀑布热力图，测试高密像素",
        "desc_en": "Live FFT peak curve & false-color waterfall heatmap test",
    },
    {
        "id": "ui_chat_reader",
        "category": "app_ui",
        "title_zh": "AI 气泡阅读",
        "title_en": "AI Chat UI",
        "desc_zh": "双色对话气泡与 12px 多行正文，测试长句行距与阅读舒适度",
        "desc_en": "Dual chat bubbles & 12px multi-line body text spacing test",
    },
    {
        "id": "photo_sunset",
        "category": "photo",
        "title_zh": "风景：日落山湖",
        "title_en": "Photo: Sunset",
        "desc_zh": "暖橙晚霞连续渐变、远山剪影与湖面波纹，检验自然色彩与色带",
        "desc_en": "Smooth twilight sky gradient, mountain ridges & water ripples",
    },
    {
        "id": "photo_cyber_city",
        "category": "photo",
        "title_zh": "光影：霓虹球体",
        "title_en": "Photo: Spheres",
        "desc_zh": "3D 高光阴影球体与高饱和青紫网格，检验 IPS 饱和度与暗部",
        "desc_en": "3D shaded glossy spheres & neon grid for gamut & shadow depth",
    },
    {
        "id": "cal_color_bars",
        "category": "calibration",
        "title_zh": "标定：彩条灰阶",
        "title_en": "Cal: ColorBars",
        "desc_zh": "8 色饱和彩条 + 16 级灰阶 + 近黑/近白死区分辨块",
        "desc_en": "8 SMPTE color bars, 16-step gray ramp & black/white clipping",
    },
    {
        "id": "cal_gradients",
        "category": "calibration",
        "title_zh": "标定：色带对比",
        "title_en": "Cal: Gradients",
        "desc_zh": "R/G/B/Gray 连续渐变，切换 rgb565 与 dither 直接对比条纹消除",
        "desc_en": "R/G/B/Gray 0-255 ramps to compare RGB565 banding vs dither",
    },
    {
        "id": "cal_typography_grid",
        "category": "calibration",
        "title_zh": "标定：字号安全框",
        "title_en": "Cal: Font & Grid",
        "desc_zh": "1px 红青贴边框检查外壳遮挡 + 明暗双底 10-18px 字号对照",
        "desc_en": "1px outer bezel check frame & dark/light 10-18px font chart",
    },
)


def list_sample_patterns(lang: str = "zh") -> list[dict[str, str]]:
    """返回全部内置样张元数据（按指定语言填充 title / desc，同时附带双语字段）。"""
    use_en = str(lang).lower() == "en"
    out: list[dict[str, str]] = []
    for item in SAMPLE_PATTERNS:
        entry = dict(item)
        entry["title"] = item["title_en"] if use_en else item["title_zh"]
        entry["desc"] = item["desc_en"] if use_en else item["desc_zh"]
        out.append(entry)
    return out


def _clamp_u8(val: float) -> int:
    if val <= 0.0:
        return 0
    if val >= 255.0:
        return 255
    return int(val)


def _draw_nav_footer(draw: ImageDraw.ImageDraw, items: tuple[str, ...], bg: tuple[int, int, int] = (20, 24, 31)) -> None:
    """绘制 CardputerZero 底部 4-8 快捷键栏（按实机按键物理中心坐标精准对齐）。"""
    y0 = SCREEN_HEIGHT - 22
    draw.rectangle((0, y0, SCREEN_WIDTH - 1, SCREEN_HEIGHT - 1), fill=bg)
    draw.line((0, y0, SCREEN_WIDTH - 1, y0), fill=(52, 62, 76), width=1)
    f = _get_font(11)
    centers = NAV_KEY_CENTERS_X if len(items) == 5 else tuple(
        idx * (SCREEN_WIDTH // len(items)) + (SCREEN_WIDTH // len(items)) // 2 for idx in range(len(items))
    )
    for cx, label in zip(centers, items):
        bbox = draw.textbbox((0, 0), label, font=f)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = max(2, min(SCREEN_WIDTH - tw - 2, cx - tw // 2)) - bbox[0]
        draw.text((tx, y0 + (22 - th) // 2 - bbox[1]), label, font=f, fill=(205, 216, 230))


def _gen_ui_launcher(lang: str = "zh") -> Image.Image:
    en = lang == "en"
    img = Image.new("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), (16, 18, 24))
    draw = ImageDraw.Draw(img)
    f_title = _get_font(13)
    f_item = _get_font(13)
    f_sub = _get_font(10)

    draw.rectangle((0, 0, 319, 23), fill=(24, 28, 36))
    draw.line((0, 23, 319, 23), fill=(50, 60, 74))
    draw.text((8, 4), "CP0 Launcher" if en else "CP0 启动器", font=f_title, fill=(235, 240, 246))
    draw.rounded_rectangle((222, 4, 264, 19), radius=4, fill=(26, 56, 44), outline=(56, 189, 126))
    draw.text((229, 5), "WiFi", font=f_sub, fill=(99, 226, 183))
    draw.rounded_rectangle((270, 4, 312, 19), radius=4, fill=(32, 44, 62), outline=(96, 165, 250))
    draw.text((277, 5), "86%", font=f_sub, fill=(147, 197, 253))

    rows = (
        (
            ("ScreenCast", "Live · 192.168.31.251:8787", (24, 160, 88), True),
            ("ZeroRadio", "RTL-SDR / ADS-B / AIS", (56, 139, 253), False),
            ("SysMon SSH", "Deb13 ARM64 · Load 0.24", (240, 160, 32), False),
        )
        if en
        else (
            ("投屏测试控台", "在线 · 192.168.31.251:8787", (24, 160, 88), True),
            ("ZeroRadio 电台", "RTL-SDR / ADS-B / AIS", (56, 139, 253), False),
            ("SSH 节点监控", "Deb13 ARM64 · 负载 0.24", (240, 160, 32), False),
        )
    )
    for idx, (title, sub, dot_col, active) in enumerate(rows):
        y = 29 + idx * 38
        if active:
            draw.rounded_rectangle((6, y, 313, y + 34), radius=6, fill=(24, 46, 38), outline=(62, 207, 142), width=1)
            draw.rounded_rectangle((9, y + 5, 13, y + 29), radius=2, fill=(99, 226, 183))
        else:
            draw.rounded_rectangle((6, y, 313, y + 34), radius=6, fill=(24, 28, 36), outline=(44, 52, 64), width=1)
        draw.ellipse((20, y + 9, 36, y + 25), fill=dot_col)
        draw.text((44, y + 3), title, font=f_item, fill=(242, 246, 250) if active else (215, 222, 232))
        draw.text((44, y + 19), sub, font=f_sub, fill=(154, 214, 186) if active else (138, 148, 164))

    _draw_nav_footer(draw, ("4 Up", "5 Dn", "6 Thm", "7 Info", "8 Run") if en else ("4 上移", "5 下移", "6 主题", "7 详情", "8 打开"))
    return img


def _gen_ui_dashboard(lang: str = "zh") -> Image.Image:
    en = lang == "en"
    img = Image.new("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), (13, 17, 23))
    draw = ImageDraw.Draw(img)
    f_h = _get_font(12)
    f_xs = _get_font(10)

    draw.rectangle((0, 0, 319, 21), fill=(22, 27, 34))
    draw.text((7, 3), "CP0 SysMon" if en else "CP0 监控", font=f_h, fill=(230, 237, 243))
    draw.rounded_rectangle((262, 3, 313, 18), radius=4, fill=(45, 32, 18), outline=(240, 160, 32))
    draw.text((269, 4), "51.2°C", font=f_xs, fill=(248, 198, 96))

    draw.rounded_rectangle((5, 26, 172, 142), radius=6, fill=(22, 27, 34), outline=(48, 54, 61))
    bars = (
        (
            ("CPU 4C", 0.42, "42%", (56, 189, 248)),
            ("RAM 352M", 0.64, "225M", (52, 211, 153)),
            ("Swap 863M", 0.19, "164M", (167, 139, 250)),
            ("Disk 29G", 0.25, "7.3G", (251, 191, 36)),
        )
        if en
        else (
            ("CPU 4核", 0.42, "42%", (56, 189, 248)),
            ("内存 352M", 0.64, "225M", (52, 211, 153)),
            ("交换 863M", 0.19, "164M", (167, 139, 250)),
            ("存储 29G", 0.25, "7.3G", (251, 191, 36)),
        )
    )
    for i, (label, ratio, val_txt, col) in enumerate(bars):
        by = 33 + i * 26
        draw.text((12, by), label, font=f_xs, fill=(180, 190, 202))
        vb = draw.textbbox((0, 0), val_txt, font=f_xs)
        draw.text((165 - (vb[2] - vb[0]), by), val_txt, font=f_xs, fill=(230, 237, 243))
        draw.rounded_rectangle((12, by + 14, 165, by + 21), radius=3, fill=(38, 45, 56))
        fw = max(6, int(153 * ratio))
        draw.rounded_rectangle((12, by + 14, 12 + fw, by + 21), radius=3, fill=col)

    draw.rounded_rectangle((177, 26, 314, 86), radius=6, fill=(22, 27, 34), outline=(48, 54, 61))
    rings = (("WiFi", 88, (74, 222, 128)), ("BAT" if en else "电池", 91, (96, 165, 250)))
    for idx, (name, pct, col) in enumerate(rings):
        cx = 212 + idx * 68
        cy = 50
        r = 18
        draw.arc((cx - r, cy - r, cx + r, cy + r), 0, 360, fill=(42, 50, 62), width=5)
        draw.arc((cx - r, cy - r, cx + r, cy + r), -90, -90 + int(360 * pct / 100), fill=col, width=5)
        t = f"{pct}%"
        tb = draw.textbbox((0, 0), t, font=f_xs)
        draw.text((cx - (tb[2] - tb[0]) // 2, cy - 6), t, font=f_xs, fill=(236, 242, 248))
        nb = draw.textbbox((0, 0), name, font=f_xs)
        draw.text((cx - (nb[2] - nb[0]) // 2, cy + 19), name, font=f_xs, fill=(148, 163, 184))

    draw.rounded_rectangle((177, 90, 314, 142), radius=6, fill=(22, 27, 34), outline=(48, 54, 61))
    draw.text((184, 94), "RX  2.4 MB/s" if en else "下行  2.4 MB/s", font=f_xs, fill=(125, 211, 252))
    samples = (18, 24, 21, 32, 28, 39, 35, 42, 31, 45, 40, 48, 44)
    pts = [(184 + idx * 10, 136 - int(v * 0.55)) for idx, v in enumerate(samples)]
    draw.polygon([(184, 137)] + pts + [(pts[-1][0], 137)], fill=(18, 54, 76))
    draw.line(pts, fill=(56, 189, 248), width=2)

    _draw_nav_footer(draw, ("4 Stat", "5 Proc", "6 Net", "7 Sens", "8 Sync") if en else ("4 概览", "5 进程", "6 网络", "7 传感", "8 刷新"))
    return img


def _gen_ui_terminal(lang: str = "zh") -> Image.Image:
    en = lang == "en"
    img = Image.new("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), (10, 14, 20))
    draw = ImageDraw.Draw(img)
    f_mono = _get_font(11, mono=True)
    f_bar = _get_font(10, mono=True)

    draw.rectangle((0, 0, 319, 16), fill=(26, 32, 44))
    draw.text((6, 2), "pi@CP0: ~/screen-cast (tty1)" if en else "pi@CP0: ~/screen-cast (终端1)", font=f_bar, fill=(190, 205, 225))

    lines: tuple[tuple[tuple[str, tuple[int, int, int]], ...], ...] = (
        (("pi@cp0", (74, 222, 128)), (":", (200, 208, 218)), ("~$ ", (96, 165, 250)), ("systemctl status cast", (238, 242, 246))),
        (("[  OK  ] ", (74, 222, 128)), ("FB /dev/fb0 320x170 RGB565", (210, 218, 228))),
        (("[  OK  ] ", (74, 222, 128)), ("Web http://192.168.31.251:8787", (125, 211, 252))),
        (("[ INFO ] ", (96, 165, 250)), ("keypad: tca8418c (event3)", (200, 210, 222))),
        (("[ WARN ] ", (250, 204, 21)), ("wlan0 -58dBm  avail=134MB", (245, 225, 140))),
        (("[ PUSH ] ", (192, 132, 252)), ("POST /push 108800B  3.8ms  26FPS", (226, 232, 240))),
        (("[ ERR  ] ", (248, 113, 113)), ("bad token from 192.168.31.88", (252, 165, 165))),
        (("pi@cp0", (74, 222, 128)), (":", (200, 208, 218)), ("~$ ", (96, 165, 250)), ("free -h | grep Mem █", (238, 242, 246))),
    )
    for row_idx, segs in enumerate(lines):
        x = 6
        y = 20 + row_idx * 16
        for text, col in segs:
            draw.text((x, y), text, font=f_mono, fill=col)
            bb = draw.textbbox((0, 0), text, font=f_mono)
            x += bb[2] - bb[0]

    draw.rectangle((0, 154, 319, 169), fill=(22, 101, 52))
    foot = "[0] bash*  1:cast  CPU:14%  MEM:218M  23:28" if en else "[0] 终端*  1:投屏  CPU:14%  内存:218M  23:28"
    draw.text((6, 156), foot, font=f_bar, fill=(240, 253, 244))
    return img


def _gen_ui_radio_spectrum(lang: str = "zh") -> Image.Image:
    en = lang == "en"
    buf = bytearray(SCREEN_WIDTH * SCREEN_HEIGHT * 3)
    for i in range(0, len(buf), 3):
        buf[i] = 10
        buf[i + 1] = 14
        buf[i + 2] = 22

    peaks = ((0.22, 0.022, 0.95), (0.48, 0.035, 1.0), (0.71, 0.016, 0.78), (0.86, 0.020, 0.62))
    xs = [x / (SCREEN_WIDTH - 1) for x in range(SCREEN_WIDTH)]
    spec = []
    for x_norm in xs:
        val = 0.14
        for pos, width, amp in peaks:
            val += amp * math.exp(-0.5 * ((x_norm - pos) / width) ** 2)
        spec.append(min(1.0, max(0.0, val)))

    rng = random.Random(42)
    for row in range(68):
        drift = 0.004 * math.sin(row * 0.22)
        row_base = (78 + row) * SCREEN_WIDTH * 3
        for x_idx, x_norm in enumerate(xs):
            val = 0.12 + rng.uniform(-0.05, 0.07)
            for pos, width, amp in peaks:
                mod = 0.85 + 0.15 * math.cos(row * 0.35 + pos * 10.0)
                val += (amp * mod) * math.exp(-0.5 * ((x_norm - (pos + drift)) / width) ** 2)
            v = min(1.0, max(0.0, val))
            p = row_base + x_idx * 3
            buf[p] = _clamp_u8((v - 0.45) * 2.4 * 255.0)
            buf[p + 1] = _clamp_u8((1.0 - abs(v - 0.55) * 2.3) * 255.0)
            buf[p + 2] = _clamp_u8(max(0.12, (0.65 - v) * 2.0) * 255.0)

    img = Image.frombytes("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), bytes(buf))
    draw = ImageDraw.Draw(img)
    f_freq = _get_font(14)
    f_xs = _get_font(10)

    draw.rectangle((0, 0, 319, 21), fill=(18, 24, 34))
    draw.text((7, 2), "101.700 MHz", font=f_freq, fill=(103, 232, 249))
    draw.rounded_rectangle((112, 4, 146, 18), radius=3, fill=(22, 78, 99))
    draw.text((117, 5), "WFM", font=f_xs, fill=(207, 250, 254))
    draw.text((196, 5), "-46 dBm  SNR 29dB", font=f_xs, fill=(134, 239, 172))

    for gy in (34, 48, 62):
        draw.line((0, gy, 319, gy), fill=(26, 36, 50))
    for gx in range(40, 320, 40):
        draw.line((gx, 22, gx, 76), fill=(26, 36, 50))

    pts = [(x, int(74 - spec[x] * 48)) for x in range(SCREEN_WIDTH)]
    draw.polygon([(0, 75)] + pts + [(319, 75)], fill=(14, 62, 82))
    draw.line(pts, fill=(56, 224, 248), width=1)
    cx = int(0.48 * SCREEN_WIDTH)
    draw.line((cx, 22, cx, 146), fill=(248, 113, 113), width=1)
    draw.line((0, 77, 319, 77), fill=(64, 80, 102), width=1)

    _draw_nav_footer(draw, ("4 Step", "5 BW", "6 SQL", "7 Gain", "8 Save") if en else ("4 步进", "5 带宽", "6 静噪", "7 增益", "8 书签"))
    return img


def _gen_ui_chat_reader(lang: str = "zh") -> Image.Image:
    en = lang == "en"
    img = Image.new("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), (17, 20, 27))
    draw = ImageDraw.Draw(img)
    f_h = _get_font(12)
    f_body = _get_font(12)
    f_xs = _get_font(10)

    draw.rectangle((0, 0, 319, 21), fill=(25, 30, 40))
    draw.text((8, 3), "ZClaw AI · Reader" if en else "ZClaw 助手 · 阅读", font=f_h, fill=(232, 238, 246))
    draw.text((266, 5), "12px UI" if en else "12px 字号", font=f_xs, fill=(148, 163, 184))

    draw.rounded_rectangle((92, 27, 312, 53), radius=8, fill=(21, 94, 117), outline=(34, 211, 238))
    draw.text((102, 33), "Best font size on 320x170?" if en else "320×170 推荐多大正文字号？", font=f_body, fill=(236, 254, 255))

    draw.rounded_rectangle((8, 59, 308, 138), radius=8, fill=(28, 34, 46), outline=(58, 70, 90))
    reply_lines = (
        (
            "Use 12-14px sans-serif for body,",
            "min 10px for hints. Dark #11141B",
            "bg + #E6EDF3 text stays crisp and",
            "comfortable in low-light rooms.",
        )
        if en
        else (
            "建议正文用 12–14px 中黑体，辅助字",
            "最小 10px；深底 #11141B 搭配浅白",
            "#E6EDF3 文字，兼顾近距离锐度与暗",
            "光阅读舒适度。",
        )
    )
    for idx, line in enumerate(reply_lines):
        draw.text((17, 65 + idx * 17), line, font=f_body, fill=(228, 234, 242))

    draw.rounded_rectangle((6, 143, 313, 166), radius=6, fill=(12, 15, 21), outline=(64, 76, 96))
    draw.text((14, 148), "> Ask ZClaw..." if en else "> 输入问题...", font=f_xs, fill=(140, 154, 174))
    draw.rounded_rectangle((268, 146, 309, 163), radius=4, fill=(24, 160, 88))
    draw.text((275 if en else 277, 148), "Send" if en else "发送", font=f_xs, fill=(255, 255, 255))
    return img


def _gen_photo_sunset(_lang: str = "zh") -> Image.Image:
    """合成自然日落晚霞、远近山脊剪影与湖面波纹倒影测试照片。"""
    buf = bytearray(SCREEN_WIDTH * SCREEN_HEIGHT * 3)
    horizon = 0.64
    h_idx = int(horizon * SCREEN_HEIGHT)
    sun_x, sun_y = 0.62, 0.44
    aspect = SCREEN_WIDTH / SCREEN_HEIGHT

    xs = [x / (SCREEN_WIDTH - 1) for x in range(SCREEN_WIDTH)]
    m1_arr = [0.49 + 0.055 * math.sin(xn * 7.5 + 0.4) + 0.025 * math.cos(xn * 17.0) for xn in xs]
    m2_arr = [0.55 + 0.045 * math.sin(xn * 10.5 + 2.1) + 0.020 * math.sin(xn * 23.0) for xn in xs]
    m3_arr = [0.60 + 0.032 * math.cos(xn * 13.0 + 1.1) + 0.012 * math.sin(xn * 31.0) for xn in xs]

    for yi in range(h_idx):
        yn = yi / (SCREEN_HEIGHT - 1)
        t = min(1.0, max(0.0, yn / horizon))
        base_r = 24.0 + 226.0 * (t**1.35)
        base_g = 28.0 + 148.0 * (t**2.1) + 35.0 * math.exp(-(((t - 0.88) / 0.14) ** 2))
        base_b = 88.0 + 95.0 * math.sin(t * math.pi * 0.85) * (1.0 - 0.55 * t)
        dy2 = (yn - sun_y) ** 2
        row_off = yi * SCREEN_WIDTH * 3

        for xi, xn in enumerate(xs):
            p = row_off + xi * 3
            if yn >= m3_arr[xi]:
                buf[p], buf[p + 1], buf[p + 2] = 22, 18, 34
                continue
            if yn >= m2_arr[xi]:
                buf[p], buf[p + 1], buf[p + 2] = 46, 30, 58
                continue

            dist = math.sqrt(((xn - sun_x) * aspect) ** 2 + dy2)
            glow = math.exp(-dist * 5.2)
            disc = min(1.0, max(0.0, (0.085 - dist) * 90.0))
            r = base_r + glow * 95.0 + disc * 120.0
            g = base_g + glow * 72.0 + disc * 115.0
            b = base_b + glow * 30.0 + disc * 90.0
            if yn >= m1_arr[xi]:
                r = r * 0.48 + 38.0
                g = g * 0.40 + 26.0
                b = b * 0.55 + 48.0
            buf[p] = _clamp_u8(r)
            buf[p + 1] = _clamp_u8(g)
            buf[p + 2] = _clamp_u8(b)

    water_rows = SCREEN_HEIGHT - h_idx
    for wy in range(water_rows):
        depth = wy / max(1, water_rows - 1)
        src_row = max(0, min(h_idx - 1, h_idx - 1 - int(wy * 1.35)))
        shift = int(3.5 * math.sin(wy * 0.75) * (0.3 + depth))
        darken = 0.74 - 0.30 * depth
        wave = 0.5 + 0.5 * math.sin(wy * 1.4)
        spread = 0.045 + 0.09 * depth
        src_off = src_row * SCREEN_WIDTH * 3
        dst_off = (h_idx + wy) * SCREEN_WIDTH * 3

        for xi, xn in enumerate(xs):
            sx = (xi - shift) % SCREEN_WIDTH
            sp = src_off + sx * 3
            shimmer = math.exp(-(((xn - sun_x) / spread) ** 2)) * wave
            r = buf[sp] * darken + 8.0 * (1.0 - darken) + shimmer * 95.0
            g = buf[sp + 1] * darken + 16.0 * (1.0 - darken) + shimmer * 65.0
            b = buf[sp + 2] * darken + 30.0 * (1.0 - darken) + shimmer * 22.0
            dp = dst_off + xi * 3
            buf[dp] = _clamp_u8(r)
            buf[dp + 1] = _clamp_u8(g)
            buf[dp + 2] = _clamp_u8(b)

    return Image.frombytes("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), bytes(buf))


def _gen_photo_cyber_city(lang: str = "zh") -> Image.Image:
    """合成高饱和霓虹透视网格与 3D Blinn-Phong 光照球体测试图。"""
    en = lang == "en"
    buf = bytearray(SCREEN_WIDTH * SCREEN_HEIGHT * 3)
    for yi in range(SCREEN_HEIGHT):
        bg_r = 12.0 + 90.0 * math.exp(-(((yi - 92.0) / 26.0) ** 2))
        bg_g = 10.0 + 45.0 * math.exp(-(((yi - 96.0) / 22.0) ** 2))
        bg_b = 28.0 + 130.0 * math.exp(-(((yi - 92.0) / 34.0) ** 2))
        row_off = yi * SCREEN_WIDTH * 3

        if yi <= 95:
            cr, cg, cb = _clamp_u8(bg_r), _clamp_u8(bg_g), _clamp_u8(bg_b)
            for xi in range(SCREEN_WIDTH):
                p = row_off + xi * 3
                buf[p], buf[p + 1], buf[p + 2] = cr, cg, cb
        else:
            dy = max(1.0, yi - 92.0)
            v_mod = abs(((900.0 / dy) % 12.0) - 6.0) < 0.85
            fade = min(1.0, max(0.15, (yi - 95.0) / 75.0))
            scale_u = 68.0 / dy
            for xi in range(SCREEN_WIDTH):
                u_mod = abs((((xi - 160.0) * scale_u) % 24.0) - 12.0) < 1.2
                is_line = u_mod or v_mod
                r = bg_r * 0.45 + (210.0 * fade if is_line else 8.0)
                g = bg_g * 0.45 + (45.0 * fade if is_line else 14.0)
                b = bg_b * 0.55 + (245.0 * fade if is_line else 34.0)
                p = row_off + xi * 3
                buf[p], buf[p + 1], buf[p + 2] = _clamp_u8(r), _clamp_u8(g), _clamp_u8(b)

    spheres = (
        (-0.48, -0.02, 0.30, (0.08, 0.82, 0.96)),
        (0.04, 0.04, 0.36, (0.96, 0.18, 0.62)),
        (0.54, 0.07, 0.25, (0.98, 0.74, 0.14)),
    )
    lx, ly, lz = -0.45, -0.60, 0.66
    hx, hy, hz = lx, ly, lz + 1.0
    hlen = math.sqrt(hx * hx + hy * hy + hz * hz)
    hx, hy, hz = hx / hlen, hy / hlen, hz / hlen

    for sx, sy, sr, base_col in spheres:
        cx_px = SCREEN_WIDTH * 0.5 + sx * SCREEN_HEIGHT
        cy_px = SCREEN_HEIGHT * 0.5 + sy * SCREEN_HEIGHT
        rad_px = sr * SCREEN_HEIGHT
        x0 = max(0, int(cx_px - rad_px - 1))
        x1 = min(SCREEN_WIDTH - 1, int(cx_px + rad_px + 1))
        y0 = max(0, int(cy_px - rad_px - 1))
        y1 = min(SCREEN_HEIGHT - 1, int(cy_px + rad_px + 1))
        sr2 = sr * sr
        inv_r = 1.0 / sr

        for yi in range(y0, y1 + 1):
            ny = (yi - SCREEN_HEIGHT * 0.5) / SCREEN_HEIGHT - sy
            ny2 = ny * ny
            row_off = yi * SCREEN_WIDTH * 3
            for xi in range(x0, x1 + 1):
                nx = (xi - SCREEN_WIDTH * 0.5) / SCREEN_HEIGHT - sx
                r2 = nx * nx + ny2
                if r2 > sr2:
                    continue
                dz = math.sqrt(sr2 - r2)
                vnx, vny, vnz = nx * inv_r, ny * inv_r, dz * inv_r
                diff = max(0.0, vnx * lx + vny * ly + vnz * lz)
                rim = (1.0 - max(0.0, min(1.0, vnz))) ** 2.6
                spec = max(0.0, vnx * hx + vny * hy + vnz * hz) ** 36.0
                p = row_off + xi * 3
                buf[p] = _clamp_u8((0.14 + 0.86 * diff) * base_col[0] * 255.0 + spec * 235.0 + rim * 55.0)
                buf[p + 1] = _clamp_u8((0.14 + 0.86 * diff) * base_col[1] * 255.0 + spec * 235.0 + rim * 55.0)
                buf[p + 2] = _clamp_u8((0.14 + 0.86 * diff) * base_col[2] * 255.0 + spec * 235.0 + rim * 110.0)

    img = Image.frombytes("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), bytes(buf))
    draw = ImageDraw.Draw(img)
    f_tag = _get_font(11)
    tag_txt = "RGB565 Gamut & Spec" if en else "RGB565 光影与饱和度"
    tb = draw.textbbox((0, 0), tag_txt, font=f_tag)
    draw.rounded_rectangle((8, 7, 20 + (tb[2] - tb[0]), 25), radius=4, fill=(18, 12, 32), outline=(0, 229, 255))
    draw.text((14, 9), tag_txt, font=f_tag, fill=(165, 243, 252))
    return img


def _gen_cal_color_bars(_lang: str = "zh") -> Image.Image:
    img = Image.new("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    f_xs = _get_font(10)

    bars = (
        ("WHT", (255, 255, 255), (0, 0, 0)),
        ("YEL", (255, 255, 0), (0, 0, 0)),
        ("CYN", (0, 255, 255), (0, 0, 0)),
        ("GRN", (0, 255, 0), (0, 0, 0)),
        ("MAG", (255, 0, 255), (255, 255, 255)),
        ("RED", (255, 0, 0), (255, 255, 255)),
        ("BLU", (0, 0, 255), (255, 255, 255)),
        ("BLK", (0, 0, 0), (200, 200, 200)),
    )
    bw = SCREEN_WIDTH // len(bars)
    for i, (name, col, txt_col) in enumerate(bars):
        x0 = i * bw
        x1 = (SCREEN_WIDTH - 1) if i == len(bars) - 1 else (x0 + bw - 1)
        draw.rectangle((x0, 0, x1, 99), fill=col)
        draw.text((x0 + 7, 82), name, font=f_xs, fill=txt_col)

    sw = SCREEN_WIDTH // 16
    for i in range(16):
        v = int(round(i * 255 / 15))
        draw.rectangle((i * sw, 100, (i + 1) * sw - 1, 135), fill=(v, v, v))

    near_levels = (0, 8, 16, 24, 32, 223, 231, 239, 247, 255)
    nw = SCREEN_WIDTH // len(near_levels)
    for i, v in enumerate(near_levels):
        x0 = i * nw
        x1 = (SCREEN_WIDTH - 1) if i == len(near_levels) - 1 else (x0 + nw - 1)
        draw.rectangle((x0, 136, x1, 169), fill=(v, v, v))
        fg = (210, 210, 210) if v < 128 else (30, 30, 30)
        draw.text((x0 + 4, 148), str(v), font=f_xs, fill=fg)

    return img


def _gen_cal_gradients(lang: str = "zh") -> Image.Image:
    en = lang == "en"
    buf = bytearray(SCREEN_WIDTH * SCREEN_HEIGHT * 3)
    ramp = [int(round(x * 255 / (SCREEN_WIDTH - 1))) for x in range(SCREEN_WIDTH)]
    bands = (
        (0, 41, (1, 0, 0), "RED 5b (32) · Banding" if en else "RED 5-bit (32级) · 观察竖向色带"),
        (43, 84, (0, 1, 0), "GRN 6b (64)" if en else "GREEN 6-bit (64级)"),
        (86, 127, (0, 0, 1), "BLU 5b (32)" if en else "BLUE 5-bit (32级)"),
        (129, 170, (1, 1, 1), "GRAY · Compare Dither" if en else "GRAY 灰阶渐变 · 对比 rgb565_dither"),
    )
    for y0, y1, mask, _ in bands:
        row_bytes = bytearray(SCREEN_WIDTH * 3)
        for x, val in enumerate(ramp):
            p = x * 3
            if mask[0]:
                row_bytes[p] = val
            if mask[1]:
                row_bytes[p + 1] = val
            if mask[2]:
                row_bytes[p + 2] = val
        r_slice = bytes(row_bytes)
        for y in range(y0, y1):
            off = y * SCREEN_WIDTH * 3
            buf[off : off + SCREEN_WIDTH * 3] = r_slice

    img = Image.frombytes("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), bytes(buf))
    draw = ImageDraw.Draw(img)
    f = _get_font(11)
    for y0, _, _, label in bands:
        lb = draw.textbbox((0, 0), label, font=f)
        draw.rounded_rectangle((6, y0 + 4, 16 + (lb[2] - lb[0]), y0 + 20), radius=3, fill=(0, 0, 0))
        draw.text((10, y0 + 5), label, font=f, fill=(240, 244, 248))
    return img


def _gen_cal_typography_grid(lang: str = "zh") -> Image.Image:
    en = lang == "en"
    img = Image.new("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), (16, 20, 26))
    draw = ImageDraw.Draw(img)
    draw.rectangle((160, 0, 319, 169), fill=(246, 248, 250))

    for gx in range(32, SCREEN_WIDTH, 32):
        col = (34, 42, 54) if gx < 160 else (222, 228, 236)
        draw.line((gx, 0, gx, 169), fill=col)
    for gy in range(32, SCREEN_HEIGHT, 32):
        draw.line((0, gy, 159, gy), fill=(34, 42, 54))
        draw.line((160, gy, 319, gy), fill=(222, 228, 236))

    draw.rectangle((0, 0, 319, 169), outline=(255, 50, 50), width=1)
    draw.rectangle((2, 2, 317, 167), outline=(0, 210, 255), width=1)

    sizes = (10, 12, 14, 16, 18)
    y_cursor = 8
    for sz in sizes:
        f = _get_font(sz)
        left_txt = f"{sz}px Txt AB12" if en else f"{sz}px 锐度 AB12"
        right_txt = f"{sz}px Ink 320w" if en else f"{sz}px 墨字 320w"
        draw.text((8, y_cursor), left_txt, font=f, fill=(238, 242, 246))
        draw.text((167, y_cursor), right_txt, font=f, fill=(20, 24, 30))
        y_cursor += sz + 15

    return img


_PATTERN_BUILDERS = {
    "ui_launcher": _gen_ui_launcher,
    "ui_dashboard": _gen_ui_dashboard,
    "ui_terminal": _gen_ui_terminal,
    "ui_radio_spectrum": _gen_ui_radio_spectrum,
    "ui_chat_reader": _gen_ui_chat_reader,
    "photo_sunset": _gen_photo_sunset,
    "photo_cyber_city": _gen_photo_cyber_city,
    "cal_color_bars": _gen_cal_color_bars,
    "cal_gradients": _gen_cal_gradients,
    "cal_typography_grid": _gen_cal_typography_grid,
}


def generate_sample_image(pattern_id: str, lang: str = "zh") -> Image.Image:
    """按样张 ID 与界面语言生成原生 320×170 RGB 测试画面。"""
    builder = _PATTERN_BUILDERS.get(pattern_id)
    if builder is None:
        raise ValueError(f"未知样张 ID: {pattern_id}")
    norm_lang = "en" if str(lang).strip().lower() == "en" else "zh"
    return builder(norm_lang)


# ---------------------------------------------------------------------------
# Linux /dev/fb0 帧缓冲后端与系统状态读取
# ---------------------------------------------------------------------------
class BaseFramebuffer:
    backend_name = "base"
    device_path = ""

    def write_frame(self, rgb565_bytes: bytes) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class MemoryFramebuffer(BaseFramebuffer):
    """桌面开发与测试使用的内存虚拟帧缓冲。"""

    backend_name = "memory"
    device_path = "memory://320x170"

    def __init__(self, width: int = SCREEN_WIDTH, height: int = SCREEN_HEIGHT) -> None:
        self.width = width
        self.height = height
        self.last_bytes: bytes = b"\x00" * (width * height * 2)
        self.write_count: int = 0

    def write_frame(self, rgb565_bytes: bytes) -> None:
        if len(rgb565_bytes) != FRAME_BYTES:
            raise ValueError(f"帧字节长度不匹配: {len(rgb565_bytes)} != {FRAME_BYTES}")
        self.last_bytes = bytes(rgb565_bytes)
        self.write_count += 1


class LinuxMmapFramebuffer(BaseFramebuffer):
    """CardputerZero ST7789v3 Linux /dev/fb* mmap 零拷贝帧缓冲驱动。"""

    backend_name = "fbdev"

    def __init__(self, fb_path: str) -> None:
        self.device_path = fb_path
        self._lock = threading.Lock()
        self._unblank(fb_path)
        self._fd = os.open(fb_path, os.O_RDWR)
        self._mmap = mmap.mmap(self._fd, FRAME_BYTES, mmap.MAP_SHARED, mmap.PROT_WRITE | mmap.PROT_READ)

    @staticmethod
    def _unblank(fb_path: str) -> None:
        fb_name = Path(fb_path).name
        blank_file = Path(f"/sys/class/graphics/{fb_name}/blank")
        try:
            if blank_file.exists():
                blank_file.write_text("0", encoding="utf-8")
        except Exception:
            pass

    def write_frame(self, rgb565_bytes: bytes) -> None:
        if len(rgb565_bytes) != FRAME_BYTES:
            raise ValueError(f"帧字节长度不匹配: {len(rgb565_bytes)} != {FRAME_BYTES}")
        with self._lock:
            self._mmap.seek(0)
            self._mmap.write(rgb565_bytes)

    def close(self) -> None:
        with self._lock:
            if getattr(self, "_mmap", None) is not None:
                try:
                    self._mmap.seek(0)
                    self._mmap.write(b"\x00" * FRAME_BYTES)
                    self._mmap.close()
                except Exception:
                    pass
                self._mmap = None
            if getattr(self, "_fd", -1) >= 0:
                try:
                    os.close(self._fd)
                except Exception:
                    pass
                self._fd = -1


def open_best_framebuffer() -> BaseFramebuffer:
    """优先读取 APPLaunch 传入的帧缓冲环境变量，再探测 st7789v_m5st / panel-mipi-dbi / /dev/fb_lcd，不可用时回退内存。"""
    forced = (os.environ.get("CP0_FB_DEVICE") or os.environ.get("APPLAUNCH_LINUX_FBDEV_DEVICE") or "").strip()
    candidates: list[str] = []
    if forced:
        if forced.lower() == "memory":
            return MemoryFramebuffer()
        candidates.append(forced)
    else:
        if Path("/dev/fb_lcd").exists():
            candidates.append("/dev/fb_lcd")
        for idx in range(4):
            name_file = Path(f"/sys/class/graphics/fb{idx}/name")
            try:
                if name_file.is_file():
                    drv_name = name_file.read_text(encoding="utf-8", errors="ignore").lower()
                    if "st7789v_m5st" in drv_name or "panel-mipi-dbi" in drv_name:
                        dev_p = f"/dev/fb{idx}"
                        if dev_p not in candidates:
                            candidates.append(dev_p)
            except Exception:
                pass
        if Path("/dev/fb0").exists() and "/dev/fb0" not in candidates:
            candidates.append("/dev/fb0")

    for dev in candidates:
        try:
            return LinuxMmapFramebuffer(dev)
        except Exception:
            continue
    return MemoryFramebuffer()


def detect_local_ipv4() -> str:
    """通过无发包 UDP 路由探测本机首选局域网 IPv4 地址。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.168.1.1", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass
    try:
        hostname_ips = socket.gethostbyname_ex(socket.gethostname())[2]
        for ip in hostname_ips:
            if ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass
    return "127.0.0.1"


def read_device_telemetry(port: int, fb: BaseFramebuffer) -> dict[str, Any]:
    """读取本机 IP、Wi-Fi、电池、温度与内存信息（任何文件缺失均安全降级）。"""
    info: dict[str, Any] = {
        "ip": detect_local_ipv4(),
        "port": port,
        "fb_backend": fb.backend_name,
        "fb_device": fb.device_path,
        "wifi_connected": False,
        "wifi_strength": None,
        "battery_percent": None,
        "battery_charging": False,
        "cpu_temp_c": None,
        "mem_used_mb": None,
        "mem_total_mb": None,
    }

    try:
        wireless_path = Path("/proc/net/wireless")
        if wireless_path.is_file():
            for line in wireless_path.read_text(encoding="utf-8", errors="ignore").splitlines()[2:]:
                if ":" in line:
                    _, rest = line.split(":", 1)
                    parts = rest.split()
                    if len(parts) >= 2:
                        qual = float(parts[1].rstrip("."))
                        info["wifi_connected"] = True
                        info["wifi_strength"] = max(0, min(100, int(round(qual * 100.0 / 70.0))))
                        break
    except Exception:
        pass

    try:
        ps_root = Path("/sys/class/power_supply")
        if ps_root.is_dir():
            for entry in ps_root.iterdir():
                tfile = entry / "type"
                if tfile.is_file() and tfile.read_text(encoding="utf-8", errors="ignore").strip() == "Battery":
                    cap_file = entry / "capacity"
                    st_file = entry / "status"
                    if cap_file.is_file():
                        info["battery_percent"] = int(cap_file.read_text(encoding="utf-8").strip())
                    if st_file.is_file():
                        info["battery_charging"] = st_file.read_text(encoding="utf-8").strip() == "Charging"
                    break
    except Exception:
        pass

    try:
        t_file = Path("/sys/class/thermal/thermal_zone0/temp")
        if t_file.is_file():
            info["cpu_temp_c"] = round(int(t_file.read_text(encoding="utf-8").strip()) / 1000.0, 1)
    except Exception:
        pass

    try:
        mem_file = Path("/proc/meminfo")
        if mem_file.is_file():
            kv: dict[str, int] = {}
            for line in mem_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    nums = v.strip().split()
                    if nums and nums[0].isdigit():
                        kv[k.strip()] = int(nums[0])
            if "MemTotal" in kv and "MemAvailable" in kv:
                total_mb = int(round(kv["MemTotal"] / 1024.0))
                avail_mb = int(round(kv["MemAvailable"] / 1024.0))
                info["mem_total_mb"] = total_mb
                info["mem_used_mb"] = max(0, total_mb - avail_mb)
    except Exception:
        pass

    return info


def build_waiting_screen_image(telemetry: Mapping[str, Any], port: int, lang: str = "zh") -> Image.Image:
    """绘制 CardputerZero 320×170 待机等待连接界面（小屏采用精简简称，支持中英切换）。"""
    en = str(lang).strip().lower() == "en"
    img = Image.new("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), (12, 16, 23))
    draw = ImageDraw.Draw(img)
    f_title = _get_font(13)
    f_url = _get_font(17, mono=True)
    f_sub = _get_font(11)
    f_xs = _get_font(10)

    draw.rectangle((0, 0, 319, 24), fill=(22, 28, 38))
    draw.line((0, 24, 319, 24), fill=(48, 60, 78))
    draw.text((8, 4), "ScreenCast" if en else "投屏控台", font=f_title, fill=(235, 242, 250))

    now_str = datetime.now().strftime("%H:%M")
    bat = telemetry.get("battery_percent")
    if bat is not None:
        bat_str = f"BAT {bat}%" if en else f"电 {bat}%"
    else:
        bat_str = "AC" if en else "外电"
    right_txt = f"{now_str} · {bat_str}"
    rb = draw.textbbox((0, 0), right_txt, font=f_xs)
    draw.text((312 - (rb[2] - rb[0]), 6), right_txt, font=f_xs, fill=(147, 197, 253))

    draw.rounded_rectangle((8, 31, 311, 141), radius=8, fill=(20, 27, 38), outline=(56, 189, 248), width=1)
    badge_txt = "READY" if en else "就绪"
    bb = draw.textbbox((0, 0), badge_txt, font=f_xs)
    bw = bb[2] - bb[0]
    draw.rounded_rectangle((16, 39, 28 + bw, 56), radius=4, fill=(18, 66, 52), outline=(52, 211, 153))
    draw.text((22, 41), badge_txt, font=f_xs, fill=(110, 231, 183))
    spec_txt = "320x170 · RGB565" if en else "320×170 · RGB565"
    draw.text((36 + bw, 41), spec_txt, font=f_xs, fill=(148, 163, 184))

    url_str = f"http://{telemetry.get('ip', '127.0.0.1')}:{port}"
    ub = draw.textbbox((0, 0), url_str, font=f_url)
    ux = max(14, (SCREEN_WIDTH - (ub[2] - ub[0])) // 2)
    draw.text((ux, 66), url_str, font=f_url, fill=(125, 211, 252))

    api_hint = "Open URL or POST /push" if en else "浏览器访问 或 POST /push"
    ab = draw.textbbox((0, 0), api_hint, font=f_sub)
    draw.text((max(12, (SCREEN_WIDTH - (ab[2] - ab[0])) // 2), 98), api_hint, font=f_sub, fill=(216, 224, 236))

    fb_short = str(telemetry.get("fb_device") or telemetry.get("fb_backend") or "--")
    fb_hint = f"FB: {fb_short} · Hold ESC: Quit" if en else f"FB: {fb_short} · 长按ESC退"
    draw.text((16, 121), fb_hint, font=f_xs, fill=(120, 134, 154))

    footer_items = ("4 Prev", "5 Next", "6 Mode", "7 HUD", "8 中文") if en else ("4 上张", "5 下张", "6 色彩", "7 角标", "8 EN")
    _draw_nav_footer(draw, footer_items)
    return img


# ---------------------------------------------------------------------------
# 运行时状态机（线程安全，统一调度推图、样张、重算、超时与按键）
# ---------------------------------------------------------------------------
class ScreenCastRuntime:
    """管理当前配置、缓存源图像、RGB565 显存输出与统计遥测。"""

    def __init__(self, env_path: Path, web_dir: Path, framebuffer: BaseFramebuffer) -> None:
        self.env_path = env_path
        self.web_dir = web_dir
        self.fb = framebuffer
        self._lock = threading.RLock()
        self._config = load_env_config(env_path)

        self._mode = "waiting"  # waiting | casting | pattern
        self._paused = False
        self._active_pattern = ""
        self._pattern_index = -1
        self._last_source_img: Image.Image | None = None
        self._frame_rgb565: bytes = b""
        self._preview_png: bytes = b""
        self._preview_png_seq: int = -1
        self._frame_sha256: str = ""
        self._frame_seq: int = 0
        self._last_received_at: str = ""
        self._last_activity_mono: float = time.monotonic()
        self._next_push_mono: float = 0.0
        self._fps_window: deque[float] = deque()
        self._fps: float = 0.0

        self._stats: dict[str, Any] = {
            "received_frames": 0,
            "blitted_frames": 0,
            "dropped_frames": 0,
            "rejected_requests": 0,
            "last_process_ms": None,
            "last_error": "",
        }
        self.stop_event = threading.Event()

    def close(self) -> None:
        self.stop_event.set()
        self.fb.close()

    def get_config(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._config)

    def check_token(self, header_token: str | None) -> bool:
        with self._lock:
            expected = self._config.get("CAST_TOKEN", "")
        if not expected:
            return True
        return (header_token or "").strip() == expected

    def _pace_push_frame(self) -> tuple[bool, int]:
        """
        按 TARGET_FPS 对外部推流执行无锁稳帧节流（适配高速视频播放与游戏推流客户端）：
        - TARGET_FPS <= 0：不控制 FPS，立即放行；
        - TARGET_FPS > 0：按 1/TARGET_FPS 间隔均匀排期上屏，锁外分段等待避免阻塞 /health 与键盘；
          若并发客户端超速灌入超出缓冲上限（max(0.25s, 5帧)），直接丢弃超额帧避免画面延迟堆积。
        """
        with self._lock:
            target_fps = int(self._config.get("TARGET_FPS", 0))
            if target_fps <= 0 or self._paused:
                self._next_push_mono = 0.0
                return True, 0
            interval = 1.0 / float(target_fps)
            now = time.monotonic()
            max_ahead = max(0.25, interval * 5.0)
            if self._next_push_mono <= now:
                self._next_push_mono = now + interval
                return True, target_fps
            wait_sec = self._next_push_mono - now
            if wait_sec > max_ahead:
                self._stats["dropped_frames"] += 1
                return False, target_fps
            scheduled_mono = self._next_push_mono
            self._next_push_mono = scheduled_mono + interval

        while not self.stop_event.is_set():
            rem = scheduled_mono - time.monotonic()
            if rem <= 0.0005:
                break
            with self._lock:
                cur_fps = int(self._config.get("TARGET_FPS", 0))
                paused = self._paused
            if cur_fps <= 0 or cur_fps != target_fps or paused:
                break
            time.sleep(min(rem, 0.02))
        return True, target_fps

    def _record_frame_timing_locked(self) -> None:
        now_mono = time.monotonic()
        self._fps_window.append(now_mono)
        while len(self._fps_window) > 2 and (now_mono - self._fps_window[0]) > 1.2:
            self._fps_window.popleft()
        if len(self._fps_window) >= 2:
            span = self._fps_window[-1] - self._fps_window[0]
            if 0.001 < span < 10.0:
                self._fps = round((len(self._fps_window) - 1) / span, 1)
        self._last_activity_mono = now_mono
        self._last_received_at = datetime.now().strftime("%H:%M:%S")

    def render_waiting_screen(self) -> dict[str, Any]:
        with self._lock:
            port = int(self._config["LISTEN_PORT"])
            lang = str(self._config.get("UI_LANG", "zh"))
            telemetry = read_device_telemetry(port, self.fb)
            wait_img = build_waiting_screen_image(telemetry, port, lang=lang)
            rgb565 = rgb888_to_rgb565_bytes(wait_img, dither=False)

            self.fb.write_frame(rgb565)
            self._mode = "waiting"
            self._active_pattern = ""
            self._last_source_img = None
            self._frame_rgb565 = rgb565
            self._preview_png = b""
            self._frame_sha256 = hashlib.sha256(rgb565).hexdigest()
            self._frame_seq += 1
            return {"ok": True, "mode": self._mode, "frame_seq": self._frame_seq}

    def _apply_source_locked(
        self,
        src_img: Image.Image,
        new_mode: str,
        pattern_id: str = "",
        temp_overrides: Mapping[str, Any] | None = None,
        t0_override: float | None = None,
    ) -> dict[str, Any]:
        t0 = t0_override if t0_override is not None else time.perf_counter()
        eff_cfg = dict(self._config)
        if temp_overrides:
            eff_cfg.update(temp_overrides)

        self._mode = new_mode
        self._active_pattern = pattern_id
        self._last_source_img = src_img

        overlay = ""
        if eff_cfg.get("SHOW_OVERLAY", False):
            en = str(eff_cfg.get("UI_LANG", "zh")) == "en"
            short_modes = {
                "rgb565": "565",
                "rgb565_dither": "565D",
                "gray": "GRAY",
                "mono_floyd": "1B-FS",
                "mono_threshold": "1B-TH",
            }
            if new_mode == "pattern":
                tag = pattern_id.replace("ui_", "").replace("photo_", "").replace("cal_", "")[:9]
                cap_tag = ""
            else:
                tag = "CAST" if en else "推流"
                tfps = int(eff_cfg.get("TARGET_FPS", 0))
                cap_tag = f"·{tfps}F" if tfps > 0 else ""
            sm = short_modes.get(str(eff_cfg["COLOR_MODE"]), str(eff_cfg["COLOR_MODE"]))
            overlay = f"{tag}{cap_tag}·{sm}"

        rgb565, _, sha = process_image_to_frame(
            src_img,
            eff_cfg,
            overlay_text=overlay,
            include_preview_png=False,
        )
        self.fb.write_frame(rgb565)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        self._record_frame_timing_locked()
        self._frame_rgb565 = rgb565
        self._preview_png = b""
        self._frame_sha256 = sha
        self._frame_seq += 1
        self._stats["blitted_frames"] += 1
        self._stats["last_process_ms"] = elapsed_ms
        self._stats["last_error"] = ""

        return {
            "ok": True,
            "mode": self._mode,
            "active_pattern": self._active_pattern,
            "width": SCREEN_WIDTH,
            "height": SCREEN_HEIGHT,
            "frame_bytes": FRAME_BYTES,
            "sha256": sha,
            "frame_seq": self._frame_seq,
            "process_ms": elapsed_ms,
        }

    def push_raw_rgb565(self, raw_bytes: bytes) -> dict[str, Any]:
        """直接接收外部已打包好的 108,800 字节小端 RGB565 帧并零转换直写显存。"""
        allowed, cap_fps = self._pace_push_frame()
        with self._lock:
            self._stats["received_frames"] += 1
            if not allowed:
                return {
                    "ok": True,
                    "dropped": True,
                    "target_fps": cap_fps,
                    "mode": self._mode,
                    "width": SCREEN_WIDTH,
                    "height": SCREEN_HEIGHT,
                    "frame_bytes": FRAME_BYTES,
                    "frame_seq": self._frame_seq,
                }
            if self._paused:
                return {
                    "ok": True,
                    "paused": True,
                    "mode": self._mode,
                    "width": SCREEN_WIDTH,
                    "height": SCREEN_HEIGHT,
                    "frame_bytes": FRAME_BYTES,
                    "frame_seq": self._frame_seq,
                }
            t0 = time.perf_counter()
            # 惰性策略：高频推流期跳过 RGB565->Image 解包与 PNG 压缩，仅在后续网页调参或拉取 /preview.png 时按需还原
            self._last_source_img = None
            self._mode = "casting"
            self._active_pattern = ""
            self.fb.write_frame(raw_bytes)
            sha = hashlib.sha256(raw_bytes).hexdigest()
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

            self._record_frame_timing_locked()
            self._frame_rgb565 = raw_bytes
            self._preview_png = b""
            self._frame_sha256 = sha
            self._frame_seq += 1
            self._stats["blitted_frames"] += 1
            self._stats["last_process_ms"] = elapsed_ms
            return {
                "ok": True,
                "mode": "casting",
                "width": SCREEN_WIDTH,
                "height": SCREEN_HEIGHT,
                "frame_bytes": FRAME_BYTES,
                "sha256": sha,
                "frame_seq": self._frame_seq,
                "process_ms": elapsed_ms,
            }

    def push_encoded_image(self, image_bytes: bytes, overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """解码任意分辨率 PNG/JPEG/BMP/WebP/GIF 并按当前配置及稳帧策略渲染上屏。"""
        t_dec0 = time.perf_counter()
        try:
            with Image.open(io.BytesIO(image_bytes)) as im:
                im.load()
                rgb = im if im.mode == "RGB" else im.convert("RGB")
        except Exception as exc:
            with self._lock:
                self._stats["rejected_requests"] += 1
                self._stats["last_error"] = f"图片解码失败: {exc}"
            raise ValueError(f"无法识别的图片格式或文件已损坏: {exc}") from exc
        decode_sec = time.perf_counter() - t_dec0

        allowed, cap_fps = self._pace_push_frame()
        with self._lock:
            self._stats["received_frames"] += 1
            if not allowed:
                return {
                    "ok": True,
                    "dropped": True,
                    "target_fps": cap_fps,
                    "mode": self._mode,
                    "width": SCREEN_WIDTH,
                    "height": SCREEN_HEIGHT,
                    "frame_bytes": FRAME_BYTES,
                    "frame_seq": self._frame_seq,
                }
            if self._paused:
                return {
                    "ok": True,
                    "paused": True,
                    "mode": self._mode,
                    "width": SCREEN_WIDTH,
                    "height": SCREEN_HEIGHT,
                    "frame_bytes": FRAME_BYTES,
                    "frame_seq": self._frame_seq,
                }
            # 扣除中间故意等待的稳帧睡眠时长，使 process_ms 真实反映设备解码+渲染 CPU 开销
            return self._apply_source_locked(
                rgb,
                new_mode="casting",
                pattern_id="",
                temp_overrides=overrides,
                t0_override=time.perf_counter() - decode_sec,
            )

    def show_sample_pattern(self, pattern_id: str) -> dict[str, Any]:
        with self._lock:
            ids = [p["id"] for p in SAMPLE_PATTERNS]
            if pattern_id == "next":
                self._pattern_index = (self._pattern_index + 1) % len(ids)
                pattern_id = ids[self._pattern_index]
            elif pattern_id == "prev":
                self._pattern_index = (self._pattern_index - 1) % len(ids)
                pattern_id = ids[self._pattern_index]
            elif pattern_id in ids:
                self._pattern_index = ids.index(pattern_id)
            else:
                raise ValueError(f"未知样张 ID: {pattern_id}")

            lang = str(self._config.get("UI_LANG", "zh"))
            img = generate_sample_image(pattern_id, lang=lang)
            return self._apply_source_locked(img, new_mode="pattern", pattern_id=pattern_id)

    def update_config(self, payload: Mapping[str, Any], save_to_disk: bool = True) -> dict[str, Any]:
        with self._lock:
            prev_lang = str(self._config.get("UI_LANG", "zh"))
            prev_fps = int(self._config.get("TARGET_FPS", 0))
            merged = {**self._config, **payload}
            merged.pop("save", None)
            normalized, errors = validate_and_normalize_config(merged)
            if errors:
                return {"ok": False, "error": "配置参数校验失败", "fields": errors}

            if save_to_disk:
                save_env_config(self.env_path, normalized)
            self._config = normalized
            if normalized["TARGET_FPS"] != prev_fps:
                self._next_push_mono = 0.0

            if self._mode == "pattern" and self._active_pattern:
                if normalized["UI_LANG"] != prev_lang or self._last_source_img is None:
                    self._last_source_img = generate_sample_image(self._active_pattern, lang=normalized["UI_LANG"])
                self._apply_source_locked(
                    self._last_source_img,
                    new_mode="pattern",
                    pattern_id=self._active_pattern,
                )
            elif self._mode == "casting":
                if self._last_source_img is None and self._frame_rgb565:
                    self._last_source_img = rgb565_bytes_to_image(self._frame_rgb565)
                if self._last_source_img is not None:
                    self._apply_source_locked(
                        self._last_source_img,
                        new_mode="casting",
                        pattern_id="",
                    )
            elif self._mode == "waiting":
                self.render_waiting_screen()

            return {"ok": True, "config": dict(self._config), "frame_seq": self._frame_seq}

    def execute_control(self, action: str) -> dict[str, Any]:
        with self._lock:
            act = action.strip().lower()
            if act in ("waiting", "disconnect", "clear"):
                res = self.render_waiting_screen()
                return {**res, "paused": self._paused}
            if act == "pause":
                self._paused = True
                return {"ok": True, "paused": True, "mode": self._mode}
            if act == "resume":
                self._paused = False
                return {"ok": True, "paused": False, "mode": self._mode}
            if act == "refresh":
                if self._mode in ("casting", "pattern"):
                    if self._last_source_img is None and self._frame_rgb565:
                        self._last_source_img = rgb565_bytes_to_image(self._frame_rgb565)
                    if self._last_source_img is not None:
                        return self._apply_source_locked(self._last_source_img, self._mode, self._active_pattern)
                return self.render_waiting_screen()
            if act == "next_pattern":
                return self.show_sample_pattern("next")
            if act == "prev_pattern":
                return self.show_sample_pattern("prev")
            if act == "cycle_color_mode":
                idx = COLOR_MODES.index(self._config["COLOR_MODE"])
                next_mode = COLOR_MODES[(idx + 1) % len(COLOR_MODES)]
                return self.update_config({"COLOR_MODE": next_mode}, save_to_disk=False)
            if act == "toggle_overlay":
                return self.update_config({"SHOW_OVERLAY": not self._config["SHOW_OVERLAY"]}, save_to_disk=False)
            if act == "toggle_lang":
                cur_lang = str(self._config.get("UI_LANG", "zh"))
                next_lang = "en" if cur_lang != "en" else "zh"
                return self.update_config({"UI_LANG": next_lang}, save_to_disk=True)
            raise ValueError(f"不支持的控制指令: {action}")

    def check_idle_timeout(self) -> None:
        with self._lock:
            timeout_sec = int(self._config.get("CAST_TIMEOUT_SEC", 0))
            if timeout_sec <= 0 or self._mode != "casting":
                return
            if (time.monotonic() - self._last_activity_mono) >= timeout_sec:
                self.render_waiting_screen()

    def get_preview_png(self) -> bytes:
        with self._lock:
            if not self._frame_rgb565:
                self.render_waiting_screen()
            if not self._preview_png or self._preview_png_seq != self._frame_seq:
                preview_img = rgb565_bytes_to_image(self._frame_rgb565)
                buf = io.BytesIO()
                preview_img.save(buf, format="PNG", compress_level=1)
                self._preview_png = buf.getvalue()
                self._preview_png_seq = self._frame_seq
            return self._preview_png

    def get_health_snapshot(self) -> dict[str, Any]:
        with self._lock:
            port = int(self._config["LISTEN_PORT"])
            cfg_safe = dict(self._config)
            live_fps = self._fps if (time.monotonic() - self._last_activity_mono) <= 1.8 else 0.0
            return {
                "ok": True,
                "mode": self._mode,
                "paused": self._paused,
                "active_pattern": self._active_pattern,
                "has_frame": bool(self._frame_rgb565),
                "frame_seq": self._frame_seq,
                "frame_sha256": self._frame_sha256,
                "last_received_at": self._last_received_at,
                "fps": live_fps,
                "stats": dict(self._stats),
                "device": read_device_telemetry(port, self.fb),
                "config": cfg_safe,
            }


def _extract_multipart_image(content_type: str, body: bytes) -> bytes | None:
    """使用标准库 email.parser 解析 multipart/form-data，兼容 Python 3.11–3.13+。"""
    header_block = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
    msg = BytesParser(policy=default_email_policy).parsebytes(header_block + body)
    if not msg.is_multipart():
        return None
    for part in msg.iter_parts():
        field_name = part.get_param("name", header="content-disposition")
        if field_name in ("image", "file"):
            payload = part.get_payload(decode=True)
            if payload:
                return payload
    return None


# ---------------------------------------------------------------------------
# HTTP 处理器（完整异常捕获，兼容长连接与跨设备调用）
# ---------------------------------------------------------------------------
class ScreenCastHttpHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    # 开启 TCP_NODELAY 并启用读写缓冲合并系统调用，彻底消除 ~80ms Nagle + Delayed ACK 交互停顿
    disable_nagle_algorithm = True
    rbufsize = 65536
    wbufsize = -1
    runtime: ScreenCastRuntime

    def log_message(self, fmt: str, *args: Any) -> None:
        if self.path.startswith(("/health", "/preview.png", "/push")):
            return
        super().log_message(fmt, *args)

    def _send_bytes(
        self,
        status: int,
        body: bytes,
        content_type: str,
        close_conn: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if close_conn:
                self.send_header("Connection", "close")
                self.close_connection = True
            if extra_headers:
                for k, v in extra_headers.items():
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True

    def _send_json(self, status: int, payload: Mapping[str, Any], close_conn: bool = False) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(status, raw, "application/json; charset=utf-8", close_conn=close_conn)

    def _read_body(self) -> tuple[bytes | None, bool]:
        raw_len = self.headers.get("Content-Length")
        if raw_len is None:
            self._send_json(HTTPStatus.LENGTH_REQUIRED, {"ok": False, "error": "缺少 Content-Length"}, close_conn=True)
            return None, False
        try:
            length = int(raw_len)
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Content-Length 非法"}, close_conn=True)
            return None, False
        if length < 0 or length > MAX_UPLOAD_BYTES:
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"ok": False, "error": f"请求体超出限制 ({MAX_UPLOAD_BYTES} 字节)"},
                close_conn=True,
            )
            return None, False
        return self.rfile.read(length), True

    def _require_auth(self) -> bool:
        token = self.headers.get("X-Cast-Token")
        if not self.runtime.check_token(token):
            self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "X-Cast-Token 鉴权失败"}, close_conn=True)
            return False
        return True

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            route = parsed.path

            if route in ("/", "/index.html"):
                f = self.runtime.web_dir / "index.html"
                self._send_bytes(HTTPStatus.OK, f.read_bytes(), "text/html; charset=utf-8")
                return
            if route == "/app.css":
                f = self.runtime.web_dir / "app.css"
                self._send_bytes(HTTPStatus.OK, f.read_bytes(), "text/css; charset=utf-8")
                return
            if route == "/app.js":
                f = self.runtime.web_dir / "app.js"
                self._send_bytes(HTTPStatus.OK, f.read_bytes(), "application/javascript; charset=utf-8")
                return
            if route == "/preview.png":
                png = self.runtime.get_preview_png()
                self._send_bytes(HTTPStatus.OK, png, "image/png")
                return
            if route == "/health":
                self._send_json(HTTPStatus.OK, self.runtime.get_health_snapshot())
                return
            if route == "/api/config":
                self._send_json(HTTPStatus.OK, {"ok": True, "config": self.runtime.get_config()})
                return
            if route == "/api/patterns":
                query = parse_qs(parsed.query)
                req_lang = query.get("lang", [self.runtime.get_config().get("UI_LANG", "zh")])[0]
                norm_lang = "en" if str(req_lang).strip().lower() == "en" else "zh"
                self._send_json(HTTPStatus.OK, {"ok": True, "lang": norm_lang, "patterns": list_sample_patterns(lang=norm_lang)})
                return

            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": f"未知路径: {route}"})
        except Exception as exc:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": f"服务器内部异常: {exc}"}, close_conn=True)

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            route = parsed.path

            if route == "/push":
                if not self._require_auth():
                    return
                body, ok = self._read_body()
                if not ok or body is None:
                    return
                if not body:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "推送内容为空"})
                    return

                cenc = (self.headers.get("Content-Encoding") or "").strip().lower()
                if cenc in ("deflate", "zlib"):
                    try:
                        decomp = zlib.decompressobj()
                        body = decomp.decompress(body, MAX_UPLOAD_BYTES + 1)
                        body += decomp.flush()
                        if len(body) > MAX_UPLOAD_BYTES:
                            self._send_json(
                                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                                {"ok": False, "error": f"解压后超出限制 ({MAX_UPLOAD_BYTES} 字节)"},
                                close_conn=True,
                            )
                            return
                    except Exception as exc:
                        self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": f"deflate 解压失败: {exc}"})
                        return

                ctype = (self.headers.get("Content-Type") or "").strip()
                query = parse_qs(parsed.query)
                overrides: dict[str, Any] = {}
                if "color_mode" in query and query["color_mode"][0] in COLOR_MODES:
                    overrides["COLOR_MODE"] = query["color_mode"][0]
                if "fit_mode" in query and query["fit_mode"][0] in FIT_MODES:
                    overrides["FIT_MODE"] = query["fit_mode"][0]
                if "rotate" in query:
                    r_val, rok = _parse_int_range(query["rotate"][0], 0, 270)
                    if rok and r_val in ROTATE_VALUES:
                        overrides["ROTATE"] = r_val

                if ctype.lower().startswith("multipart/form-data"):
                    img_bytes = _extract_multipart_image(ctype, body)
                    if not img_bytes:
                        self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "multipart 缺少有效 image 或 file 字段"})
                        return
                    res = self.runtime.push_encoded_image(img_bytes, overrides=overrides)
                    self._send_json(HTTPStatus.OK, res)
                    return

                is_encoded_magic = body.startswith((b"\x89PNG", b"\xff\xd8\xff", b"BM", b"GIF8", b"RIFF"))
                if len(body) == FRAME_BYTES and not is_encoded_magic:
                    res = self.runtime.push_raw_rgb565(body)
                    self._send_json(HTTPStatus.OK, res)
                    return

                res = self.runtime.push_encoded_image(body, overrides=overrides)
                self._send_json(HTTPStatus.OK, res)
                return

            if route in ("/api/test-pattern", "/api/config", "/api/control"):
                if route != "/api/config" and not self._require_auth():
                    return
                body, ok = self._read_body()
                if not ok or body is None:
                    return
                try:
                    payload = json.loads(body.decode("utf-8") or "{}")
                    if not isinstance(payload, dict):
                        raise ValueError("JSON 根节点须为对象")
                except Exception as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": f"无效 JSON: {exc}"})
                    return

                if route == "/api/test-pattern":
                    pat_id = str(payload.get("pattern", "ui_launcher")).strip()
                    res = self.runtime.show_sample_pattern(pat_id)
                    self._send_json(HTTPStatus.OK, res)
                    return

                if route == "/api/config":
                    save_disk = bool(payload.get("save", True))
                    res = self.runtime.update_config(payload, save_to_disk=save_disk)
                    code = HTTPStatus.OK if res.get("ok") else HTTPStatus.BAD_REQUEST
                    self._send_json(code, res)
                    return

                if route == "/api/control":
                    action = str(payload.get("action", "")).strip()
                    res = self.runtime.execute_control(action)
                    self._send_json(HTTPStatus.OK, res)
                    return

            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": f"未知接口: {route}"})
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except Exception as exc:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": f"处理请求失败: {exc}"}, close_conn=True)


def create_http_server(host: str, port: int, runtime: ScreenCastRuntime) -> ThreadingHTTPServer:
    """创建绑定指定 runtime 实例的多线程 HTTP 服务器。"""

    class BoundHandler(ScreenCastHttpHandler):
        pass

    BoundHandler.runtime = runtime
    server = ThreadingHTTPServer((host, port), BoundHandler)
    server.daemon_threads = True
    return server


# ---------------------------------------------------------------------------
# Linux evdev 机身键盘监听（TCA8418，桌面无设备时自动静默跳过）
# ---------------------------------------------------------------------------
def start_evdev_keypad_thread(runtime: ScreenCastRuntime) -> threading.Thread | None:
    """在设备端监听 4-8 功能键（8/L 切换语言）、短按 ESC 回待机与长按 ESC 退出。"""
    try:
        import evdev  # type: ignore
    except ImportError:
        return None

    dev_path = os.environ.get("CP0_KEY_DEVICE", "").strip()
    if not dev_path:
        for idx in range(8):
            nfile = Path(f"/sys/class/input/event{idx}/device/name")
            try:
                if nfile.is_file() and "tca8418" in nfile.read_text(encoding="utf-8", errors="ignore").lower():
                    dev_path = f"/dev/input/event{idx}"
                    break
            except Exception:
                pass
    if not dev_path or not Path(dev_path).exists():
        return None

    def _worker() -> None:
        esc_down_at = 0.0
        try:
            device = evdev.InputDevice(dev_path)
            for event in device.read_loop():
                if runtime.stop_event.is_set():
                    break
                if event.type != evdev.ecodes.EV_KEY:
                    continue
                code = event.code
                val = event.value
                if code == evdev.ecodes.KEY_ESC:
                    if val == 1:
                        esc_down_at = time.monotonic()
                    elif val == 2 and esc_down_at > 0 and (time.monotonic() - esc_down_at) >= 0.7:
                        runtime.stop_event.set()
                        break
                    elif val == 0 and esc_down_at > 0:
                        held = time.monotonic() - esc_down_at
                        esc_down_at = 0.0
                        if held >= 0.7:
                            runtime.stop_event.set()
                            break
                        runtime.execute_control("waiting")
                elif val == 1:
                    if code in (evdev.ecodes.KEY_4, evdev.ecodes.KEY_LEFT, evdev.ecodes.KEY_Z):
                        runtime.execute_control("prev_pattern")
                    elif code in (evdev.ecodes.KEY_5, evdev.ecodes.KEY_RIGHT, evdev.ecodes.KEY_C):
                        runtime.execute_control("next_pattern")
                    elif code == evdev.ecodes.KEY_6:
                        runtime.execute_control("cycle_color_mode")
                    elif code == evdev.ecodes.KEY_7:
                        runtime.execute_control("toggle_overlay")
                    elif code in (evdev.ecodes.KEY_8, evdev.ecodes.KEY_L):
                        runtime.execute_control("toggle_lang")
                    elif code in (evdev.ecodes.KEY_0, evdev.ecodes.KEY_BACKSPACE):
                        runtime.execute_control("waiting")
        except Exception:
            return

    t = threading.Thread(target=_worker, name="cp0-evdev-keypad", daemon=True)
    t.start()
    return t


def _resolve_default_env_path(app_dir: Path) -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if xdg and os.name != "nt":
        return Path(xdg) / "cp0-screen-cast" / "cp0-screen-cast.conf"
    if os.name != "nt" and os.environ.get("HOME"):
        user_conf = Path(os.environ["HOME"]) / ".config" / "cp0-screen-cast" / "cp0-screen-cast.conf"
        if user_conf.is_file() or not (app_dir / ".env").is_file():
            if not user_conf.is_file() and Path("/etc/cp0-screen-cast.conf").is_file():
                user_conf.parent.mkdir(parents=True, exist_ok=True)
                user_conf.write_bytes(Path("/etc/cp0-screen-cast.conf").read_bytes())
            return user_conf
    return app_dir / ".env"


def main() -> int:
    parser = argparse.ArgumentParser(description="CardputerZero 网页控台与无线投屏画面测试服务")
    parser.add_argument("--env", type=str, default="", help="指定 .env 配置文件路径")
    parser.add_argument("--host", type=str, default="", help="覆盖监听地址")
    parser.add_argument("--port", type=int, default=0, help="覆盖监听端口")
    parser.add_argument("--pattern", type=str, default="", help="启动后立即显示的内置样张 ID")
    args = parser.parse_args()

    app_dir = Path(__file__).resolve().parent
    env_path = Path(args.env).resolve() if args.env else _resolve_default_env_path(app_dir)
    if not env_path.is_file() and (app_dir / ".env.example").is_file():
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_bytes((app_dir / ".env.example").read_bytes())

    fb = open_best_framebuffer()
    runtime = ScreenCastRuntime(env_path=env_path, web_dir=app_dir / "web", framebuffer=fb)
    cfg = runtime.get_config()
    host = args.host or str(cfg["LISTEN_HOST"])
    port = args.port if args.port > 0 else int(cfg["LISTEN_PORT"])
    if port != cfg["LISTEN_PORT"]:
        runtime.update_config({"LISTEN_PORT": port}, save_to_disk=False)

    if args.pattern:
        runtime.show_sample_pattern(args.pattern)
    else:
        runtime.render_waiting_screen()

    server = create_http_server(host, port, runtime)
    srv_thread = threading.Thread(target=server.serve_forever, name="cp0-http-server", daemon=True)
    srv_thread.start()
    start_evdev_keypad_thread(runtime)

    def _on_signal(_signum: int, _frame: Any) -> None:
        runtime.stop_event.set()

    signal.signal(signal.SIGINT, _on_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _on_signal)

    local_ip = detect_local_ipv4()
    print(
        f"[cp0-screen-cast] 已启动: http://{local_ip}:{port} "
        f"(绑定 {host}:{port}, 显存后端={fb.backend_name}:{fb.device_path}, 配置={env_path})",
        flush=True,
    )

    try:
        while not runtime.stop_event.wait(timeout=1.0):
            runtime.check_idle_timeout()
    finally:
        server.shutdown()
        server.server_close()
        runtime.close()
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
