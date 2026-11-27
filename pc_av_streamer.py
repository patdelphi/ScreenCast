#!/usr/bin/env python3
"""
程序说明：CardputerZero PC 端自适应混合压缩音视频推流客户端（pc_av_streamer.py）。

设计目的（将重计算全放 PC 端，兼顾最小 Wi-Fi 带宽与最低设备端 CPU 解压开销）：
1. 视频解码、缩放、旋转、色彩抖动与时域感光噪点门限过滤全部在 PC 端完成；
2. 逐帧智能选择最优编码（CP0S 混合二进制流协议）：
   - 静止 / 对话 / 动画 / 桌面窗口场景：发送“时域降噪 XOR 帧间差分 RGB565 + zlib(1)”（包类型 0x02），
     设备端无需运行 JPEG 解码与 RGB888->RGB565 转换，仅用 C 层 zlib + 大整数异或直刷显存（<0.5ms）；
   - 大幅运动 / 镜头切换场景：当无损差分包体积偏大时，自动切换为预缩放 320×170 小体积 JPEG（包类型 0x03，约 10KB），
     将 2.4GHz Wi-Fi 带宽稳定压制在 200–320 KB/s，彻底消除无线信道拥塞卡顿；
3. 单条 TCP_NODELAY 长连接复用传输音视频包，零逐帧 HTTP 头与停等 RTT 损耗。
"""

from __future__ import annotations

import argparse
import io
import shutil
import socket
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

from PIL import Image, ImageChops

SCREEN_WIDTH = 320
SCREEN_HEIGHT = 170
FRAME_RGB24_BYTES = SCREEN_WIDTH * SCREEN_HEIGHT * 3
FRAME_RGB565_BYTES = SCREEN_WIDTH * SCREEN_HEIGHT * 2

_R_HI_LUT = [i & 0xF8 for i in range(256)]
_G_HI_LUT = [i >> 5 for i in range(256)]
_G_LO_LUT = [(i << 3) & 0xE0 for i in range(256)]
_B_LO_LUT = [i >> 3 for i in range(256)]


def pack_rgb565_le(img: Image.Image) -> bytes:
    """在 PC 端将 320×170 RGB 图像打包为 108,800 字节小端 RGB565。"""
    r_ch, g_ch, b_ch = img.split()
    hi = ImageChops.add(r_ch.point(_R_HI_LUT), g_ch.point(_G_HI_LUT))
    lo = ImageChops.add(g_ch.point(_G_LO_LUT), b_ch.point(_B_LO_LUT))
    return Image.merge("LA", (lo, hi)).tobytes()


class HybridCp0sEncoder:
    """PC 端时域降噪 + XOR 帧间差分 / JPEG 自适应混合编码器。"""

    def __init__(self, jpeg_quality: int = 74, delta_max_bytes: int = 15360, noise_gate: int = 6) -> None:
        self.jpeg_quality = max(40, min(95, int(jpeg_quality)))
        self.delta_max_bytes = max(4096, int(delta_max_bytes))
        self._gate_lut = [0 if i <= max(0, int(noise_gate)) else 255 for i in range(256)]
        self._prev_rgb: Image.Image | None = None
        self._last_jpeg_rgb: Image.Image | None = None
        self._prev_565_int: int = 0
        self._since_key: int = 0

    def encode_frame(self, rgb_320x170: Image.Image) -> tuple[int, bytes]:
        """返回 (pkt_type, payload_bytes)，pkt_type: 0x01=关键帧, 0x02=XOR差分, 0x03=JPEG。"""
        if self._prev_rgb is None or self._since_key >= 90:
            # 若刚经历镜头切换 JPEG 帧且当前画面已趋于稳定，立即插入关键帧使后续帧恢复零 JPEG 负担的 0x02 差分模式
            calm_after_jpeg = False
            if self._prev_rgb is None and self._last_jpeg_rgb is not None:
                d_mask = ImageChops.difference(rgb_320x170, self._last_jpeg_rgb).convert("L").point(self._gate_lut)
                changed_px = d_mask.histogram()[255]
                calm_after_jpeg = changed_px < int(SCREEN_WIDTH * SCREEN_HEIGHT * 0.16)

            raw565 = pack_rgb565_le(rgb_320x170)
            z_key = zlib.compress(raw565, 1)
            if calm_after_jpeg or len(z_key) <= self.delta_max_bytes * 2:
                self._prev_rgb = rgb_320x170
                self._last_jpeg_rgb = None
                self._prev_565_int = int.from_bytes(raw565, "little")
                self._since_key = 1
                return 0x01, z_key

        if self._prev_rgb is not None:
            # 时域感光噪点过滤：微小颗粒抖动复用上一帧像素，使静止背景差分严格归零
            diff_gray = ImageChops.difference(rgb_320x170, self._prev_rgb).convert("L")
            motion_mask = diff_gray.point(self._gate_lut)
            stabilized = Image.composite(rgb_320x170, self._prev_rgb, motion_mask)
            raw565 = pack_rgb565_le(stabilized)
            cur_int = int.from_bytes(raw565, "little")
            xor_bytes = (cur_int ^ self._prev_565_int).to_bytes(FRAME_RGB565_BYTES, "little")
            z_delta = zlib.compress(xor_bytes, 1)
            if len(z_delta) <= self.delta_max_bytes:
                self._prev_rgb = stabilized
                self._prev_565_int = cur_int
                self._since_key += 1
                return 0x02, z_delta

        # 剧烈运动或全屏切换镜头：回退到小体积 320×170 JPEG，并记录画面供下一静止镜头切回 0x02 差分
        jbuf = io.BytesIO()
        rgb_320x170.save(jbuf, format="JPEG", quality=self.jpeg_quality)
        self._prev_rgb = None
        self._last_jpeg_rgb = rgb_320x170
        self._prev_565_int = 0
        self._since_key = 0
        return 0x03, jbuf.getvalue()


def _send_http_chunk(sock: socket.socket, data: bytes) -> None:
    if not data:
        return
    sock.sendall(f"{len(data):X}\r\n".encode("ascii") + data + b"\r\n")


def build_cp0s_header(audio_rate: int = 24000, channels: int = 1) -> bytes:
    flags = 0x01 if channels == 2 else 0x00
    return b"CP0S" + struct.pack("<BBH", 1, flags, int(audio_rate))


def pack_cp0s_packet(pkt_type: int, payload: bytes) -> bytes:
    return struct.pack("<BI", pkt_type, len(payload)) + payload


def stream_media_file(
    media_path: str,
    host: str,
    port: int = 8787,
    fps: int = 24,
    fit: str = "contain",
    rotate: str | int = "auto",
    audio_rate: int = 24000,
    jpeg_quality: int = 74,
    token: str = "",
    realtime: bool = True,
) -> int:
    """在 PC 端调用 ffmpeg 解码任意视频文件，通过 CP0S 混合压缩流推送到 CardputerZero。"""
    ff_bin = shutil.which("ffmpeg")
    if not ff_bin:
        print("错误：未在 PATH 中找到 ffmpeg，请先安装 ffmpeg。", file=sys.stderr)
        return 1

    rot_str = str(rotate).strip().lower()
    if rot_str == "auto":
        rot_prefix = "transpose=clock:passthrough=landscape,"
    else:
        rot_prefix = {"90": "transpose=1,", "180": "hflip,vflip,", "270": "transpose=2,"}.get(rot_str, "")
    if fit == "stretch":
        scale_expr = f"scale={SCREEN_WIDTH}:{SCREEN_HEIGHT}"
    elif fit == "cover":
        scale_expr = f"scale={SCREEN_WIDTH}:{SCREEN_HEIGHT}:force_original_aspect_ratio=increase,crop={SCREEN_WIDTH}:{SCREEN_HEIGHT}"
    else:
        scale_expr = (
            f"scale={SCREEN_WIDTH}:{SCREEN_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={SCREEN_WIDTH}:{SCREEN_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black"
        )

    cmd = [ff_bin, "-v", "error"]
    if realtime:
        cmd.append("-re")
    cmd.extend([
        "-i", media_path,
        "-map", "0:v:0?",
        "-map", "0:a:0?",
        "-vf", f"fps={fps},{rot_prefix}{scale_expr}",
        "-c:v", "rawvideo",
        "-pix_fmt", "rgb24",
        "-ar", str(audio_rate),
        "-ac", "1",
        "-c:a", "pcm_s16le",
        "-flush_packets", "1",
        "-f", "avi",
        "-",
    ])

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=131072)
    encoder = HybridCp0sEncoder(jpeg_quality=jpeg_quality)
    sock: socket.socket | None = None

    try:
        sock = socket.create_connection((host, port), timeout=8.0)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        tok_hdr = f"X-Cast-Token: {token}\r\n" if token else ""
        stream_path = "/stream" if realtime else "/stream?pace=0"
        req_head = (
            f"POST {stream_path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"{tok_hdr}"
            f"Content-Type: application/octet-stream\r\n"
            f"Transfer-Encoding: chunked\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("ascii")
        sock.sendall(req_head)
        _send_http_chunk(sock, build_cp0s_header(audio_rate=audio_rate, channels=1))

        assert proc.stdout is not None
        buf = bytearray()
        read_pos = 0
        in_movi = False
        sent_frames = 0
        delta_count = 0
        jpeg_count = 0
        sent_bytes = 0
        t_report = time.perf_counter()

        while True:
            chunk = proc.stdout.read(65536)
            if not chunk:
                break
            buf.extend(chunk)

            if not in_movi:
                movi_idx = buf.find(b"movi", read_pos)
                if movi_idx < 0:
                    continue
                read_pos = movi_idx + 4
                in_movi = True

            out_batch = bytearray()
            buf_len = len(buf)
            while in_movi and (buf_len - read_pos) >= 8:
                c2 = buf[read_pos + 2 : read_pos + 4]
                size = struct.unpack_from("<I", buf, read_pos + 4)[0]
                if c2 == b"ST" and buf[read_pos : read_pos + 4] == b"LIST":
                    if (buf_len - read_pos) < 12:
                        break
                    read_pos += 12
                    continue
                if c2 == b"x1" and buf[read_pos : read_pos + 4] == b"idx1":
                    in_movi = False
                    break
                padded = size + (size & 1)
                if (buf_len - read_pos) < 8 + padded:
                    break
                d_start = read_pos + 8
                d_end = d_start + size
                read_pos += 8 + padded

                if c2 in (b"dc", b"db") and size == FRAME_RGB24_BYTES:
                    im = Image.frombytes("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), bytes(buf[d_start:d_end]))
                    ptype, pdata = encoder.encode_frame(im)
                    pkt = pack_cp0s_packet(ptype, pdata)
                    out_batch.extend(pkt)
                    sent_frames += 1
                    sent_bytes += len(pkt)
                    if ptype in (0x01, 0x02):
                        delta_count += 1
                    else:
                        jpeg_count += 1
                elif c2 == b"wb" and size > 0:
                    pkt = pack_cp0s_packet(0x10, bytes(buf[d_start:d_end]))
                    out_batch.extend(pkt)
                    sent_bytes += len(pkt)

            if out_batch:
                _send_http_chunk(sock, bytes(out_batch))

            if read_pos > 0:
                if read_pos >= len(buf):
                    buf.clear()
                    read_pos = 0
                elif read_pos >= 262144:
                    del buf[:read_pos]
                    read_pos = 0

            now = time.perf_counter()
            if (now - t_report) >= 2.0 and sent_frames > 0:
                kbps = (sent_bytes / 1024.0) / (now - t_report)
                print(
                    f"[CP0S] 已推 {sent_frames} 帧 | 速率 {kbps:.1f} KB/s | "
                    f"零JPEG差分帧={delta_count} 镜头切换JPEG帧={jpeg_count}",
                    flush=True,
                )
                sent_bytes = 0
                t_report = now

        _send_http_chunk(sock, pack_cp0s_packet(0xFF, b""))
        sock.sendall(b"0\r\n\r\n")
        try:
            sock.recv(4096)
        except OSError:
            pass
        return 0
    except KeyboardInterrupt:
        print("\n已停止推流。")
        return 0
    except OSError as exc:
        print(f"连接或推流异常: {exc}", file=sys.stderr)
        return 1
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        try:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=1.0)
        except Exception:
            pass
        for pipe in (proc.stdout, proc.stderr):
            if pipe is not None:
                try:
                    pipe.close()
                except Exception:
                    pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CardputerZero PC 端 CP0S 自适应混合压缩音视频推流工具")
    parser.add_argument("media", type=str, help="本地视频或音频文件路径（如 movie.mp4）")
    parser.add_argument("--host", type=str, required=True, help="CardputerZero 设备 IP（如 192.168.31.251）")
    parser.add_argument("--port", type=int, default=8787, help="服务端口（默认 8787）")
    parser.add_argument("--fps", type=int, default=24, help="推送目标帧率（默认 24）")
    parser.add_argument("--fit", choices=("contain", "cover", "stretch"), default="contain", help="画面缩放策略")
    parser.add_argument(
        "--rotate",
        type=str,
        choices=("auto", "0", "90", "180", "270"),
        default="auto",
        help="旋转模式：auto（默认，竖屏视频自动顺时针90°横显）或手动固定角度 0/90/180/270",
    )
    parser.add_argument("--quality", type=int, default=74, help="剧烈运动帧 JPEG 质量 (40-95，默认 74)")
    parser.add_argument("--token", type=str, default="", help="可选 X-Cast-Token 鉴权口令")
    parser.add_argument("--no-realtime", action="store_true", help="关闭实时匀速限速（用于基准测速与单元测试）")
    args = parser.parse_args(argv)

    if not Path(args.media).is_file():
        print(f"文件不存在: {args.media}", file=sys.stderr)
        return 1
    return stream_media_file(
        media_path=args.media,
        host=args.host,
        port=args.port,
        fps=max(1, min(60, args.fps)),
        fit=args.fit,
        rotate=args.rotate,
        jpeg_quality=args.quality,
        token=args.token,
        realtime=not args.no_realtime,
    )


if __name__ == "__main__":
    sys.exit(main())
