#!/usr/bin/env python3
"""
程序说明：CardputerZero PC 端多速率连续推流 FPS 测速应用（pc_fps_tester.py）。

功能概述：
1. 面向 320×170 屏幕实时合成测速画面：居中超大号实测 FPS 数字 + 目标档位标签 +
   每帧步进 30° 的旋转雷达指针 + 恒速平滑往返滑块 + 0..F 16 格逐帧频闪条，让肉眼可直观分辨各帧率流畅度与跳帧。
2. 基于单套接字 HTTP/1.1 Keep-Alive + TCP_NODELAY + 单次 sendall 合包 + 顺序流水线（Pipelining），
   支持 rgb565_zlib（deflate 极速无损帧）、JPEG 4:4:4、PNG、Raw RGB565 四种载荷，彻底消除 Nagle/Delayed ACK 与往返空等。
3. 同时提供 Tkinter 桌面可视化控台（默认无参启动）与命令行巡检模式（--cli / --sweep）。
"""

from __future__ import annotations

import argparse
import io
import json
import math
import socket
import sys
import threading
import time
import zlib
from collections import deque
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageTk

SCREEN_WIDTH = 320
SCREEN_HEIGHT = 170
FRAME_BYTES = SCREEN_WIDTH * SCREEN_HEIGHT * 2
DEFAULT_HOST = "192.168.31.251"
DEFAULT_PORT = 8787
FORMAT_CHOICES: tuple[str, ...] = ("rgb565_zlib", "jpeg", "png", "rgb565")
PRESET_RATES: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0, 15.0, 20.0, 30.0, 60.0, 0.0)
SWEEP_TIERS: tuple[float, ...] = (2.0, 5.0, 10.0, 15.0, 20.0, 30.0, 60.0, 0.0)

# RGB888 -> 小端 RGB565 256 项快速查表（Pillow C 层合并）
_R_HI_LUT = [i & 0xF8 for i in range(256)]
_G_HI_LUT = [i >> 5 for i in range(256)]
_G_LO_LUT = [(i << 3) & 0xE0 for i in range(256)]
_B_LO_LUT = [i >> 3 for i in range(256)]

_FONT_CACHE: dict[int, ImageFont.ImageFont] = {}


def _get_font(size: int) -> ImageFont.ImageFont:
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    candidates = (
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        Path(r"C:\Windows\Fonts\segoeui.ttf"),
        Path(r"C:\Windows\Fonts\arialbd.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    )
    for fp in candidates:
        if fp.is_file():
            try:
                font = ImageFont.truetype(str(fp), size)
                _FONT_CACHE[size] = font
                return font
            except Exception:
                continue
    font = ImageFont.load_default()
    _FONT_CACHE[size] = font
    return font


def format_tier_label(target_fps: float, lang: str = "zh") -> str:
    """将目标帧率数值格式化为可读档位名称（0 表示不限速极限推流）。"""
    en = str(lang).lower() == "en"
    if target_fps <= 0:
        return "MAX Speed" if en else "MAX 全速"
    if abs(target_fps - round(target_fps)) < 0.05:
        return f"{int(round(target_fps))} FPS"
    return f"{target_fps:.1f} FPS"


def render_fps_frame(
    target_fps: float,
    actual_fps: float,
    frame_seq: int,
    elapsed_sec: float,
    rtt_ms: float,
    kbps: float,
    fmt: str = "jpeg",
    lang: str = "zh",
) -> Image.Image:
    """
    绘制 320×170 连续测速帧（支持 zh / en 双语界面）：
    - 中央超大号实测 FPS 数字（或首帧预热时的目标值）；
    - 右侧每帧旋转 30° 的 12 刻度指针盘（一圈 12 帧，高频连续性一目了然）；
    - 底部双轨：时间恒速平滑往返滑块（看果冻/卡顿感）+ 0..F 16 格逐帧频闪跑马灯（看是否丢帧）。
    """
    en = str(lang).lower() == "en"
    img = Image.new("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), (11, 15, 23))
    draw = ImageDraw.Draw(img)

    f_huge = _get_font(44)
    f_unit = _get_font(16)
    f_hdr = _get_font(12)
    f_xs = _get_font(10)

    # 1. 顶部状态栏 (y: 0..24)
    draw.rectangle((0, 0, 319, 24), fill=(20, 27, 38))
    draw.line((0, 24, 319, 24), fill=(48, 62, 82), width=1)

    tier_prefix = "Target: " if en else "目标: "
    tier_str = f"{tier_prefix}{format_tier_label(target_fps, lang=lang)}"
    tb = draw.textbbox((0, 0), tier_str, font=f_hdr)
    pill_w = (tb[2] - tb[0]) + 14
    is_max = target_fps <= 0
    pill_bg = (68, 36, 16) if is_max else (16, 56, 78)
    pill_bd = (251, 146, 60) if is_max else (56, 189, 248)
    pill_fg = (254, 215, 170) if is_max else (186, 230, 253)
    draw.rounded_rectangle((6, 3, 6 + pill_w, 21), radius=4, fill=pill_bg, outline=pill_bd)
    draw.text((13 - tb[0], 4 - tb[1]), tier_str, font=f_hdr, fill=pill_fg)

    short_fmt = "Z565" if fmt.lower() == "rgb565_zlib" else fmt.upper()
    right_meta = f"#{frame_seq:05d} · {short_fmt} · {rtt_ms:.0f}ms"
    rb = draw.textbbox((0, 0), right_meta, font=f_xs)
    draw.text((313 - (rb[2] - rb[0]), 6), right_meta, font=f_xs, fill=(148, 163, 184))

    # 2. 中左主数字区 (x: 6..222, y: 29..109)
    draw.rounded_rectangle((6, 29, 222, 109), radius=7, fill=(17, 24, 35), outline=(45, 58, 76))
    shown_fps = actual_fps if actual_fps > 0.05 else (target_fps if target_fps > 0 else 0.0)
    fps_num_txt = f"{shown_fps:4.1f}".strip()

    if is_max or target_fps <= 0 or shown_fps >= target_fps * 0.85:
        num_col = (52, 211, 153)
    else:
        num_col = (251, 191, 36)

    nb = draw.textbbox((0, 0), fps_num_txt, font=f_huge)
    nx, ny = 16, 36
    draw.text((nx - nb[0], ny - nb[1]), fps_num_txt, font=f_huge, fill=num_col)
    num_w = nb[2] - nb[0]

    ux = nx + num_w + 8
    draw.text((ux, 42), "FPS", font=f_unit, fill=(226, 232, 240))
    draw.text((ux, 64), "Live Rate" if en else "实测推流速率", font=f_xs, fill=(148, 163, 184))

    bw_txt = f"BW: {kbps:.0f} KB/s ({kbps * 8.0 / 1000.0:.2f} Mbps)" if en else f"吞吐: {kbps:.0f} KB/s ({kbps * 8.0 / 1000.0:.2f} Mbps)"
    draw.text((16, 91), bw_txt, font=f_xs, fill=(125, 211, 252))

    # 3. 中右逐帧旋转雷达盘 (x: 227..313, y: 29..109) —— 每帧顺时针前进 30°
    draw.rounded_rectangle((227, 29, 313, 109), radius=7, fill=(17, 24, 35), outline=(45, 58, 76))
    cx, cy, rad = 270, 69, 29
    draw.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), outline=(51, 65, 85), width=2)

    slot12 = frame_seq % 12
    head_deg = -90 + slot12 * 30
    draw.arc((cx - rad + 2, cy - rad + 2, cx + rad - 2, cy + rad - 2), head_deg - 75, head_deg, fill=(14, 116, 144), width=5)

    for idx in range(12):
        ang = math.radians(-90 + idx * 30)
        x_in = cx + (rad - 6) * math.cos(ang)
        y_in = cy + (rad - 6) * math.sin(ang)
        x_out = cx + (rad - 1) * math.cos(ang)
        y_out = cy + (rad - 1) * math.sin(ang)
        tick_col = (52, 211, 153) if idx == slot12 else (71, 85, 105)
        draw.line((x_in, y_in, x_out, y_out), fill=tick_col, width=2 if idx == slot12 else 1)

    head_rad = math.radians(head_deg)
    px = cx + (rad - 5) * math.cos(head_rad)
    py = cy + (rad - 5) * math.sin(head_rad)
    draw.line((cx, cy, px, py), fill=(110, 231, 183), width=3)
    draw.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill=(248, 250, 252))

    # 4. 轨道 A：基于真实时间的恒速平滑往返滑块 (y: 115..137, 周期 1.5 秒)
    draw.rounded_rectangle((6, 115, 313, 137), radius=4, fill=(15, 21, 30), outline=(40, 52, 68))
    for gx in range(36, 310, 30):
        draw.line((gx, 116, gx, 136), fill=(28, 37, 50), width=1)

    phase = (elapsed_sec / 1.5) % 1.0
    tri = 1.0 - abs(phase * 2.0 - 1.0)
    bar_w = 26
    track_span = (310 - 9) - bar_w
    bx0 = int(round(9 + tri * track_span))
    prev_phase = (max(0.0, elapsed_sec - 0.045) / 1.5) % 1.0
    prev_tri = 1.0 - abs(prev_phase * 2.0 - 1.0)
    prev_bx0 = int(round(9 + prev_tri * track_span))
    draw.rounded_rectangle((prev_bx0, 118, prev_bx0 + bar_w, 134), radius=3, fill=(18, 68, 92))
    draw.rounded_rectangle((bx0, 118, bx0 + bar_w, 134), radius=3, fill=(56, 189, 248), outline=(224, 242, 254))

    # 5. 轨道 B：0..F 16 格逐帧频闪跑马灯 (y: 142..165) —— 严格每推送 1 帧右移 1 格
    slot16 = frame_seq % 16
    cell_step = 19
    start_x = 8
    for idx in range(16):
        cx0 = start_x + idx * cell_step
        cx1 = cx0 + 16
        dist = (slot16 - idx) % 16
        if dist == 0:
            fill_c = (34, 197, 94)
            txt_c = (5, 20, 12)
        elif dist == 1:
            fill_c = (21, 128, 61)
            txt_c = (200, 245, 215)
        elif dist == 2:
            fill_c = (20, 83, 45)
            txt_c = (134, 197, 156)
        else:
            fill_c = (20, 27, 38)
            txt_c = (82, 96, 116)
        draw.rounded_rectangle((cx0, 143, cx1, 165), radius=3, fill=fill_c)
        lbl = f"{idx:X}"
        lb = draw.textbbox((0, 0), lbl, font=f_xs)
        draw.text((cx0 + (17 - (lb[2] - lb[0])) // 2 - lb[0], 148 - lb[1]), lbl, font=f_xs, fill=txt_c)

    return img


def rgb888_to_rgb565_le(img: Image.Image) -> bytes:
    """快速将 320×170 RGB 图像打包为 108,800 字节小端 RGB565 原始帧。"""
    if img.size != (SCREEN_WIDTH, SCREEN_HEIGHT):
        img = img.resize((SCREEN_WIDTH, SCREEN_HEIGHT), Image.Resampling.BILINEAR)
    if img.mode != "RGB":
        img = img.convert("RGB")
    r_ch, g_ch, b_ch = img.split()
    hi = ImageChops.add(r_ch.point(_R_HI_LUT), g_ch.point(_G_HI_LUT))
    lo = ImageChops.add(g_ch.point(_G_LO_LUT), b_ch.point(_B_LO_LUT))
    return Image.merge("LA", (lo, hi)).tobytes()


def encode_frame_packet(img: Image.Image, fmt: str = "jpeg") -> tuple[bytes, str, str]:
    """
    按选定传输编码打包帧数据并返回 (字节流, Content-Type, Content-Encoding)。
    - rgb565_zlib: 小端 RGB565 + zlib level=1 极速无损压缩（UI/数字画面仅 ~5-7KB，双端编解码 <0.6ms）
    - jpeg: 4:4:4 高清 JPEG (~12-16KB)
    - png: 快速无损 PNG (~12-18KB)
    - rgb565: 原始未压缩 108,800 字节帧（用于测试裸 Wi-Fi 吞吐带宽）
    """
    norm = fmt.strip().lower()
    if norm == "rgb565_zlib":
        raw = rgb888_to_rgb565_le(img)
        return zlib.compress(raw, level=1), "application/octet-stream", "deflate"
    if norm == "rgb565":
        return rgb888_to_rgb565_le(img), "application/octet-stream", ""
    buf = io.BytesIO()
    if norm == "png":
        img.save(buf, format="PNG", compress_level=1)
        return buf.getvalue(), "image/png", ""
    img.save(buf, format="JPEG", quality=85, subsampling=0)
    return buf.getvalue(), "image/jpeg", ""


def encode_frame_payload(img: Image.Image, fmt: str = "jpeg") -> tuple[bytes, str]:
    """兼容二元组调用签名，返回 (字节流, Content-Type)。"""
    payload, ctype, _ = encode_frame_packet(img, fmt=fmt)
    return payload, ctype


class KeepAlivePushClient:
    """
    支持单次合包发送（消除分包 Delayed ACK）与 HTTP/1.1 顺序流水线（Pipelining）的高速推流客户端。
    所有请求均在同一条 TCP 连接上按严格 FIFO 顺序收发，既掩盖无线往返空等，又保证帧顺序绝不乱序。
    """

    def __init__(self, host: str, port: int, token: str = "", timeout: float = 4.0) -> None:
        self.host = host.strip()
        self.port = int(port)
        self.token = token.strip()
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._rfile: io.BufferedReader | None = None

    def _ensure_conn(self) -> tuple[socket.socket, io.BufferedReader]:
        if self._sock is None or self._rfile is None:
            sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 262144)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 131072)
            except OSError:
                pass
            self._sock = sock
            self._rfile = sock.makefile("rb", buffering=65536)
        return self._sock, self._rfile

    def close(self) -> None:
        if self._rfile is not None:
            try:
                self._rfile.close()
            except Exception:
                pass
            self._rfile = None
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def send_push_request(self, payload: bytes, content_type: str, content_encoding: str = "") -> None:
        """将 HTTP 请求头与图像载荷合并为单一字节块一次性写入套接字（不等待响应，用于流水线并发）。"""
        sock, _ = self._ensure_conn()
        hdr_lines = [
            "POST /push HTTP/1.1",
            f"Host: {self.host}:{self.port}",
            f"Content-Type: {content_type}",
            f"Content-Length: {len(payload)}",
            "Connection: keep-alive",
        ]
        if content_encoding:
            hdr_lines.append(f"Content-Encoding: {content_encoding}")
        if self.token:
            hdr_lines.append(f"X-Cast-Token: {self.token}")
        header_bytes = ("\r\n".join(hdr_lines) + "\r\n\r\n").encode("ascii")
        sock.sendall(header_bytes + payload)

    def read_one_response(self) -> dict[str, Any]:
        """按 FIFO 顺序读取最早发出的一个 HTTP/1.1 响应包。"""
        if self._rfile is None:
            raise ConnectionError("连接尚未建立")
        status_line = self._rfile.readline()
        if not status_line:
            self.close()
            raise ConnectionError("对端已关闭连接")

        parts = status_line.split(None, 2)
        if len(parts) < 2 or not parts[1].isdigit():
            self.close()
            raise RuntimeError(f"非法 HTTP 状态行: {status_line!r}")
        status_code = int(parts[1])

        content_length = 0
        conn_close = False
        while True:
            hline = self._rfile.readline()
            if hline in (b"\r\n", b"\n", b""):
                break
            if b":" in hline:
                k, v = hline.split(b":", 1)
                kl = k.strip().lower()
                vl = v.strip().lower()
                if kl == b"content-length":
                    content_length = int(vl)
                elif kl == b"connection" and vl == b"close":
                    conn_close = True

        body = self._rfile.read(content_length) if content_length > 0 else b""
        if len(body) < content_length:
            self.close()
            raise ConnectionError("HTTP 响应体截断")
        if conn_close:
            self.close()

        if status_code != 200:
            msg = body.decode("utf-8", errors="replace")[:160]
            raise RuntimeError(f"HTTP {status_code}: {msg}")
        return json.loads(body.decode("utf-8")) if body else {"ok": True}

    def push_frame(self, payload: bytes, content_type: str, content_encoding: str = "") -> dict[str, Any]:
        """同步一发一收单帧（自动带一次断线重连）。"""
        last_err: Exception | None = None
        for attempt in range(2):
            try:
                self.send_push_request(payload, content_type, content_encoding)
                return self.read_one_response()
            except (OSError, ConnectionError, TimeoutError) as exc:
                last_err = exc
                self.close()
                if attempt == 1:
                    raise
        raise RuntimeError(str(last_err))

    def send_control(self, action: str) -> dict[str, Any]:
        """发送控制指令（如停止测速后恢复待机页 waiting）。"""
        body = json.dumps({"action": action}).encode("utf-8")
        try:
            sock, _ = self._ensure_conn()
            hdr_lines = [
                "POST /api/control HTTP/1.1",
                f"Host: {self.host}:{self.port}",
                "Content-Type: application/json",
                f"Content-Length: {len(body)}",
                "Connection: keep-alive",
            ]
            if self.token:
                hdr_lines.append(f"X-Cast-Token: {self.token}")
            sock.sendall(("\r\n".join(hdr_lines) + "\r\n\r\n").encode("ascii") + body)
            return self.read_one_response()
        except Exception as exc:
            self.close()
            return {"ok": False, "error": str(exc)}


def run_single_tier(
    host: str,
    port: int,
    target_fps: float,
    duration_sec: float = 4.0,
    fmt: str = "jpeg",
    token: str = "",
    pipeline_depth: int = 0,
    lang: str = "zh",
    stop_event: threading.Event | None = None,
    on_frame: Callable[[Image.Image, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """
    以指定目标速率连续推送指定时长，返回实测统计结果字典。
    - target_fps <= 0 表示不限速全速连续推送；
    - pipeline_depth <= 0 时自动决策：低帧率(<12 FPS)用 1，高频(>=12 FPS 或 MAX)自动启用 4 级顺序流水线消除 Wi-Fi 空等。
    """
    if pipeline_depth <= 0:
        eff_pipe = 4 if (target_fps <= 0 or target_fps >= 12.0) else 1
    else:
        eff_pipe = max(1, min(8, int(pipeline_depth)))

    client = KeepAlivePushClient(host=host, port=port, token=token)
    inflight: deque[tuple[float, int, Image.Image]] = deque()
    timestamps: deque[float] = deque()
    byte_window: deque[tuple[float, int]] = deque()

    t_start = time.perf_counter()
    t_end = t_start + max(0.1, duration_sec)
    interval = (1.0 / target_fps) if target_fps > 0 else 0.0
    next_deadline = t_start

    issued_seq = 0
    sent_frames = 0
    errors = 0
    total_bytes = 0
    rtt_sum_ms = 0.0
    dev_ms_sum = 0.0
    dev_ms_count = 0
    rolling_fps = 0.0
    last_display_fps = 0.0
    last_fps_update = 0.0
    last_rtt_ms = 0.0
    rolling_kbps = 0.0
    last_error = ""

    def _consume_one_inflight() -> None:
        nonlocal sent_frames, total_bytes, rtt_sum_ms, dev_ms_sum, dev_ms_count
        nonlocal rolling_fps, last_display_fps, last_fps_update, last_rtt_ms, rolling_kbps
        send_t0, plen, f_img = inflight.popleft()
        res = client.read_one_response()
        done_t = time.perf_counter()
        elapsed_now = done_t - t_start

        last_rtt_ms = (done_t - send_t0) * 1000.0
        rtt_sum_ms += last_rtt_ms
        if isinstance(res.get("process_ms"), (int, float)):
            dev_ms_sum += float(res["process_ms"])
            dev_ms_count += 1

        sent_frames += 1
        total_bytes += plen
        timestamps.append(done_t)
        byte_window.append((done_t, plen))

        while len(timestamps) > 2 and (done_t - timestamps[0]) > 1.2:
            timestamps.popleft()
        while len(byte_window) > 1 and (done_t - byte_window[0][0]) > 1.2:
            byte_window.popleft()

        if len(timestamps) >= 2 and (timestamps[-1] - timestamps[0]) > 0.004:
            rolling_fps = (len(timestamps) - 1) / (timestamps[-1] - timestamps[0])
        elif elapsed_now > 0.004:
            rolling_fps = sent_frames / elapsed_now

        if len(byte_window) >= 2 and (byte_window[-1][0] - byte_window[0][0]) > 0.004:
            win_bytes = sum(b for _, b in list(byte_window)[1:])
            rolling_kbps = (win_bytes / 1024.0) / (byte_window[-1][0] - byte_window[0][0])
        elif elapsed_now > 0.004:
            rolling_kbps = (total_bytes / 1024.0) / elapsed_now

        if sent_frames <= 2 or (done_t - last_fps_update) >= 0.18:
            last_display_fps = rolling_fps
            last_fps_update = done_t

        if on_frame is not None:
            on_frame(
                f_img,
                {
                    "target_fps": target_fps,
                    "actual_fps": round(rolling_fps, 2),
                    "rtt_ms": round(last_rtt_ms, 1),
                    "device_ms": res.get("process_ms"),
                    "kbps": round(rolling_kbps, 1),
                    "sent_frames": sent_frames,
                    "errors": errors,
                    "payload_bytes": plen,
                    "pipeline": eff_pipe,
                },
            )

    try:
        while True:
            now = time.perf_counter()
            if now >= t_end or (stop_event is not None and stop_event.is_set()):
                break

            if interval > 0 and now < next_deadline:
                sleep_s = min(next_deadline - now, t_end - now, 0.04)
                if sleep_s > 0.0005:
                    time.sleep(sleep_s)
                continue

            try:
                while len(inflight) >= eff_pipe:
                    _consume_one_inflight()

                frame_t0 = time.perf_counter()
                issued_seq += 1
                img = render_fps_frame(
                    target_fps=target_fps,
                    actual_fps=last_display_fps,
                    frame_seq=issued_seq,
                    elapsed_sec=frame_t0 - t_start,
                    rtt_ms=last_rtt_ms,
                    kbps=rolling_kbps,
                    fmt=fmt,
                    lang=lang,
                )
                payload, ctype, cenc = encode_frame_packet(img, fmt=fmt)
                client.send_push_request(payload, ctype, cenc)
                inflight.append((frame_t0, len(payload), img))

                if eff_pipe == 1:
                    _consume_one_inflight()
            except Exception as exc:
                errors += 1
                last_error = str(exc)
                inflight.clear()
                client.close()
                time.sleep(0.06)

            if interval > 0:
                next_deadline += interval
                now_after = time.perf_counter()
                if next_deadline < now_after - interval:
                    next_deadline = now_after

        # 收尾排空已在途的流水线帧响应
        while inflight and (stop_event is None or not stop_event.is_set()):
            try:
                _consume_one_inflight()
            except Exception as exc:
                errors += 1
                last_error = str(exc)
                inflight.clear()
                client.close()
                break
    finally:
        client.close()

    total_elapsed = max(0.001, time.perf_counter() - t_start)
    overall_fps = sent_frames / total_elapsed if sent_frames > 0 else 0.0
    avg_rtt = (rtt_sum_ms / sent_frames) if sent_frames > 0 else 0.0
    avg_dev_ms = (dev_ms_sum / dev_ms_count) if dev_ms_count > 0 else 0.0
    avg_kbps = (total_bytes / 1024.0) / total_elapsed

    return {
        "tier": format_tier_label(target_fps, lang=lang),
        "target_fps": target_fps,
        "pipeline": eff_pipe,
        "sent_frames": sent_frames,
        "errors": errors,
        "elapsed_sec": round(total_elapsed, 2),
        "actual_fps": round(overall_fps, 2),
        "avg_rtt_ms": round(avg_rtt, 2),
        "avg_device_ms": round(avg_dev_ms, 2),
        "avg_kbps": round(avg_kbps, 1),
        "last_error": last_error,
    }


# ---------------------------------------------------------------------------
# Tkinter 桌面交互界面
# ---------------------------------------------------------------------------
class FpsTesterDesktopApp:
    """PC 本地可视化多速率连续推流测速窗口。"""

    def __init__(self, host: str, port: int, fmt: str, token: str, pipeline: int = 0) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.root = tk.Tk()
        self.root.title("CardputerZero 局域网连续推流 FPS 测速器 (320×170)")
        self.root.geometry("780x560")
        self.root.minsize(740, 520)
        self.root.configure(bg="#11161F")

        self.host_var = tk.StringVar(value=host)
        self.port_var = tk.StringVar(value=str(port))
        self.token_var = tk.StringVar(value=token)
        self.fmt_var = tk.StringVar(value=fmt)
        self.pipe_var = tk.StringVar(value="auto" if pipeline <= 0 else str(pipeline))
        self.custom_fps_var = tk.StringVar(value="30")

        self.stat_tier_var = tk.StringVar(value="待机未推送")
        self.stat_fps_var = tk.StringVar(value="0.0 FPS")
        self.stat_rtt_var = tk.StringVar(value="-- ms")
        self.stat_bw_var = tk.StringVar(value="0 KB/s")
        self.stat_cnt_var = tk.StringVar(value="0 帧 / 0 错")

        self._worker_thread: threading.Thread | None = None
        self._stop_evt = threading.Event()
        self._ui_lock = threading.Lock()
        self._latest_img: Image.Image | None = None
        self._latest_meta: dict[str, Any] | None = None
        self._tk_photo: ImageTk.PhotoImage | None = None

        self._build_layout()
        init_img = render_fps_frame(30.0, 0.0, 0, 0.0, 0.0, 0.0, fmt=fmt)
        self._update_canvas_image(init_img)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(45, self._poll_ui_updates)

    def _build_layout(self) -> None:
        tk = self.tk
        ttk = self.ttk

        top = tk.Frame(self.root, bg="#18202C", padx=12, pady=8)
        top.pack(fill="x", padx=10, pady=(10, 6))

        tk.Label(top, text="设备 IP:", bg="#18202C", fg="#CBD5E1", font=("Microsoft YaHei UI", 9, "bold")).pack(side="left")
        tk.Entry(top, textvariable=self.host_var, width=14, bg="#0E141D", fg="#F8FAFC", insertbackground="#F8FAFC", relief="flat").pack(side="left", padx=(4, 8), ipady=3)

        tk.Label(top, text="端口:", bg="#18202C", fg="#CBD5E1", font=("Microsoft YaHei UI", 9, "bold")).pack(side="left")
        tk.Entry(top, textvariable=self.port_var, width=5, bg="#0E141D", fg="#F8FAFC", insertbackground="#F8FAFC", relief="flat").pack(side="left", padx=(4, 8), ipady=3)

        tk.Label(top, text="编码:", bg="#18202C", fg="#CBD5E1", font=("Microsoft YaHei UI", 9, "bold")).pack(side="left")
        ttk.Combobox(top, textvariable=self.fmt_var, values=FORMAT_CHOICES, width=11, state="readonly").pack(side="left", padx=(4, 8))

        tk.Label(top, text="流水线:", bg="#18202C", fg="#CBD5E1", font=("Microsoft YaHei UI", 9, "bold")).pack(side="left")
        ttk.Combobox(top, textvariable=self.pipe_var, values=("auto", "1", "2", "4", "6"), width=5, state="readonly").pack(side="left", padx=(4, 8))

        tk.Label(top, text="Token:", bg="#18202C", fg="#94A3B8", font=("Microsoft YaHei UI", 9)).pack(side="left")
        tk.Entry(top, textvariable=self.token_var, width=10, show="*", bg="#0E141D", fg="#F8FAFC", insertbackground="#F8FAFC", relief="flat").pack(side="left", padx=(4, 0), ipady=3)

        rate_box = tk.Frame(self.root, bg="#18202C", padx=12, pady=8)
        rate_box.pack(fill="x", padx=10, pady=4)

        row1 = tk.Frame(rate_box, bg="#18202C")
        row1.pack(fill="x", pady=(0, 6))
        tk.Label(row1, text="点击档位立即连续推送:", bg="#18202C", fg="#93C5FD", font=("Microsoft YaHei UI", 9, "bold")).pack(side="left", padx=(0, 8))

        for r in PRESET_RATES:
            lbl = "MAX 全速" if r <= 0 else f"{int(r)} FPS"
            bg_c = "#B45309" if r <= 0 else "#1E3A5F"
            tk.Button(
                row1,
                text=lbl,
                command=lambda val=r: self.start_continuous_rate(val),
                bg=bg_c,
                fg="#F8FAFC",
                activebackground="#2563EB",
                activeforeground="#FFFFFF",
                relief="flat",
                padx=8,
                pady=3,
                cursor="hand2",
                font=("Segoe UI", 9, "bold"),
            ).pack(side="left", padx=2)

        row2 = tk.Frame(rate_box, bg="#18202C")
        row2.pack(fill="x")
        tk.Label(row2, text="自定义 FPS:", bg="#18202C", fg="#CBD5E1", font=("Microsoft YaHei UI", 9)).pack(side="left")
        tk.Entry(row2, textvariable=self.custom_fps_var, width=6, bg="#0E141D", fg="#F8FAFC", insertbackground="#F8FAFC", relief="flat").pack(side="left", padx=(4, 6), ipady=3)
        tk.Button(
            row2,
            text="按自定义速率推送",
            command=self._start_custom_rate,
            bg="#0F766E",
            fg="#FFFFFF",
            relief="flat",
            padx=9,
            pady=3,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(side="left", padx=(0, 10))

        tk.Button(
            row2,
            text="▶ 阶梯自动巡检 (2→5→10→15→20→30→60→MAX)",
            command=self.start_auto_sweep,
            bg="#0284C7",
            fg="#FFFFFF",
            relief="flat",
            padx=10,
            pady=3,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(side="left", padx=(0, 10))

        tk.Button(
            row2,
            text="■ 停止推送",
            command=lambda: self.stop_push(back_to_waiting=False),
            bg="#475569",
            fg="#FFFFFF",
            relief="flat",
            padx=10,
            pady=3,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            row2,
            text="停止并回待机页",
            command=lambda: self.stop_push(back_to_waiting=True),
            bg="#991B1B",
            fg="#FFFFFF",
            relief="flat",
            padx=10,
            pady=3,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(side="left")

        mid = tk.Frame(self.root, bg="#11161F")
        mid.pack(fill="x", padx=10, pady=6)

        prev_frame = tk.Frame(mid, bg="#0B0E14", bd=2, relief="groove", padx=6, pady=6)
        prev_frame.pack(side="left")
        self.canvas_lbl = tk.Label(prev_frame, bg="#0B0E14")
        self.canvas_lbl.pack()

        stats_card = tk.Frame(mid, bg="#18202C", padx=16, pady=12)
        stats_card.pack(side="left", fill="both", expand=True, padx=(10, 0))

        tk.Label(stats_card, textvariable=self.stat_tier_var, bg="#18202C", fg="#7DD3FC", font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
        tk.Label(stats_card, textvariable=self.stat_fps_var, bg="#18202C", fg="#34D399", font=("Segoe UI", 28, "bold")).pack(anchor="w", pady=(2, 4))

        grid = tk.Frame(stats_card, bg="#18202C")
        grid.pack(fill="x", pady=(4, 0))
        for row_i, (k_txt, var) in enumerate(
            (
                ("单帧耗时 (窗口RTT / 设备):", self.stat_rtt_var),
                ("实时网络吞吐:", self.stat_bw_var),
                ("当前档位已发送:", self.stat_cnt_var),
            )
        ):
            tk.Label(grid, text=k_txt, bg="#18202C", fg="#94A3B8", font=("Microsoft YaHei UI", 9)).grid(row=row_i, column=0, sticky="w", pady=2)
            tk.Label(grid, textvariable=var, bg="#18202C", fg="#F1F5F9", font=("Consolas", 10, "bold")).grid(row=row_i, column=1, sticky="w", padx=(8, 0), pady=2)

        log_wrap = tk.Frame(self.root, bg="#18202C", padx=10, pady=8)
        log_wrap.pack(fill="both", expand=True, padx=10, pady=(2, 10))
        tk.Label(log_wrap, text="测速记录（推荐使用 rgb565_zlib 或 jpeg 冲击高帧率）:", bg="#18202C", fg="#CBD5E1", font=("Microsoft YaHei UI", 9, "bold")).pack(anchor="w", pady=(0, 4))

        self.log_text = tk.Text(log_wrap, height=8, bg="#0D1219", fg="#E2E8F0", font=("Consolas", 10), relief="flat", padx=8, pady=6)
        self.log_text.pack(fill="both", expand=True)
        self._append_log("就绪：点击任意 FPS 按钮可长时间连续推流；rgb565_zlib 采用无损极速压缩，设备端解码 <1ms。")

    def _append_log(self, line: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {line}\n")
        self.log_text.see("end")

    def _update_canvas_image(self, img: Image.Image) -> None:
        scaled = img.resize((400, 212), Image.Resampling.NEAREST)
        self._tk_photo = ImageTk.PhotoImage(scaled)
        self.canvas_lbl.configure(image=self._tk_photo)

    def _on_worker_frame(self, img: Image.Image, meta: dict[str, Any]) -> None:
        with self._ui_lock:
            self._latest_img = img
            self._latest_meta = meta

    def _poll_ui_updates(self) -> None:
        img = None
        meta = None
        with self._ui_lock:
            if self._latest_img is not None:
                img = self._latest_img
                meta = self._latest_meta
                self._latest_img = None
                self._latest_meta = None

        if img is not None:
            self._update_canvas_image(img)
        if meta is not None:
            self.stat_tier_var.set(
                f"连续推送 · 目标 {format_tier_label(meta['target_fps'])} ({self.fmt_var.get()} · 流水线x{meta.get('pipeline', 1)})"
            )
            self.stat_fps_var.set(f"{meta['actual_fps']:.1f} FPS")
            dev_ms = meta.get("device_ms")
            dev_str = f"{dev_ms} ms" if dev_ms is not None else "--"
            self.stat_rtt_var.set(f"{meta['rtt_ms']:.1f} ms / 设备 {dev_str}")
            self.stat_bw_var.set(f"{meta['kbps']:.1f} KB/s ({meta['payload_bytes']} B/帧)")
            self.stat_cnt_var.set(f"{meta['sent_frames']} 帧 / {meta['errors']} 错")

        self.root.after(45, self._poll_ui_updates)

    def _stop_current_worker(self) -> None:
        self._stop_evt.set()
        if self._worker_thread is not None and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.5)
        self._worker_thread = None
        self._stop_evt = threading.Event()

    def _read_connection_params(self) -> tuple[str, int, str, str, int]:
        host = self.host_var.get().strip() or DEFAULT_HOST
        try:
            port = max(1, min(65535, int(self.port_var.get().strip())))
        except ValueError:
            port = DEFAULT_PORT
        fmt = self.fmt_var.get().strip() or "rgb565_zlib"
        tok = self.token_var.get().strip()
        p_raw = self.pipe_var.get().strip().lower()
        pipe = 0 if p_raw == "auto" else int(p_raw)
        return host, port, fmt, tok, pipe

    def _start_custom_rate(self) -> None:
        try:
            val = float(self.custom_fps_var.get().strip())
        except ValueError:
            val = 30.0
        self.start_continuous_rate(max(0.0, val))

    def start_continuous_rate(self, target_fps: float) -> None:
        self._stop_current_worker()
        host, port, fmt, tok, pipe = self._read_connection_params()
        stop_evt = self._stop_evt
        self._append_log(f"开始连续推送 -> {host}:{port} | 档位={format_tier_label(target_fps)} | 编码={fmt}")

        def _worker() -> None:
            res = run_single_tier(
                host=host,
                port=port,
                target_fps=target_fps,
                duration_sec=3600.0,
                fmt=fmt,
                token=tok,
                pipeline_depth=pipe,
                stop_event=stop_evt,
                on_frame=self._on_worker_frame,
            )
            self.root.after(
                0,
                lambda: self._append_log(
                    f"档位 [{res['tier']}] 结束: 实测={res['actual_fps']} FPS | 窗口RTT={res['avg_rtt_ms']}ms | "
                    f"设备处理={res['avg_device_ms']}ms | 带宽={res['avg_kbps']} KB/s | 帧数={res['sent_frames']} (错:{res['errors']})"
                    + (f" | 提示:{res['last_error']}" if res["last_error"] else "")
                ),
            )

        self._worker_thread = threading.Thread(target=_worker, daemon=True)
        self._worker_thread.start()

    def start_auto_sweep(self) -> None:
        self._stop_current_worker()
        host, port, fmt, tok, pipe = self._read_connection_params()
        stop_evt = self._stop_evt
        self._append_log(f"=== 启动阶梯自动巡检 ({host}:{port}, 编码={fmt}, 每档 3.0s) ===")

        def _sweep_worker() -> None:
            results: list[dict[str, Any]] = []
            for tier_fps in SWEEP_TIERS:
                if stop_evt.is_set():
                    break
                res = run_single_tier(
                    host=host,
                    port=port,
                    target_fps=tier_fps,
                    duration_sec=3.0,
                    fmt=fmt,
                    token=tok,
                    pipeline_depth=pipe,
                    stop_event=stop_evt,
                    on_frame=self._on_worker_frame,
                )
                results.append(res)
                self.root.after(
                    0,
                    lambda r=res: self._append_log(
                        f"  • {r['tier']:<8} -> 实测 {r['actual_fps']:>5.1f} FPS | RTT {r['avg_rtt_ms']:>5.1f}ms | "
                        f"设备 {r['avg_device_ms']:>5.1f}ms | {r['avg_kbps']:>6.1f} KB/s | {r['sent_frames']}帧"
                    ),
                )
            if results and not stop_evt.is_set():
                peak = max(r["actual_fps"] for r in results)
                self.root.after(
                    0,
                    lambda: (
                        self.stat_tier_var.set(f"阶梯巡检完成 · 最高达成 {peak:.1f} FPS"),
                        self._append_log(f"=== 巡检完成：当前网络与 {fmt} 编码最高可持续帧率约 {peak:.1f} FPS ==="),
                    ),
                )

        self._worker_thread = threading.Thread(target=_sweep_worker, daemon=True)
        self._worker_thread.start()

    def stop_push(self, back_to_waiting: bool = False) -> None:
        self._stop_current_worker()
        self.stat_tier_var.set("已停止推送")
        if back_to_waiting:
            host, port, _, tok, _ = self._read_connection_params()
            cli = KeepAlivePushClient(host=host, port=port, token=tok)
            cli.send_control("waiting")
            cli.close()
            self._append_log("已停止推送并通知设备切回待机页。")

    def _on_close(self) -> None:
        self._stop_current_worker()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def _run_cli(args: argparse.Namespace) -> int:
    tiers: list[float]
    if args.sweep:
        tiers = [float(x.strip()) for x in args.tiers.split(",") if x.strip() != ""]
    else:
        tiers = [args.fps]

    print(
        f"[pc-fps-tester] 目标 http://{args.host}:{args.port}/push | 编码={args.format} | "
        f"流水线={'auto' if args.pipeline <= 0 else args.pipeline} | 每档时长={args.duration}s",
        flush=True,
    )
    print("-" * 86, flush=True)
    print(f"{'目标档位':<12} {'实测FPS':>9} {'流水线':>6} {'已推帧数':>8} {'窗口RTT(ms)':>12} {'设备耗时(ms)':>13} {'平均吞吐(KB/s)':>15}", flush=True)
    print("-" * 86, flush=True)

    peak_fps = 0.0
    for t_fps in tiers:
        res = run_single_tier(
            host=args.host,
            port=args.port,
            target_fps=t_fps,
            duration_sec=args.duration,
            fmt=args.format,
            token=args.token,
            pipeline_depth=args.pipeline,
            lang=args.lang,
        )
        peak_fps = max(peak_fps, res["actual_fps"])
        err_suffix = f"  [错误: {res['last_error']}]" if res["errors"] else ""
        print(
            f"{res['tier']:<12} {res['actual_fps']:>9.2f} {res['pipeline']:>6d} {res['sent_frames']:>8d} "
            f"{res['avg_rtt_ms']:>12.2f} {res['avg_device_ms']:>13.2f} {res['avg_kbps']:>15.1f}{err_suffix}",
            flush=True,
        )

    print("-" * 86, flush=True)
    print(f"峰值可持续帧率: {peak_fps:.2f} FPS ({args.format})", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="CardputerZero PC 端多速率连续推流 FPS 测速工具")
    parser.add_argument("--host", type=str, default=DEFAULT_HOST, help="CardputerZero 设备 IP")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="服务端口（默认 8787）")
    parser.add_argument("--format", choices=FORMAT_CHOICES, default="rgb565_zlib", help="推流图像编码格式")
    parser.add_argument("--lang", choices=("zh", "en"), default="zh", help="测速画面语言：zh | en")
    parser.add_argument("--pipeline", type=int, default=0, help="HTTP/1.1 顺序流水线深度（0 为高频自动 4 级）")
    parser.add_argument("--token", type=str, default="", help="可选鉴权口令 X-Cast-Token")
    parser.add_argument("--cli", action="store_true", help="使用命令行模式运行测速（默认打开桌面窗口）")
    parser.add_argument("--sweep", action="store_true", help="命令行模式下依次运行多档速率阶梯巡检")
    parser.add_argument("--tiers", type=str, default="2,5,10,15,20,30,60,0", help="阶梯巡检速率列表（0 代表 MAX 全速）")
    parser.add_argument("--fps", type=float, default=0.0, help="单档命令行测速目标 FPS（0 代表 MAX 全速）")
    parser.add_argument("--duration", type=float, default=2.5, help="每档持续推送秒数")
    args = parser.parse_args()

    if args.cli or args.sweep:
        return _run_cli(args)

    app = FpsTesterDesktopApp(host=args.host, port=args.port, fmt=args.format, token=args.token, pipeline=args.pipeline)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
