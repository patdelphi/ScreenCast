#!/usr/bin/env python3
"""
程序说明：CardputerZero 网页控台与无线投屏测试应用（apps/screen-cast）自动化回归测试套件。

测试覆盖：
1. .env 配置解析、边界校验、行内中文注释保留与非法参数拦截；
2. RGB888 <-> RGB565 小端序（108,800 字节）精确打包与解包、防色带抖动与各色彩/缩放/旋转/亮度管线；
3. 10 类内置屏幕测试样张（5 类 App UI + 2 类测试图片 + 3 类硬件标定卡）完整性与像素分布校验；
4. HTTP 服务全端点（控台静态页、/push 多格式推图、样张切换、实时调参、鉴权 401 与畸形输入 400 处理）；
5. build_deb.py 生成的 arm64 .deb 包结构与 APPLaunch 启动项校验。
"""

from __future__ import annotations

import io
import json
import shutil
import socket
import struct
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
import wave
import zlib
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image, ImageStat

APP_DIR = Path(__file__).resolve().parent.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import build_deb  # noqa: E402
import cp0_cast_app as app_mod  # noqa: E402
import pc_av_streamer as streamer_mod  # noqa: E402


class TestConfigAndPixelPipeline(unittest.TestCase):
    """验证配置解析保存与 RGB565 图像处理管线。"""

    def test_env_load_validate_and_save_preserves_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "LISTEN_PORT=8788   # 自定义端口\r\n"
                "CAST_TOKEN=   # 留空不启用鉴权\r\n"
                "COLOR_MODE=rgb565_dither # 防色带抖动\r\n",
                encoding="utf-8",
            )
            cfg = app_mod.load_env_config(env_path)
            self.assertEqual(cfg["LISTEN_PORT"], 8788)
            self.assertEqual(cfg["CAST_TOKEN"], "")
            self.assertEqual(cfg["COLOR_MODE"], "rgb565_dither")

            updated, errors = app_mod.validate_and_normalize_config(
                {
                    **cfg,
                    "TARGET_FPS": 30,
                    "FIT_MODE": "cover",
                    "ROTATE": 180,
                    "BRIGHTNESS": 115,
                    "CONTRAST": 110,
                    "SATURATION": 120,
                    "INVERT": True,
                }
            )
            self.assertEqual(errors, {})
            app_mod.save_env_config(env_path, updated)

            saved_text = env_path.read_text(encoding="utf-8")
            self.assertIn("#", saved_text)
            self.assertNotIn("\ufeff", saved_text)
            reloaded = app_mod.load_env_config(env_path)
            self.assertEqual(reloaded["TARGET_FPS"], 30)
            self.assertEqual(reloaded["FIT_MODE"], "cover")
            self.assertEqual(reloaded["ROTATE"], 180)
            self.assertEqual(reloaded["BRIGHTNESS"], 115)
            self.assertTrue(reloaded["INVERT"])

            _, bad_errors = app_mod.validate_and_normalize_config(
                {
                    **cfg,
                    "UI_LANG": "fr",
                    "TARGET_FPS": 150,
                    "LISTEN_PORT": 70000,
                    "COLOR_MODE": "invalid_mode",
                    "ROTATE": 45,
                    "CAST_TOKEN": "bad\nline",
                }
            )
            self.assertIn("UI_LANG", bad_errors)
            self.assertIn("TARGET_FPS", bad_errors)
            self.assertIn("LISTEN_PORT", bad_errors)
            self.assertIn("COLOR_MODE", bad_errors)
            self.assertIn("ROTATE", bad_errors)
            self.assertIn("CAST_TOKEN", bad_errors)

            cn_alias, cn_err = app_mod.validate_and_normalize_config({**cfg, "UI_LANG": "cn"})
            self.assertEqual(cn_err, {})
            self.assertEqual(cn_alias["UI_LANG"], "zh")

            # 验证默认不显示角标 (SHOW_OVERLAY=False) 且默认开启自动旋转 (ROTATE='auto')，保存重载保持一致
            def_cfg = app_mod.default_config()
            self.assertFalse(def_cfg["SHOW_OVERLAY"])
            self.assertEqual(def_cfg["ROTATE"], "auto")
            app_mod.save_env_config(env_path, def_cfg)
            reloaded_auto = app_mod.load_env_config(env_path)
            self.assertEqual(reloaded_auto["ROTATE"], "auto")
            self.assertFalse(reloaded_auto["SHOW_OVERLAY"])

            # 验证自动旋转与手动旋转互斥：竖屏图 (170x320) 在 auto 下自动顺时针转 90°（左上红块移至右上角），切手动 0° 则保持左上角
            portrait = Image.new("RGB", (170, 320), (0, 0, 0))
            portrait.paste((255, 0, 0), (0, 0, 12, 12))
            raw_auto, _, _ = app_mod.process_image_to_frame(portrait, {**def_cfg, "ROTATE": "auto", "FIT_MODE": "stretch"})
            img_auto = app_mod.rgb565_bytes_to_image(raw_auto)
            self.assertEqual(img_auto.getpixel((319, 0)), (255, 0, 0))
            self.assertEqual(img_auto.getpixel((0, 0)), (0, 0, 0))

            raw_manual0, _, _ = app_mod.process_image_to_frame(portrait, {**def_cfg, "ROTATE": 0, "FIT_MODE": "stretch"})
            img_manual0 = app_mod.rgb565_bytes_to_image(raw_manual0)
            self.assertEqual(img_manual0.getpixel((0, 0)), (255, 0, 0))
            self.assertEqual(img_manual0.getpixel((319, 0)), (0, 0, 0))

            # 横屏图 (320x170) 在 auto 下保持 0° 不旋转
            landscape = Image.new("RGB", (320, 170), (0, 0, 0))
            landscape.putpixel((0, 0), (0, 255, 0))
            raw_land_auto, _, _ = app_mod.process_image_to_frame(landscape, {**def_cfg, "ROTATE": "auto"})
            self.assertEqual(app_mod.rgb565_bytes_to_image(raw_land_auto).getpixel((0, 0)), (0, 255, 0))

    def test_rgb565_little_endian_exact_values_and_roundtrip(self) -> None:
        img = Image.new("RGB", (app_mod.SCREEN_WIDTH, app_mod.SCREEN_HEIGHT), (0, 0, 0))
        img.putpixel((0, 0), (255, 0, 0))    # 纯红 -> 0xF800
        img.putpixel((1, 0), (0, 255, 0))    # 纯绿 -> 0x07E0
        img.putpixel((2, 0), (0, 0, 255))    # 纯蓝 -> 0x001F
        img.putpixel((3, 0), (255, 255, 255))  # 纯白 -> 0xFFFF

        raw = app_mod.rgb888_to_rgb565_bytes(img, dither=False)
        self.assertEqual(len(raw), app_mod.FRAME_BYTES)
        self.assertEqual(len(raw), 320 * 170 * 2)

        p0, p1, p2, p3 = struct.unpack_from("<HHHH", raw, 0)
        self.assertEqual(p0, 0xF800)
        self.assertEqual(p1, 0x07E0)
        self.assertEqual(p2, 0x001F)
        self.assertEqual(p3, 0xFFFF)

        restored = app_mod.rgb565_bytes_to_image(raw)
        self.assertEqual(restored.size, (320, 170))
        self.assertEqual(restored.getpixel((0, 0)), (255, 0, 0))
        self.assertEqual(restored.getpixel((1, 0)), (0, 255, 0))
        self.assertEqual(restored.getpixel((2, 0)), (0, 0, 255))
        self.assertEqual(restored.getpixel((3, 0)), (255, 255, 255))

    def test_dither_and_color_modes_produce_valid_frames(self) -> None:
        grad = app_mod.generate_sample_image("cal_gradients")
        base_cfg = app_mod.default_config()

        raw_plain, _, _ = app_mod.process_image_to_frame(grad, {**base_cfg, "COLOR_MODE": "rgb565"})
        raw_dither, _, _ = app_mod.process_image_to_frame(grad, {**base_cfg, "COLOR_MODE": "rgb565_dither"})
        self.assertEqual(len(raw_plain), app_mod.FRAME_BYTES)
        self.assertEqual(len(raw_dither), app_mod.FRAME_BYTES)
        # 渐变图开启误差扩散抖动后，像素分布应与直接截断存在差异以消除色带
        self.assertNotEqual(raw_plain, raw_dither)

        for mode in ("gray", "mono_floyd", "mono_threshold"):
            raw_m, png_m, sha_m = app_mod.process_image_to_frame(grad, {**base_cfg, "COLOR_MODE": mode})
            self.assertEqual(len(raw_m), app_mod.FRAME_BYTES)
            self.assertTrue(len(sha_m) == 64)
            decoded = Image.open(io.BytesIO(png_m))
            self.assertEqual(decoded.size, (320, 170))


class TestSampleGallery(unittest.TestCase):
    """验证全部 10 类内置样张（App UI / 测试图片 / 标定卡）渲染有效。"""

    def test_all_ten_patterns_render_distinct_320x170_images(self) -> None:
        patterns = app_mod.list_sample_patterns()
        self.assertGreaterEqual(len(patterns), 10)
        categories = {item["category"] for item in patterns}
        self.assertEqual(categories, {"app_ui", "photo", "calibration"})

        hashes = set()
        for item in patterns:
            pid = item["id"]
            img = app_mod.generate_sample_image(pid)
            self.assertEqual(img.size, (320, 170), f"样张尺寸错误: {pid}")
            self.assertEqual(img.mode, "RGB")
            stddev = max(ImageStat.Stat(img).stddev)
            # 确保不是纯色空白画面
            self.assertGreater(stddev, 8.0, f"样张对比度过低或空白: {pid}")
            raw = app_mod.rgb888_to_rgb565_bytes(img)
            hashes.add(raw)

        self.assertEqual(len(hashes), len(patterns), "存在重复的测试样张渲染结果")

        # 验证英文与中文模式在含文案样张与待机页上能分别正常渲染且像素不同
        zh_dash = app_mod.rgb888_to_rgb565_bytes(app_mod.generate_sample_image("ui_dashboard", lang="zh"))
        en_dash = app_mod.rgb888_to_rgb565_bytes(app_mod.generate_sample_image("ui_dashboard", lang="en"))
        self.assertNotEqual(zh_dash, en_dash)

        en_patterns = app_mod.list_sample_patterns(lang="en")
        self.assertEqual(en_patterns[0]["title"], en_patterns[0]["title_en"])


class TestHttpServerEndToEnd(unittest.TestCase):
    """端到端测试网页控台服务与各类推送/控制异常分支。"""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.env_path = Path(self.tmp_dir.name) / ".env"
        self.fb = app_mod.MemoryFramebuffer(320, 170)
        self.diag_log_path = Path(self.tmp_dir.name) / "cp0-screen-cast.log"
        self.runtime = app_mod.ScreenCastRuntime(
            env_path=self.env_path,
            web_dir=APP_DIR / "web",
            framebuffer=self.fb,
            diag_log_path=self.diag_log_path,
        )
        self.runtime.render_waiting_screen()
        self.server = app_mod.create_http_server("127.0.0.1", 0, self.runtime)
        self.port = self.server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.runtime.close()
        self.tmp_dir.cleanup()

    def _req(self, path: str, method: str = "GET", body: bytes | None = None, headers: dict | None = None):
        req = Request(f"{self.base_url}{path}", data=body, method=method, headers=headers or {})
        with urlopen(req, timeout=5) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read()

    def test_static_pages_patterns_and_preview_work(self) -> None:
        status, ctype, html = self._req("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", ctype)
        self.assertIn("320×170".encode("utf-8"), html)
        self.assertIn(b"btn-toggle-lang", html)
        self.assertIn(b'id="TARGET_FPS"', html)
        self.assertIn(b'class="panel cast-hub-card"', html)
        self.assertIn(b'id="image-file-name"', html)
        self.assertIn(b'id="media-file-name"', html)
        self.assertIn(b'class="hub-divider"', html)

        css_status, css_type, css_bytes = self._req("/app.css")
        self.assertEqual(css_status, 200)
        self.assertIn("text/css", css_type)
        self.assertIn(b".filename-box", css_bytes)
        self.assertIn(b"@container configcard", css_bytes)

        js_status, js_type, js_bytes = self._req("/app.js")
        self.assertEqual(js_status, 200)
        self.assertIn("javascript", js_type)
        self.assertIn(b"renderFilenameKeepExt", js_bytes)

        status, _, patterns_raw = self._req("/api/patterns?lang=en")
        self.assertEqual(status, 200)
        pdata = json.loads(patterns_raw.decode("utf-8"))
        self.assertTrue(pdata["ok"])
        self.assertEqual(pdata["lang"], "en")
        self.assertGreaterEqual(len(pdata["patterns"]), 10)

        # 待机态下 /preview.png 也应返回有效 320x170 PNG
        status, ptype, png_bytes = self._req("/preview.png")
        self.assertEqual(status, 200)
        self.assertIn("image/png", ptype)
        preview_img = Image.open(io.BytesIO(png_bytes))
        self.assertEqual(preview_img.size, (320, 170))

    def test_push_png_multipart_raw_rgb565_and_pattern_switch(self) -> None:
        # 1. 推送任意尺寸彩色 PNG（如 640x360）
        src = Image.new("RGB", (640, 360), (20, 120, 220))
        buf = io.BytesIO()
        src.save(buf, format="PNG")
        status, _, resp_raw = self._req(
            "/push",
            method="POST",
            body=buf.getvalue(),
            headers={"Content-Type": "image/png"},
        )
        self.assertEqual(status, 200)
        res = json.loads(resp_raw.decode("utf-8"))
        self.assertEqual(res["frame_bytes"], 108800)
        self.assertEqual(res["mode"], "casting")
        self.assertEqual(len(self.fb.last_bytes), 108800)

        # 2. multipart/form-data 上传
        boundary = "----TestBoundary7MA4YWxkTrZu0gW"
        part = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="sample.png"\r\n'
            f"Content-Type: image/png\r\n\r\n"
        ).encode("utf-8") + buf.getvalue() + f"\r\n--{boundary}--\r\n".encode("utf-8")
        status, _, _ = self._req(
            "/push",
            method="POST",
            body=part,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        self.assertEqual(status, 200)

        # 3. 直接推送原始 108,800 字节 RGB565 帧，以及 deflate 压缩 RGB565 帧 + 惰性预览与重算校验
        raw_frame = b"\x1f\x00" * (320 * 170)  # 全屏纯蓝
        status, _, _ = self._req(
            "/push",
            method="POST",
            body=raw_frame,
            headers={"Content-Type": "application/octet-stream"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(self.fb.last_bytes[:2], b"\x1f\x00")

        # 推送绿色 deflate 压缩 RGB565 帧，验证极速解压直写显存与按需生成 /preview.png
        green_raw = b"\xe0\x07" * (320 * 170)
        compressed_green = zlib.compress(green_raw, level=1)
        status, _, z_resp = self._req(
            "/push",
            method="POST",
            body=compressed_green,
            headers={"Content-Type": "application/octet-stream", "Content-Encoding": "deflate"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(self.fb.last_bytes[:2], b"\xe0\x07")
        self.assertTrue(json.loads(z_resp.decode("utf-8"))["ok"])

        status, _, lazy_png = self._req("/preview.png")
        self.assertEqual(status, 200)
        self.assertEqual(Image.open(io.BytesIO(lazy_png)).getpixel((0, 0)), (0, 255, 0))

        # 验证原始帧模式下修改配置仍能惰性重建源图像并翻转显存像素
        status, _, _ = self._req(
            "/api/config",
            method="POST",
            body=json.dumps({**self.runtime.get_config(), "INVERT": True, "save": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        self.assertNotEqual(self.fb.last_bytes[:2], b"\xe0\x07")
        self._req(
            "/api/config",
            method="POST",
            body=json.dumps({**self.runtime.get_config(), "INVERT": False, "save": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        # 4. 切换内置 App UI 样张并修改配置自动重刷显存
        status, _, pat_raw = self._req(
            "/api/test-pattern",
            method="POST",
            body=json.dumps({"pattern": "ui_dashboard"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        pat_res = json.loads(pat_raw.decode("utf-8"))
        self.assertEqual(pat_res["active_pattern"], "ui_dashboard")
        before_invert = self.fb.last_bytes

        status, _, _ = self._req(
            "/api/config",
            method="POST",
            body=json.dumps({**self.runtime.get_config(), "INVERT": True, "save": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        self.assertNotEqual(before_invert, self.fb.last_bytes)

        # 5. 测试中英文切换控制指令（样张态与待机态均实时刷新显存）
        fb_zh_pat = self.fb.last_bytes
        status, _, lang_raw = self._req(
            "/api/control",
            method="POST",
            body=json.dumps({"action": "toggle_lang"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(lang_raw.decode("utf-8"))["config"]["UI_LANG"], "en")
        self.assertNotEqual(fb_zh_pat, self.fb.last_bytes)

        # 6. 返回待机等待页并验证英文待机页与切回中文待机页不同
        status, _, ctrl_raw = self._req(
            "/api/control",
            method="POST",
            body=json.dumps({"action": "waiting"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(ctrl_raw.decode("utf-8"))["mode"], "waiting")
        fb_en_wait = self.fb.last_bytes

        status, _, lang_back_raw = self._req(
            "/api/control",
            method="POST",
            body=json.dumps({"action": "toggle_lang"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(lang_back_raw.decode("utf-8"))["config"]["UI_LANG"], "zh")
        self.assertNotEqual(fb_en_wait, self.fb.last_bytes)

    def test_target_fps_fixed_pacing_and_unlimited_mode(self) -> None:
        raw_frame = zlib.compress(b"\x1f\x00" * (320 * 170), level=1)

        # 设定固定 10 FPS（帧间隔 100ms），连续发送 4 帧总跨度应 >= 0.27s（3 个间隔）
        self._req(
            "/api/config",
            method="POST",
            body=json.dumps({**self.runtime.get_config(), "TARGET_FPS": 10, "save": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        t0 = time.perf_counter()
        for _ in range(4):
            status, _, _ = self._req(
                "/push",
                method="POST",
                body=raw_frame,
                headers={"Content-Type": "application/octet-stream", "Content-Encoding": "deflate"},
            )
            self.assertEqual(status, 200)
        paced_elapsed = time.perf_counter() - t0
        self.assertGreaterEqual(paced_elapsed, 0.26)

        # 切回 TARGET_FPS=0（不控制 FPS），连续发送 8 帧应极速完成
        self._req(
            "/api/config",
            method="POST",
            body=json.dumps({**self.runtime.get_config(), "TARGET_FPS": 0, "save": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        t1 = time.perf_counter()
        for _ in range(8):
            status, _, _ = self._req(
                "/push",
                method="POST",
                body=raw_frame,
                headers={"Content-Type": "application/octet-stream", "Content-Encoding": "deflate"},
            )
            self.assertEqual(status, 200)
        unlimited_elapsed = time.perf_counter() - t1
        self.assertLess(unlimited_elapsed, 0.22)

    def test_auth_token_and_bad_payload_errors(self) -> None:
        # 启用鉴权 Token
        self._req(
            "/api/config",
            method="POST",
            body=json.dumps({**self.runtime.get_config(), "CAST_TOKEN": "secret123"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        # 未携带 Token 推图应返回 401
        with self.assertRaises(HTTPError) as ctx:
            self._req("/push", method="POST", body=b"not-an-image", headers={"Content-Type": "image/png"})
        self.assertEqual(ctx.exception.code, 401)

        # 携带正确 Token 但图像数据损坏应返回 400
        with self.assertRaises(HTTPError) as ctx2:
            self._req(
                "/push",
                method="POST",
                body=b"corrupted-image-bytes",
                headers={"Content-Type": "image/png", "X-Cast-Token": "secret123"},
            )
        self.assertEqual(ctx2.exception.code, 400)

        # 损坏的 deflate 压缩流同样应被安全捕获并返回 400
        with self.assertRaises(HTTPError) as ctx3:
            self._req(
                "/push",
                method="POST",
                body=b"not-valid-zlib-stream",
                headers={
                    "Content-Type": "application/octet-stream",
                    "Content-Encoding": "deflate",
                    "X-Cast-Token": "secret123",
                },
            )
        self.assertEqual(ctx3.exception.code, 400)

    def _build_minimal_avi(self, frames: list[bytes], pcm_chunks: list[bytes], rate: int = 24000, channels: int = 1) -> bytes:
        """构建带 WAVEFORMATEX 音频头与 movi 交错块的测试用 RIFF/AVI 字节流。"""
        wave_fmt = struct.pack(
            "<HHIIHH",
            1,
            channels,
            rate,
            rate * channels * 2,
            channels * 2,
            16,
        )
        strh_auds = b"strh" + struct.pack("<I", 56) + b"auds" + (b"\x00" * 52)
        strf_auds = b"strf" + struct.pack("<I", len(wave_fmt)) + wave_fmt
        hdrl_body = b"hdrl" + strh_auds + strf_auds
        hdrl_list = b"LIST" + struct.pack("<I", len(hdrl_body)) + hdrl_body

        movi_parts = bytearray(b"movi")
        max_len = max(len(frames), len(pcm_chunks))
        for i in range(max_len):
            if i < len(frames):
                vf = frames[i]
                movi_parts.extend(b"00dc" + struct.pack("<I", len(vf)) + vf)
                if len(vf) & 1:
                    movi_parts.append(0)
            if i < len(pcm_chunks):
                af = pcm_chunks[i]
                movi_parts.extend(b"01wb" + struct.pack("<I", len(af)) + af)
                if len(af) & 1:
                    movi_parts.append(0)
        movi_list = b"LIST" + struct.pack("<I", len(movi_parts)) + bytes(movi_parts)
        riff_body = b"AVI " + hdrl_list + movi_list
        return b"RIFF" + struct.pack("<I", len(riff_body)) + riff_body

    def _send_chunked_post(self, path: str, payload: bytes, step: int = 4096) -> tuple[int, dict]:
        """使用原始 TCP 套接字模拟 ffmpeg 的 HTTP/1.1 Transfer-Encoding: chunked 流式推送。"""
        with socket.create_connection(("127.0.0.1", self.port), timeout=8) as sock:
            head = (
                f"POST {path} HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{self.port}\r\n"
                f"Content-Type: application/octet-stream\r\n"
                f"Transfer-Encoding: chunked\r\n"
                f"Connection: close\r\n\r\n"
            ).encode("ascii")
            sock.sendall(head)
            for off in range(0, len(payload), step):
                part = payload[off : off + step]
                sock.sendall(f"{len(part):X}\r\n".encode("ascii") + part + b"\r\n")
            sock.sendall(b"0\r\n\r\n")
            resp = bytearray()
            while True:
                buf = sock.recv(8192)
                if not buf:
                    break
                resp.extend(buf)
        raw_resp = bytes(resp)
        header_blob, body_blob = raw_resp.split(b"\r\n\r\n", 1)
        status_code = int(header_blob.splitlines()[0].split()[1])
        return status_code, json.loads(body_blob.decode("utf-8"))

    def test_audio_sink_volume_mute_and_bounded_drop(self) -> None:
        raw_pcm = struct.pack("<4h", 10000, -10000, 25000, -25000)
        self.assertEqual(app_mod.scale_pcm_s16le(raw_pcm, 100, False), raw_pcm)
        self.assertEqual(app_mod.scale_pcm_s16le(raw_pcm, 100, True), b"\x00" * len(raw_pcm))

        half = struct.unpack("<4h", app_mod.scale_pcm_s16le(raw_pcm, 50, False))
        self.assertEqual(half, (5000, -5000, 12500, -12500))

        boosted = struct.unpack("<4h", app_mod.scale_pcm_s16le(raw_pcm, 150, False))
        self.assertEqual(boosted[2], 32767)
        self.assertEqual(boosted[3], -32768)

        # 验证有界防堆积队列在积压超出上限时自动丢弃旧音频块且不阻塞写入线程
        sink = app_mod.AudioOutputSink(force_memory=True, max_buffer_ms=40, consume_realtime=True)
        try:
            burst = b"\x10\x00" * 24000  # 1 秒 24kHz 单声道数据，远超 40ms 缓冲上限
            sink.write_pcm(burst, sample_rate=24000, channels=1)
            st = sink.get_stats()
            self.assertGreater(st["dropped_bytes"], 0)
        finally:
            sink.close()

    def test_chunked_avi_stream_and_bgr565_swap(self) -> None:
        red_rgb565 = b"\x00\xf8" * (320 * 170)
        green_rgb565 = b"\xe0\x07" * (320 * 170)
        pcm1 = struct.pack("<240h", *([4000, -4000] * 120))
        pcm2 = struct.pack("<240h", *([6000, -6000] * 120))
        avi_bytes = self._build_minimal_avi([red_rgb565, green_rgb565], [pcm1, pcm2], rate=24000, channels=1)

        # 以非对齐块大小 (3331 字节) 分片发送 chunked AVI 流，校验跨分片解析鲁棒性（pace=0 验证全帧不丢）
        status, data = self._send_chunked_post("/stream?pace=0", avi_bytes, step=3331)
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["video_frames"], 2)
        self.assertEqual(data["audio_bytes"], len(pcm1) + len(pcm2))
        self.assertEqual(self.fb.last_bytes[:2], b"\xe0\x07")

        # 验证未加 -re 的全速突发灌入（单次瞬发 45 帧 = 4.9MB）触发非阻塞丢帧保护，不卡死且并发 /health 秒回
        burst_avi = self._build_minimal_avi([red_rgb565] * 45, [pcm1] * 45, rate=24000, channels=1)
        health_latencies: list[float] = []

        def _poll_health() -> None:
            for _ in range(5):
                t_h = time.perf_counter()
                st, _, _ = self._req("/health")
                if st == 200:
                    health_latencies.append(time.perf_counter() - t_h)
                time.sleep(0.01)

        poller = threading.Thread(target=_poll_health, daemon=True)
        poller.start()
        t_burst0 = time.perf_counter()
        st_b, res_b = self._send_chunked_post("/stream", burst_avi, step=65536)
        burst_sec = time.perf_counter() - t_burst0
        poller.join(timeout=2.0)

        self.assertEqual(st_b, 200)
        self.assertLess(burst_sec, 1.5)
        self.assertGreater(res_b["dropped_frames"], 20)
        self.assertTrue(health_latencies and max(health_latencies) < 0.25)

        # 验证音频子进程启动即退出的异常场景：最多尝试 2 次便自动熔断降级至 memory，绝不引发 fork 风暴
        failing_sink = app_mod.AudioOutputSink(
            candidate_override=[("aplay", sys.executable), ("memory", "")],
        )
        # 覆写命令使子进程立即以非零码退出，模拟无声卡或 root 无 PipeWire 套接字错误
        failing_sink._build_player_cmd = lambda r, c: [sys.executable, "-c", "import sys; sys.exit(1)"]  # type: ignore[method-assign]
        try:
            for _ in range(25):
                failing_sink.write_pcm(pcm1, sample_rate=24000, channels=1)
                time.sleep(0.015)
            time.sleep(0.45)
            f_stats = failing_sink.get_stats()
            self.assertEqual(f_stats["backend"], "memory")
            self.assertLessEqual(f_stats["spawn_count"], 3)
        finally:
            failing_sink.close()

        # 验证 bgr565le 参数自动红蓝互换（0x001F 在 bgr565le 中表示纯红 -> 显存应写入 0xF800 = b"\x00\xf8"）
        bgr_red = b"\x1f\x00" * (320 * 170)
        avi_bgr = self._build_minimal_avi([bgr_red], [], rate=24000, channels=1)
        status2, data2 = self._send_chunked_post("/stream?pix_fmt=bgr565le", avi_bgr, step=8192)
        self.assertEqual(status2, 200)
        self.assertEqual(data2["video_frames"], 1)
        self.assertEqual(self.fb.last_bytes[:2], b"\x00\xf8")

        # 验证视频流 (/stream) 与原始帧 (/push) 实时响应控台的 ROTATE 旋转选项
        # 构造左上角 (0,0) 为纯红 (0xF800 = b"\x00\xf8")、其余全黑的原始帧
        corner_frame = b"\x00\xf8" + (b"\x00\x00" * (320 * 170 - 1))
        self._req(
            "/api/config",
            method="POST",
            body=json.dumps({**self.runtime.get_config(), "ROTATE": 180, "save": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        st_rot, _ = self._send_chunked_post(
            "/stream?pace=0",
            self._build_minimal_avi([corner_frame], [], rate=24000, channels=1),
            step=16384,
        )
        self.assertEqual(st_rot, 200)
        # 旋转 180° 后，左上角 (0,0) 应变为黑色，右下角最后一个像素 (319,169) 应变为纯红 0xF800
        self.assertEqual(self.fb.last_bytes[:2], b"\x00\x00")
        self.assertEqual(self.fb.last_bytes[-2:], b"\x00\xf8")

        # 网页端已做源分辨率预旋转时 (?pre_rotated=1)，不应被服务端二次翻转
        self._req(
            "/push?pre_rotated=1",
            method="POST",
            body=corner_frame,
            headers={"Content-Type": "application/octet-stream"},
        )
        self.assertEqual(self.fb.last_bytes[:2], b"\x00\xf8")

        # 恢复 ROTATE=0，并验证切换内置样张会自动递增流纪元中止后台音视频流且清空音频队列
        self._req(
            "/api/config",
            method="POST",
            body=json.dumps({**self.runtime.get_config(), "ROTATE": 0, "save": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        epoch_before = self.runtime._stream_epoch
        self._req(
            "/api/test-pattern",
            method="POST",
            body=json.dumps({"pattern": "cal_color_bars"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        self.assertGreater(self.runtime._stream_epoch, epoch_before)
        self.assertEqual(self.runtime.get_audio_status()["queued_bytes"], 0)

        # 验证 MJPEG AVI 合流 (-c:v mjpeg) 与 CP0S 自适应混合差分协议 (Key + XOR-Delta + JPEG + PCM) + X-Frame-Seq 乱序拦截
        mjpeg_img = Image.new("RGB", (320, 170), (0, 255, 0))
        jbuf = io.BytesIO()
        mjpeg_img.save(jbuf, format="JPEG", quality=85)
        avi_mjpeg = self._build_minimal_avi([jbuf.getvalue()], [pcm1], rate=24000, channels=1)
        st_mj, res_mj = self._send_chunked_post("/stream?pace=0", avi_mjpeg, step=4096)
        self.assertEqual(st_mj, 200)
        self.assertEqual(res_mj["video_frames"], 1)
        restored_mj = app_mod.rgb565_bytes_to_image(self.fb.last_bytes)
        self.assertGreater(restored_mj.getpixel((10, 10))[1], 220)

        # 验证 CP0S 协议流：帧1(关键帧) -> 帧2(微动走 0x02 XOR 差分帧) -> 帧3(突变走 0x03 JPEG) + 0x10 音频
        enc = streamer_mod.HybridCp0sEncoder(jpeg_quality=80, delta_max_bytes=20000)
        f1 = Image.new("RGB", (320, 170), (20, 30, 40))
        f2 = f1.copy()
        f2.putpixel((5, 5), (255, 0, 0))
        t1, p1 = enc.encode_frame(f1)
        t2, p2 = enc.encode_frame(f2)
        self.assertEqual(t1, 0x01)
        self.assertEqual(t2, 0x02)  # 局部微动应命中零 JPEG 负担的 XOR 差分帧

        cp0s_blob = (
            streamer_mod.build_cp0s_header(24000, 1)
            + streamer_mod.pack_cp0s_packet(t1, p1)
            + streamer_mod.pack_cp0s_packet(0x10, pcm1)
            + streamer_mod.pack_cp0s_packet(t2, p2)
            + streamer_mod.pack_cp0s_packet(0xFF, b"")
        )
        st_cp, res_cp = self._send_chunked_post("/stream?pace=0", cp0s_blob, step=2048)
        self.assertEqual(st_cp, 200)
        self.assertEqual(res_cp["protocol"], "cp0s")
        self.assertEqual(res_cp["video_frames"], 2)
        self.assertEqual(res_cp["audio_bytes"], len(pcm1))
        self.assertEqual(app_mod.rgb565_bytes_to_image(self.fb.last_bytes).getpixel((5, 5)), (255, 0, 0))

        # 验证并发流水线乱序旧帧过滤 (X-Frame-Seq: 先到 seq=10 后到 seq=9 时，seq=9 应被直接丢弃不覆盖画面)
        blue_im = Image.new("RGB", (320, 170), (0, 0, 255))
        b_buf = io.BytesIO()
        blue_im.save(b_buf, format="JPEG", quality=85)
        self._req(
            "/push?pre_processed=1&fast=1",
            method="POST",
            body=b_buf.getvalue(),
            headers={"Content-Type": "image/jpeg", "X-Stream-Session": "s1", "X-Frame-Seq": "10"},
        )
        st_stale, _, stale_raw = self._req(
            "/push?pre_processed=1&fast=1",
            method="POST",
            body=jbuf.getvalue(),
            headers={"Content-Type": "image/jpeg", "X-Stream-Session": "s1", "X-Frame-Seq": "9"},
        )
        self.assertEqual(st_stale, 200)
        self.assertTrue(json.loads(stale_raw.decode("utf-8")).get("stale_seq"))
        # 屏幕上仍应保持 seq=10 的纯蓝画面，未被迟到的 seq=9 绿色帧覆盖
        self.assertGreater(app_mod.rgb565_bytes_to_image(self.fb.last_bytes).getpixel((10, 10))[2], 220)

    def test_post_audio_api_audio_and_curl_play_wav_mp4(self) -> None:
        # 1. 测试 /api/audio 音量与静音控制
        status, _, resp_raw = self._req(
            "/api/audio",
            method="POST",
            body=json.dumps({"volume": 80, "muted": False, "save": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        a_cfg = json.loads(resp_raw.decode("utf-8"))
        self.assertEqual(a_cfg["audio"]["volume"], 80)
        self.assertFalse(a_cfg["audio"]["muted"])

        # 2. 测试 POST /audio 推送原始 PCM 采样块
        pcm_chunk = struct.pack("<480h", *([3000, -3000] * 240))
        status, _, a_resp = self._req(
            "/audio?rate=24000&channels=1",
            method="POST",
            body=pcm_chunk,
            headers={"Content-Type": "application/octet-stream"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(a_resp.decode("utf-8"))["audio_bytes"], len(pcm_chunk))

        # 3. 测试 curl 直推标准 .wav 文件到 POST /play?realtime=0
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(pcm_chunk * 3)
        status, _, wav_resp = self._req(
            "/play?realtime=0",
            method="POST",
            body=wav_buf.getvalue(),
            headers={"Content-Type": "audio/wav"},
        )
        self.assertEqual(status, 200)
        wav_json = json.loads(wav_resp.decode("utf-8"))
        self.assertTrue(wav_json["ok"])
        self.assertEqual(wav_json["audio_bytes"], len(pcm_chunk) * 3)

        # 4. 若当前环境具备 ffmpeg，验证 curl 直推 .mp4 原片到 POST /play?realtime=0 自动音画同解
        if shutil.which("ffmpeg"):
            with tempfile.TemporaryDirectory() as tmp_m:
                mp4_path = Path(tmp_m) / "mini.mp4"
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-v", "error",
                        "-f", "lavfi", "-i", "color=c=blue:s=320x170:r=10",
                        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=24000",
                        "-t", "0.3",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac",
                        str(mp4_path),
                    ],
                    check=True,
                )
                status, _, mp4_resp = self._req(
                    "/play?realtime=0",
                    method="POST",
                    body=mp4_path.read_bytes(),
                    headers={"Content-Type": "video/mp4"},
                )
                self.assertEqual(status, 200)
                mp4_json = json.loads(mp4_resp.decode("utf-8"))
                self.assertGreaterEqual(mp4_json["video_frames"], 2)
                self.assertGreater(mp4_json["audio_bytes"], 0)

                # 5. 验证真实命令行 ffmpeg -re -c:v mjpeg -f avi 推送至 HTTP /stream 音画完整上屏且不误丢帧
                before_blit = self.runtime.get_health_snapshot()["stats"]["blitted_frames"]
                subprocess.run(
                    [
                        "ffmpeg", "-v", "error", "-re",
                        "-i", str(mp4_path),
                        "-vf", "fps=10,scale=320:170",
                        "-c:v", "mjpeg", "-q:v", "7",
                        "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le",
                        "-f", "avi", f"{self.base_url}/stream",
                    ],
                    check=True,
                )
                time.sleep(0.12)
                after_mjpeg_blit = self.runtime.get_health_snapshot()["stats"]["blitted_frames"]
                self.assertGreaterEqual(after_mjpeg_blit - before_blit, 2)

                # 6. 验证 pc_av_streamer.py CLI 端到端推送 CP0S 自适应混合流（含竖屏 120x240 视频自动 90° 横向旋转）
                rc_cp0s = streamer_mod.main(
                    [str(mp4_path), "--host", "127.0.0.1", "--port", str(self.port), "--fps", "10", "--no-realtime"]
                )
                self.assertEqual(rc_cp0s, 0)

                # 生成左半红、右半蓝的竖屏视频 (120x240)：在默认 ROTATE=auto 下自动顺时针转 90° 后，上半屏应变为红色、下半屏变为蓝色
                vert_mp4 = Path(tmp_m) / "portrait.mp4"
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-v", "error",
                        "-f", "lavfi", "-i", "color=c=red:s=60x240:r=10",
                        "-f", "lavfi", "-i", "color=c=blue:s=60x240:r=10",
                        "-filter_complex", "[0:v][1:v]hstack=inputs=2[v]",
                        "-map", "[v]", "-t", "0.2",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        str(vert_mp4),
                    ],
                    check=True,
                )
                self._req(
                    "/api/config",
                    method="POST",
                    body=json.dumps({**self.runtime.get_config(), "ROTATE": "auto", "FIT_MODE": "stretch", "save": False}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                st_vp, _, _ = self._req(
                    "/play?realtime=0",
                    method="POST",
                    body=vert_mp4.read_bytes(),
                    headers={"Content-Type": "video/mp4"},
                )
                self.assertEqual(st_vp, 200)
                vp_img = app_mod.rgb565_bytes_to_image(self.fb.last_bytes)
                # 顺时针旋转 90° 后，原左侧红色位于顶部 (160, 20)，原右侧蓝色位于底部 (160, 150)
                self.assertGreater(vp_img.getpixel((160, 20))[0], 180)
                self.assertGreater(vp_img.getpixel((160, 150))[2], 180)
                after_cp0s_blit = self.runtime.get_health_snapshot()["stats"]["blitted_frames"]
                self.assertGreaterEqual(after_cp0s_blit - after_mjpeg_blit, 2)

    def test_diag_rolling_logger_and_logs_api(self) -> None:
        # 1. 验证定容自动轮转：单文件上限 4096B 时，连续写入 200 行总大小严格不超过 2 * 4096B
        with tempfile.TemporaryDirectory() as tmp_l:
            rot_path = Path(tmp_l) / "test_diag.log"
            logger = app_mod.DiagRollingLogger(rot_path, max_bytes=4096)
            for i in range(200):
                logger.append_line(f"line-{i:04d}-" + ("x" * 60))
            self.assertLessEqual(logger.size_bytes(), 8192)
            self.assertTrue(logger.backup_path.is_file())
            tail = logger.read_tail(5)
            self.assertEqual(len(tail), 5)
            self.assertTrue(tail[-1].startswith("line-0199-"))

        # 2. 验证通过 /api/logs 开启运行时按秒诊断日志 -> 推送帧产生性能汇总行 -> 纯文本拉取 -> 清空日志
        st_on, _, on_raw = self._req(
            "/api/logs",
            method="POST",
            body=json.dumps({"enabled": True, "save": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(st_on, 200)
        self.assertTrue(json.loads(on_raw.decode("utf-8"))["enabled"])

        time.sleep(1.15)
        raw_frame = zlib.compress(b"\x00\xf8" * (320 * 170), level=1)
        self._req(
            "/push?fast=1",
            method="POST",
            body=raw_frame,
            headers={"Content-Type": "application/octet-stream", "Content-Encoding": "deflate"},
        )
        time.sleep(1.15)

        st_txt, ctype_txt, txt_raw = self._req("/api/logs?tail=20&format=text")
        self.assertEqual(st_txt, 200)
        self.assertIn("text/plain", ctype_txt)
        txt_str = txt_raw.decode("utf-8")
        self.assertIn("[INIT] diag_log=ON", txt_str)
        self.assertIn("proc_avg=", txt_str)

        st_clr, _, clr_raw = self._req(
            "/api/logs",
            method="POST",
            body=json.dumps({"action": "clear", "enabled": False, "save": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(st_clr, 200)
        clr_json = json.loads(clr_raw.decode("utf-8"))
        self.assertEqual(clr_json["size_bytes"], 0)
        self.assertFalse(clr_json["enabled"])

        # 3. 验证右上角缓存角标行级直贴快路 + 客户端 Ctrl+C 半截断开 chunked /stream 不报 400 + 空闲连接无 path 不抛 AttributeError
        self._req(
            "/api/config",
            method="POST",
            body=json.dumps({**self.runtime.get_config(), "SHOW_OVERLAY": True, "save": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        black_raw = b"\x00\x00" * (320 * 170)
        self._req("/push?fast=1", method="POST", body=black_raw, headers={"Content-Type": "application/octet-stream"})
        self.assertNotEqual(self.fb.last_bytes, black_raw)  # 右上角已叠加缓存角标贴片

        # 模拟 ffmpeg 发送完 1 帧后在下一个 chunk 半截被 Ctrl+C 中断（声明 0x4000 字节但仅发 100 字节即关闭）
        avi_1f = self._build_minimal_avi([black_raw], [], rate=24000, channels=1)
        with socket.create_connection(("127.0.0.1", self.port), timeout=5) as sock:
            sock.sendall(
                (
                    f"POST /stream?pace=0 HTTP/1.1\r\n"
                    f"Host: 127.0.0.1:{self.port}\r\n"
                    f"Transfer-Encoding: chunked\r\n\r\n"
                ).encode("ascii")
            )
            sock.sendall(f"{len(avi_1f):X}\r\n".encode("ascii") + avi_1f + b"\r\n")
            sock.sendall(b"4000\r\n" + (b"\x00" * 100))
            sock.shutdown(socket.SHUT_WR)
            resp_aborted = sock.recv(4096)
        self.assertIn(b"200 OK", resp_aborted)

        # 验证 handler 尚未解析出 self.path 时调用 log_message 不抛 AttributeError
        dummy_handler = object.__new__(app_mod.ScreenCastHttpHandler)
        dummy_handler.log_message("Request timed out: %r", TimeoutError("timed out"))


class TestDebPackageBuilder(unittest.TestCase):
    """验证纯 Python 构建的 arm64 .deb 包符合 Debian 与 APPLaunch 结构规范。"""

    def test_build_deb_creates_valid_ar_and_data_tar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            deb_path = build_deb.build_deb_package(output_dir=Path(tmp))
            self.assertTrue(deb_path.is_file())
            raw = deb_path.read_bytes()
            self.assertTrue(raw.startswith(b"!<arch>\n"))
            members = build_deb.parse_ar_members(raw)
            self.assertIn("debian-binary", members)
            self.assertIn("control.tar.gz", members)
            self.assertIn("data.tar.gz", members)

            with tarfile.open(fileobj=io.BytesIO(members["data.tar.gz"]), mode="r:gz") as tf:
                names = {m.name.lstrip("./") for m in tf.getmembers()}
                self.assertIn("usr/bin/cp0-screen-cast", names)
                self.assertIn("usr/share/APPLaunch/applications/cp0-screen-cast.desktop", names)
                self.assertIn("usr/share/APPLaunch/share/images/cp0-screen-cast.png", names)
                self.assertIn("usr/share/APPLaunch/share/images/cp0-screen-cast_100.png", names)
                self.assertIn("usr/share/APPLaunch/share/images/cp0-screen-cast_80.png", names)
                self.assertIn("usr/share/cp0-screen-cast/cp0_cast_app.py", names)
                bin_info = next(m for m in tf.getmembers() if m.name.lstrip("./") == "usr/bin/cp0-screen-cast")
                self.assertEqual(bin_info.mode & 0o111, 0o111)

                # 校验图标尺寸严格符合 APPLaunch 100x100 与 80x80 RGBA 规范且四角透明
                im_100 = Image.open(tf.extractfile("./usr/share/APPLaunch/share/images/cp0-screen-cast.png"))
                im_80 = Image.open(tf.extractfile("./usr/share/APPLaunch/share/images/cp0-screen-cast_80.png"))
                self.assertEqual(im_100.size, (100, 100))
                self.assertEqual(im_80.size, (80, 80))
                self.assertEqual(im_100.mode, "RGBA")
                self.assertEqual(im_100.getpixel((0, 0))[3], 0)

                desktop_txt = tf.extractfile("./usr/share/APPLaunch/applications/cp0-screen-cast.desktop").read().decode("utf-8")
                self.assertIn("Sysplause=true", desktop_txt)
                self.assertIn("Icon=share/images/cp0-screen-cast.png", desktop_txt)


if __name__ == "__main__":
    unittest.main()
