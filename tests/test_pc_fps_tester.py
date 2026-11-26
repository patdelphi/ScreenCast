#!/usr/bin/env python3
"""
程序说明：CardputerZero PC 端多速率连续推流测速工具（pc_fps_tester.py）自动化测试套件。

测试覆盖：
1. 320×170 速率数字与双轨运动指示器画面渲染，验证连续帧像素必然变化；
2. JPEG (4:4:4)、PNG 与原始小端 RGB565 三种推流载荷编码有效性；
3. HTTP/1.1 Keep-Alive 连续推流引擎对接本地 ScreenCast 服务端的多档位测速与异常恢复。
"""

from __future__ import annotations

import io
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from PIL import Image

APP_DIR = Path(__file__).resolve().parent.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import cp0_cast_app as cast_app  # noqa: E402
import pc_fps_tester as fps_mod  # noqa: E402


class TestPcFpsFrameAndEncoder(unittest.TestCase):
    """验证测速画面绘制、动态帧差异与三种推流编码格式。"""

    def test_render_fps_frame_dimensions_and_motion_diff(self) -> None:
        f1 = fps_mod.render_fps_frame(
            target_fps=30.0,
            actual_fps=24.5,
            frame_seq=1,
            elapsed_sec=0.10,
            rtt_ms=39.2,
            kbps=260.4,
            fmt="jpeg",
        )
        f2 = fps_mod.render_fps_frame(
            target_fps=30.0,
            actual_fps=24.5,
            frame_seq=2,
            elapsed_sec=0.14,
            rtt_ms=39.2,
            kbps=260.4,
            fmt="jpeg",
        )
        self.assertEqual(f1.size, (320, 170))
        self.assertEqual(f1.mode, "RGB")
        # 连续两帧的旋转指针、滑块与 16 格频闪条必须产生可见像素变化
        self.assertNotEqual(f1.tobytes(), f2.tobytes())

        f1_en = fps_mod.render_fps_frame(
            target_fps=30.0,
            actual_fps=24.5,
            frame_seq=1,
            elapsed_sec=0.10,
            rtt_ms=39.2,
            kbps=260.4,
            fmt="jpeg",
            lang="en",
        )
        self.assertEqual(f1_en.size, (320, 170))
        self.assertNotEqual(f1.tobytes(), f1_en.tobytes())

    def test_encode_jpeg_png_and_rgb565_payloads(self) -> None:
        img = fps_mod.render_fps_frame(
            target_fps=0.0,
            actual_fps=28.0,
            frame_seq=7,
            elapsed_sec=1.25,
            rtt_ms=34.0,
            kbps=310.0,
            fmt="jpeg",
        )
        jpg_bytes, jpg_ct = fps_mod.encode_frame_payload(img, "jpeg")
        self.assertEqual(jpg_ct, "image/jpeg")
        self.assertTrue(jpg_bytes.startswith(b"\xff\xd8\xff"))
        self.assertEqual(Image.open(io.BytesIO(jpg_bytes)).size, (320, 170))

        png_bytes, png_ct = fps_mod.encode_frame_payload(img, "png")
        self.assertEqual(png_ct, "image/png")
        self.assertTrue(png_bytes.startswith(b"\x89PNG"))

        raw_bytes, raw_ct = fps_mod.encode_frame_payload(img, "rgb565")
        self.assertEqual(raw_ct, "application/octet-stream")
        self.assertEqual(len(raw_bytes), 320 * 170 * 2)

        zraw_bytes, zraw_ct, zraw_enc = fps_mod.encode_frame_packet(img, "rgb565_zlib")
        self.assertEqual(zraw_ct, "application/octet-stream")
        self.assertEqual(zraw_enc, "deflate")
        self.assertLess(len(zraw_bytes), 320 * 170 * 2)


class TestKeepAliveContinuousPusher(unittest.TestCase):
    """验证 HTTP/1.1 长连接连续推流测速与断连容错。"""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.fb = cast_app.MemoryFramebuffer(320, 170)
        self.runtime = cast_app.ScreenCastRuntime(
            env_path=Path(self.tmp_dir.name) / ".env",
            web_dir=APP_DIR / "web",
            framebuffer=self.fb,
        )
        self.server = cast_app.create_http_server("127.0.0.1", 0, self.runtime)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.runtime.close()
        self.tmp_dir.cleanup()

    def test_run_tier_benchmark_and_error_handling(self) -> None:
        res_20 = fps_mod.run_single_tier(
            host="127.0.0.1",
            port=self.port,
            target_fps=20.0,
            duration_sec=0.6,
            fmt="jpeg",
        )
        self.assertGreaterEqual(res_20["sent_frames"], 6)
        self.assertEqual(res_20["errors"], 0)
        self.assertGreater(res_20["actual_fps"], 8.0)

        res_max = fps_mod.run_single_tier(
            host="127.0.0.1",
            port=self.port,
            target_fps=0.0,
            duration_sec=0.45,
            fmt="rgb565_zlib",
            pipeline_depth=4,
        )
        self.assertGreaterEqual(res_max["sent_frames"], 10)
        self.assertEqual(res_max["errors"], 0)
        self.assertGreater(self.fb.write_count, 15)

        # 验证目标不可达时捕获异常而不崩溃
        bad_res = fps_mod.run_single_tier(
            host="127.0.0.1",
            port=1,
            target_fps=10.0,
            duration_sec=0.25,
            fmt="jpeg",
        )
        self.assertEqual(bad_res["sent_frames"], 0)
        self.assertGreaterEqual(bad_res["errors"], 1)


if __name__ == "__main__":
    unittest.main()
