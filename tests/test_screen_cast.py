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
import struct
import sys
import tarfile
import tempfile
import threading
import time
import unittest
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
        self.runtime = app_mod.ScreenCastRuntime(
            env_path=self.env_path,
            web_dir=APP_DIR / "web",
            framebuffer=self.fb,
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
