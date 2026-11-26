#!/usr/bin/env python3
"""
程序说明：为 CardputerZero 无线投屏与画面测试应用生成多尺寸超采样启动器图标并构建 arm64 .deb 安装包。

实机 APPLaunch 规范对齐（基于 192.168.31.251 实机核查）：
1. 图标尺寸与命名：APPLaunch 轮播主卡使用 100×100 RGBA PNG，左右副卡支持 _80.png（80×80），
   商店元数据使用 256×256 RGBA PNG。本脚本以 1024×1024 4x 超采样绘制图标，抗锯齿缩放出
   icon_256.png (256×256)、icon.png / _100.png (100×100) 与 _80.png (80×80)，四角全透明。
2. .desktop 规范：安装至 /usr/share/APPLaunch/applications/cp0-screen-cast.desktop，APPLaunch
   通过 inotify 实时监听该目录自动热加载；Exec 使用无特殊字符绝对路径通过 DesktopExecIsSafe 检查；
   启动脚本使用 python3 -I -B 避免向 root 只读目录写入 __pycache__。
"""

from __future__ import annotations

import gzip
import io
import tarfile
from pathlib import Path

from PIL import Image, ImageDraw

PACKAGE_NAME = "cp0-screen-cast"
PACKAGE_VERSION = "0.1.0"
PACKAGE_ARCH = "arm64"
ICON_BASENAME = "cp0-screen-cast"
FIXED_MTIME = 1764060000


def render_master_icon_1024() -> Image.Image:
    """
    以 1024×1024 RGBA 超采样绘制贴合 CardputerZero 掌机形态与无线彩屏投屏主题的图标：
    - 外层：透明四角 + 深海蓝渐变圆角底板与青绿微光内框（对齐原生 APPLaunch 图标圆角比例）
    - 主体：琥珀金/深空灰掌机机身，上半部为 320:170 比例高亮彩条屏幕，下半部为矩阵键盘点阵
    - 顶部视觉焦点：青绿无线投屏电波弧线汇入屏幕中心
    """
    sz = 1024
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))

    # 1. 绘制圆角方标渐变底板（留出透明圆角与边缘呼吸感）
    mask = Image.new("L", (sz, sz), 0)
    mdraw = ImageDraw.Draw(mask)
    pad = 28
    radius = 228
    mdraw.rounded_rectangle((pad, pad, sz - 1 - pad, sz - 1 - pad), radius=radius, fill=255)

    grad = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(grad)
    for y in range(pad, sz - pad):
        t = (y - pad) / max(1, (sz - 2 * pad - 1))
        r = int(14 + 10 * (1.0 - t))
        g = int(28 + 26 * (1.0 - t * 0.6))
        b = int(46 + 38 * (1.0 - t * 0.4))
        gdraw.line((pad, y, sz - 1 - pad, y), fill=(r, g, b, 255))
    img.paste(grad, (0, 0), mask)

    draw = ImageDraw.Draw(img)
    # 双层质感描边
    draw.rounded_rectangle(
        (pad, pad, sz - 1 - pad, sz - 1 - pad),
        radius=radius,
        outline=(56, 189, 248, 220),
        width=18,
    )
    draw.rounded_rectangle(
        (pad + 26, pad + 26, sz - 1 - pad - 26, sz - 1 - pad - 26),
        radius=radius - 24,
        outline=(99, 226, 183, 78),
        width=10,
    )

    # 2. 绘制居中 CardputerZero 掌机机身（y=290..856）
    body_box = (176, 300, 848, 852)
    # 机身底部投影
    draw.rounded_rectangle((186, 320, 858, 872), radius=88, fill=(5, 10, 18, 150))
    # 机身外壳（暖琥珀科技灰金配色，高辨识度）
    draw.rounded_rectangle(body_box, radius=84, fill=(236, 184, 78, 255), outline=(255, 222, 142, 255), width=12)

    # 3. 掌机上半部 16:8.5 宽屏黑框与彩色测试条画面
    bezel_box = (224, 344, 800, 628)
    draw.rounded_rectangle(bezel_box, radius=42, fill=(13, 18, 28, 255), outline=(38, 50, 68, 255), width=8)

    scr_x0, scr_y0, scr_x1, scr_y1 = 252, 370, 772, 602
    bar_colors = (
        (255, 92, 92, 255),    # 红
        (255, 196, 46, 255),   # 黄
        (52, 218, 142, 255),   # 绿
        (46, 204, 255, 255),   # 青
        (96, 142, 255, 255),   # 蓝
        (214, 108, 255, 255),  # 品红
    )
    total_w = scr_x1 - scr_x0
    bw = total_w // len(bar_colors)
    for i, col in enumerate(bar_colors):
        bx0 = scr_x0 + i * bw
        bx1 = scr_x1 if i == len(bar_colors) - 1 else (bx0 + bw - 8)
        draw.rounded_rectangle((bx0, scr_y0, bx1, scr_y1), radius=14, fill=col)

    # 屏幕中央叠加半透明深色投屏徽章与播放/帧同步箭头
    draw.rounded_rectangle((432, 430, 592, 542), radius=28, fill=(12, 18, 30, 218), outline=(255, 255, 255, 235), width=10)
    draw.polygon([(488, 456), (488, 516), (546, 486)], fill=(110, 242, 196, 255))

    # 4. 掌机下半部标志性矩阵键盘点阵（6 列 × 3 行）
    key_cols, key_rows = 6, 3
    kx_start, ky_start = 238, 662
    kw, kh = 72, 40
    kgap_x, kgap_y = 20, 18
    for r_idx in range(key_rows):
        for c_idx in range(key_cols):
            kx = kx_start + c_idx * (kw + kgap_x)
            ky = ky_start + r_idx * (kh + kgap_y)
            # 左上角首键用橙红高亮致敬 M5 键盘 ESC 键
            kcol = (224, 78, 62, 255) if (r_idx == 0 and c_idx == 0) else (24, 42, 54, 255)
            draw.rounded_rectangle((kx, ky, kx + kw, ky + kh), radius=12, fill=kcol)

    # 5. 顶部无线投屏信号电波（亮青绿双弧线 + 发射圆心）
    cx, cy = 512, 278
    for rad, w in ((92, 24), (158, 24)):
        draw.arc(
            (cx - rad, cy - rad, cx + rad, cy + rad),
            start=212,
            end=328,
            fill=(110, 242, 196, 255),
            width=w,
        )
    draw.ellipse((cx - 24, cy - 36, cx + 24, cy + 12), fill=(125, 224, 255, 255))

    return img


def _encode_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def ensure_launcher_icons(assets_dir: Path, regenerate: bool = False) -> dict[str, bytes]:
    """
    生成并保存全套符合 APPLaunch 与商店标准的图标变体：
    - icon_256.png : 256×256 RGBA（商店与高清展示）
    - icon.png     : 100×100 RGBA（APPLaunch 默认主图标，与 _100.png 同尺寸）
    - icon_100.png : 100×100 RGBA（APPLaunch 选中态主卡）
    - icon_80.png  : 80×80 RGBA  （APPLaunch 侧边副卡）
    """
    assets_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "256": assets_dir / "icon_256.png",
        "base": assets_dir / "icon.png",
        "100": assets_dir / "icon_100.png",
        "80": assets_dir / "icon_80.png",
    }
    if not regenerate and all(p.is_file() for p in paths.values()):
        return {k: p.read_bytes() for k, p in paths.items()}

    master = render_master_icon_1024()
    im_256 = master.resize((256, 256), Image.Resampling.LANCZOS)
    im_100 = master.resize((100, 100), Image.Resampling.LANCZOS)
    im_80 = master.resize((80, 80), Image.Resampling.LANCZOS)

    data = {
        "256": _encode_png(im_256),
        "base": _encode_png(im_100),
        "100": _encode_png(im_100),
        "80": _encode_png(im_80),
    }
    for k, raw in data.items():
        paths[k].write_bytes(raw)
    return data


def _add_tar_entry(
    tf: tarfile.TarFile,
    arcname: str,
    data: bytes | None = None,
    mode: int = 0o644,
    is_dir: bool = False,
) -> None:
    info = tarfile.TarInfo(name=arcname)
    info.mtime = FIXED_MTIME
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    if is_dir:
        info.type = tarfile.DIRTYPE
        info.mode = mode
        info.size = 0
        tf.addfile(info)
    else:
        payload = data or b""
        info.type = tarfile.REGTYPE
        info.mode = mode
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))


def _to_gzip_tar(entries: list[tuple[str, bytes | None, int, bool]]) -> bytes:
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w", format=tarfile.GNU_FORMAT) as tf:
        for arcname, data, mode, is_dir in entries:
            _add_tar_entry(tf, arcname, data=data, mode=mode, is_dir=is_dir)
    gz_buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=gz_buf, compresslevel=9, mtime=FIXED_MTIME) as gz:
        gz.write(tar_buf.getvalue())
    return gz_buf.getvalue()


def _pack_ar_archive(members: list[tuple[str, bytes]]) -> bytes:
    out = bytearray(b"!<arch>\n")
    for name, content in members:
        header = (
            f"{name:<16}"
            f"{FIXED_MTIME:<12}"
            f"{'0':<6}"
            f"{'0':<6}"
            f"{'100644':<8}"
            f"{len(content):<10}"
            "`\n"
        ).encode("ascii")
        if len(header) != 60:
            raise ValueError(f"ar 头长度异常: {len(header)}")
        out.extend(header)
        out.extend(content)
        if len(content) % 2 == 1:
            out.extend(b"\n")
    return bytes(out)


def parse_ar_members(raw: bytes) -> dict[str, bytes]:
    """解析 ar 归档各成员字节，供单元测试校验 .deb 包完整性。"""
    if not raw.startswith(b"!<arch>\n"):
        raise ValueError("不是有效的 ar 归档")
    pos = 8
    result: dict[str, bytes] = {}
    while pos + 60 <= len(raw):
        hdr = raw[pos : pos + 60]
        name = hdr[0:16].decode("ascii").strip().rstrip("/")
        size = int(hdr[48:58].decode("ascii").strip())
        pos += 60
        result[name] = raw[pos : pos + size]
        pos += size + (size % 2)
    return result


def _lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def build_deb_package(output_dir: Path | None = None, regenerate_icons: bool = False) -> Path:
    """构建符合实机 APPLaunch 规范的 cp0-screen-cast_<version>_arm64.deb。"""
    app_dir = Path(__file__).resolve().parent
    out_dir = output_dir if output_dir is not None else (app_dir / "dist")
    out_dir.mkdir(parents=True, exist_ok=True)

    icons = ensure_launcher_icons(app_dir / "assets", regenerate=regenerate_icons)
    py_bytes = _lf((app_dir / "cp0_cast_app.py").read_bytes())
    env_bytes = _lf((app_dir / ".env.example").read_bytes())
    html_bytes = _lf((app_dir / "web" / "index.html").read_bytes())
    css_bytes = _lf((app_dir / "web" / "app.css").read_bytes())
    js_bytes = _lf((app_dir / "web" / "app.js").read_bytes())

    # 对齐实机 zerodesk 启动脚本：使用 python3 -I -B 隔离运行，不向 /usr/share 写 .pyc
    launcher_sh = (
        "#!/bin/sh\n"
        "exec /usr/bin/python3 -I -B /usr/share/cp0-screen-cast/cp0_cast_app.py \"$@\"\n"
    ).encode("utf-8")

    # 对齐实机 APPLaunch 解析契约：Name 仅用非本地化键，Exec 无任何 shell 元字符，Sysplause=true 暂停启动器抢占 fb0/键盘
    desktop_entry = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=ScreenCast\n"
        "Comment=Web console and 320x170 RGB565 screen cast tester\n"
        f"Exec=/usr/bin/{PACKAGE_NAME}\n"
        f"Icon=share/images/{ICON_BASENAME}.png\n"
        "Terminal=false\n"
        "Sysplause=true\n"
        "Categories=Utility;System;\n"
        "StartupNotify=false\n"
    ).encode("utf-8")

    systemd_unit = (
        "[Unit]\n"
        "Description=CardputerZero Screen Cast & Display Test Console\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        "User=pi\n"
        "ExecStart=/usr/bin/cp0-screen-cast --env /etc/cp0-screen-cast.conf\n"
        "Restart=on-failure\n"
        "RestartSec=3\n\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    ).encode("utf-8")

    data_entries: list[tuple[str, bytes | None, int, bool]] = [
        ("./etc", None, 0o755, True),
        ("./etc/cp0-screen-cast.conf", env_bytes, 0o644, False),
        ("./usr", None, 0o755, True),
        ("./usr/bin", None, 0o755, True),
        ("./usr/bin/cp0-screen-cast", launcher_sh, 0o755, False),
        ("./usr/lib", None, 0o755, True),
        ("./usr/lib/systemd", None, 0o755, True),
        ("./usr/lib/systemd/system", None, 0o755, True),
        ("./usr/lib/systemd/system/cp0-screen-cast.service", systemd_unit, 0o644, False),
        ("./usr/share", None, 0o755, True),
        ("./usr/share/cp0-screen-cast", None, 0o755, True),
        ("./usr/share/cp0-screen-cast/cp0_cast_app.py", py_bytes, 0o755, False),
        ("./usr/share/cp0-screen-cast/.env.example", env_bytes, 0o644, False),
        ("./usr/share/cp0-screen-cast/assets", None, 0o755, True),
        ("./usr/share/cp0-screen-cast/assets/icon.png", icons["base"], 0o644, False),
        ("./usr/share/cp0-screen-cast/assets/icon_256.png", icons["256"], 0o644, False),
        ("./usr/share/cp0-screen-cast/web", None, 0o755, True),
        ("./usr/share/cp0-screen-cast/web/index.html", html_bytes, 0o644, False),
        ("./usr/share/cp0-screen-cast/web/app.css", css_bytes, 0o644, False),
        ("./usr/share/cp0-screen-cast/web/app.js", js_bytes, 0o644, False),
        ("./usr/share/APPLaunch", None, 0o755, True),
        ("./usr/share/APPLaunch/applications", None, 0o755, True),
        ("./usr/share/APPLaunch/applications/cp0-screen-cast.desktop", desktop_entry, 0o644, False),
        ("./usr/share/APPLaunch/share", None, 0o755, True),
        ("./usr/share/APPLaunch/share/images", None, 0o755, True),
        (f"./usr/share/APPLaunch/share/images/{ICON_BASENAME}.png", icons["base"], 0o644, False),
        (f"./usr/share/APPLaunch/share/images/{ICON_BASENAME}_100.png", icons["100"], 0o644, False),
        (f"./usr/share/APPLaunch/share/images/{ICON_BASENAME}_80.png", icons["80"], 0o644, False),
    ]
    data_tar_gz = _to_gzip_tar(data_entries)

    installed_kb = max(1, sum(len(item[1] or b"") for item in data_entries) // 1024 + 16)
    control_text = (
        f"Package: {PACKAGE_NAME}\n"
        f"Version: {PACKAGE_VERSION}\n"
        f"Section: utils\n"
        f"Priority: optional\n"
        f"Architecture: {PACKAGE_ARCH}\n"
        f"Installed-Size: {installed_kb}\n"
        f"Depends: python3 (>= 3.11), python3-pil\n"
        f"Recommends: python3-evdev, fonts-noto-cjk\n"
        f"Maintainer: patdelphi <patdelphi@outlook.com>\n"
        f"Description: CardputerZero 320x170 Web Console and Screen Cast Tester\n"
        f" Runs on CardputerZero to serve an HTTP web console (:8787) and display\n"
        f" pushed images, raw RGB565 frames, and 10 UI/photo/calibration samples.\n"
    ).encode("utf-8")

    conffiles_text = b"/etc/cp0-screen-cast.conf\n"
    control_tar_gz = _to_gzip_tar(
        [
            ("./", None, 0o755, True),
            ("./control", control_text, 0o644, False),
            ("./conffiles", conffiles_text, 0o644, False),
        ]
    )

    deb_bytes = _pack_ar_archive(
        [
            ("debian-binary", b"2.0\n"),
            ("control.tar.gz", control_tar_gz),
            ("data.tar.gz", data_tar_gz),
        ]
    )

    deb_file = out_dir / f"{PACKAGE_NAME}_{PACKAGE_VERSION}_{PACKAGE_ARCH}.deb"
    deb_file.write_bytes(deb_bytes)
    return deb_file


if __name__ == "__main__":
    built = build_deb_package(regenerate_icons=True)
    print(f"已重新生成多尺寸图标与安装包: {built} ({built.stat().st_size} 字节)")
