# CardputerZero 网页控台与无线投屏测试应用（apps/screen-cast）

## 1. 目标与范围

在 `Y:\Dev\Cardputer\CardputerZero\apps\screen-cast\` 下开发面向 CardputerZero（`320 × 170` 16-bit RGB565 彩屏，Debian 13 `aarch64`）的一体化设备端应用，用于实机测试不同画面、常用 App UI 布局、照片色彩、字号与抖动效果，为后续应用开发提供视觉基准：

- **功能一（IP 网页控台与开放推送接口）**：设备启动后监听局域网 HTTP 端口（默认 `0.0.0.0:8787`），提供双栏网页控台与 REST 接口，支持浏览器上传/拖拽/剪贴板粘贴图片、一键切换 **10 类内置样张**（5 类模拟常用 App UI + 2 类风景/霓虹测试图片 + 3 类屏幕标定卡）、实时调整色彩/缩放/亮度对比度参数，以及接收任意局域网设备通过 `POST /push` 推送的图像。
- **功能二（设备 `320 × 170` 屏幕渲染与交互）**：未投屏时在设备屏幕显示本机 `IPv4:端口`、推送地址、Wi-Fi 与电池状态；收到任意设备推图或样张指令后，将画面转换为小端序 `RGB565`（`108,800` 字节）通过 `mmap` 直写 `/dev/fb0` 显示，并支持机身按键切换上/下一张样张、一键切换色彩模式对比画面、开关信息角标、返回待机页与长按 `ESC` 退出回 `APPLaunch`。
- **暂不纳入范围**：本阶段不修改 `Quote0Local`，不安装 C++ 交叉编译链，仅依赖 Python 标准库与设备已装的 `python3-pil`（可选 `python3-evdev` 与 `NotoSansCJK` 字体）；PC 无 `/dev/fb0` 时自动以内存虚拟帧缓冲运行，便于本地完整调试网页控台与接口。

## 2. 内置 10 类样张矩阵（320 × 170 原生设计）

1. **模拟常用 App UI（5 类）**
   - `ui_launcher`：启动器与菜单列表 UI（顶栏状态 + 图标高亮列表 + 底部 `4–8` 键位导航栏，测试列表行高与选中态对比）
   - `ui_dashboard`：系统监控与数据看板 UI（暗色卡片 + 彩色进度条 + 双圆环仪表 + 折线趋势图，测试扁屏多指标信息密度）
   - `ui_terminal`：SSH 终端与日志控制台 UI（多色高亮命令行输出 + 状态底栏，测试 `10–12px` 紧凑字符行数与配色可读性）
   - `ui_radio_spectrum`：频谱瀑布图与硬件工具 UI（实时频谱曲线 + 伪彩色瀑布热力图 + 频率读数，测试高密度像素图形表现）
   - `ui_chat_reader`：AI 对话气泡与阅读卡片 UI（双色消息气泡 + 多行中文排版 + 底栏输入提示，测试中文长句行距与阅读观感）
2. **测试图片（2 类）**
   - `photo_sunset`：日落山峦与湖面倒影合成测试照（大面积暖色天空渐变、远近山体剪影与水面波纹，测试照片层次与色带表现）
   - `photo_cyber_city`：高饱和霓虹光影与立体球体测试图（3D 高光阴影球体、品红/青蓝霓虹灯牌与暗部反光，测试 IPS 饱和度与暗部细节）
3. **屏幕硬件标定卡（3 类）**
   - `cal_color_bars`：标准 8 色饱和彩条 + 16 级灰阶步进 + 黑白死区分辨块
   - `cal_gradients`：R/G/B/Gray 四通道连续渐变条（直观对比原生 `rgb565` 色带断层与 `rgb565_dither` 误差扩散平滑效果）
   - `cal_typography_grid`：`320×170` 1px 贴边安全框与像素网格 + 中英文 `10/12/14/16/18/20px` 明暗底对照卡

## 3. 目录结构规划

```text
apps/screen-cast/
  todo.md                  范围、样张清单、实施阶段与完成标准
  README.md                运行说明、HTTP API 规范、打包与设备安装指南
  .env.example             运行配置模板（含中文备注）
  cp0_cast_app.py          设备端主程序（HTTP/Web 服务 + 10 类样张库 + 图像管线 + /dev/fb0 + evdev）
  build_deb.py             纯 Python 打包脚本（生成接入 APPLaunch 的 arm64 .deb 安装包）
  deploy_to_device.ps1     SSH 上传与安装辅助脚本（需确认后执行）
  assets/
    icon.png               APPLaunch 启动器应用图标（256x256）
  web/
    index.html             双栏网页控台页面
    app.css                浅色/暗色自适应样式
    app.js                 实时预览、拖拽/剪贴板推图、10 类样张矩阵与参数实时调整
  tests/
    test_screen_cast.py    单元与端到端 HTTP 接口回归测试
```

## 4. 实施阶段

### 阶段 1：自动化测试先行（`tests/test_screen_cast.py`）
- [x] 编写覆盖以下核心行为的测试用例：
  - `.env` 配置解析、边界校验、注释保留保存与非法参数拒绝；
  - `RGB888 -> RGB565` 小端序字节打包（验证纯红 `0xF800`、纯绿 `0x07E0`、纯蓝 `0x001F` 及帧长度严格等于 `108,800` 字节）与 `RGB565 -> PNG` 预览还原一致性；
  - 色彩模式（`rgb565`、`rgb565_dither`、`gray`、`mono_floyd`、`mono_threshold`）、缩放模式（`contain` / `cover` / `stretch`）、旋转（`0/90/180/270`）、亮度/对比度/饱和度/反相调整；
  - 全部 10 类内置样张列表元数据与逐张渲染校验（尺寸 `320×170`、非空色彩分布）；
  - HTTP 全接口（`GET /`、`GET /api/patterns`、`POST /push` raw/multipart/raw-rgb565、`POST /api/test-pattern`、`GET/POST /api/config`、`POST /api/control`、`GET /preview.png`、`GET /health`、鉴权 `401` 与畸形请求 `400` 异常处理）；
  - `.deb` 打包产物结构校验（包含 `APPLaunch` `.desktop`、图标与可执行权限）。

### 阶段 2：设备端渲染、样张库、按键与 HTTP 服务实现（`cp0_cast_app.py` + `.env.example`）
- [x] 实现帧缓冲后端：自动识别 `/sys/class/graphics/fb*/name`（`st7789v_m5st` / `panel-mipi-dbi`）并唤醒 `/sys/class/graphics/fb*/blank`，使用 `mmap` 写入 `108,800` 字节；桌面环境自动回退到内存虚拟显存。
- [x] 实现待机等待页、10 类样张生成器与状态角标浮层。
- [x] 实现 `evdev` 键盘监听线程（无设备时静默降级）：`4`/`Left` 上一样张、`5`/`Right` 下一样张、`6` 循环切换色彩模式、`7` 开关信息角标、`8`/`L` 切换中英文（小屏采用精简简称）、短按 `ESC` 回待机页、长按 `ESC` 退出程序回 `APPLaunch`。
- [x] 实现带完整异常捕获的 `ThreadingHTTPServer` 接口、修改参数后自动重算当前画面、`toggle_lang` 双语同步及可选超时回退待机页。

### 阶段 3：双栏网页控台开发（`web/`）
- [x] 实现对称双栏响应式控台页面（支持浅色/暗色主题与顶栏 `En / Cn` 中英双语切换开关）：
  - 左栏：`320 × 170` 真实 RGB565 还原预览、点击/拖拽/剪贴板粘贴（`Ctrl+V`）即时推图、按分组排列的 10 类样张快捷按钮（带上/下一张切换）、清屏回待机按钮，以及设备帧率/IP/电量/内存遥测卡片；
  - 右栏：色彩模式、缩放策略、旋转、亮度/对比度/饱和度/阈值/反相调节（支持改动即刻实时预览与保存到 `.env`），附带自动拼好当前 IP 的 `curl` / Python 跨设备推送示例。

### 阶段 4：安装包构建与全项验证（`build_deb.py` + `README.md`）
- [x] 编写 `build_deb.py` 与启动器图标，生成可安装的 `dist/cp0-screen-cast_0.1.0_arm64.deb`（遵循 `APPLaunch` 目录规范）及部署脚本与 `README.md` 文档。
- [x] 运行 `unittest` 全量回归测试、`node --check` 前端语法检查、`dpkg-deb` 包结构核验，并在本地完成样张渲染与实时推图验证；全部文本/Markdown 文件校验 UTF-8 BOM + CRLF（`.env` 保持无 BOM + CRLF）。

## 5. 完成标准

1. `python -B -m unittest discover -s "apps/screen-cast/tests" -v` 全部通过，退出码为 `0`。
2. `node --check "apps/screen-cast/web/app.js"` 退出码为 `0`。
3. 本地运行 `cp0_cast_app.py` 后，网页控台可正常打开，10 类样张切换、上传/粘贴任意分辨率图片、切换色彩/缩放/亮度参数均能实时更新 `320 × 170` RGB565 预览图，通过 `POST /push` 推送返回 `200` 且 `frame_bytes=108800`。
4. `python "apps/screen-cast/build_deb.py"` 生成有效 `arm64.deb` 包，经 WSL `dpkg-deb -I` 与 `dpkg-deb -c` 校验包含可执行入口、`/usr/share/APPLaunch/applications/cp0-screen-cast.desktop` 与图标。
5. 新增 Markdown 文档统一为单 UTF-8 BOM + CRLF 换行（`BareLF=0`）；向真机 SSH 部署安装前单独与用户确认。
---

## 6. v0.2.0 升级计划：音视频同步投屏（命令行合流 + 网页本地视频投播）

### 6.1 升级范围
- **单连接音画合流接口（`POST /stream`）**：原生支持 HTTP/1.1 `Transfer-Encoding: chunked` 长连接流式读取与 `RIFF/AVI`（`rawvideo` `rgb565le`/`bgr565le` + `pcm_s16le`）实时分拣，画面块（`00dc`/`00db`）直刷 `/dev/fb0`，音频块（`01wb`）送入声卡播放队列；一条 `ffmpeg` 命令即可音画同传，设备端无需安装解码库。
- **低延迟音频输出引擎与独立音频接口（`POST /audio` + `POST /api/audio`）**：自动调用设备端 `pw-play` / `paplay` / `aplay` 低延迟管道播放 `S16_LE` PCM 音频，内置有界防堆积队列（积压超阈值自动丢弃旧音频帧防滞后）、静音开关与 `0–150%` 数字音量调节；无声卡桌面环境自动降级为内存计数后端。
- **双栏网页控台新增“本地音视频投播”面板（`web/`）**：支持在手机/电脑浏览器直接选择或拖入本地 `.mp4/.webm/.mov/.mp3/.wav` 文件，由浏览器本地解码并通过 `<canvas>`（`RGB565`）+ `Web Audio API`（`PCM`）同步推送至设备屏幕与扬声器，提供播放/暂停、进度拖动、循环、设备静音与音量滑块，并在控台底部展示可直接复制的 `ffmpeg` 音视频合流命令。
- **重新编译 `.deb` 安装包**：升级构建脚本与元数据至 `0.2.0`，生成 `dist/cp0-screen-cast_0.2.0_arm64.deb`。

### 6.2 实施阶段
- [x] **阶段 5（测试先行）**：在 `tests/test_screen_cast.py` 增加 HTTP `chunked` 流读取、AVI `rgb565le`/`bgr565le` + `pcm_s16le` 合流拆包、`POST /audio`、静音/音量缩放与队列防堆积回归测试。
- [x] **阶段 6（服务端音视频引擎）**：在 `cp0_cast_app.py` 实现 `AudioOutputSink`、chunked 流解析器、`POST /stream`、`POST /audio`、`POST /play` 与 `POST /api/audio`，并确保未知路由返回 `404` 时立即关闭连接（`close_conn=True`）。
- [x] **阶段 7（网页控台视频投播与重新打包）**：更新 `web/index.html`、`web/app.css`、`web/app.js` 增加音视频投播与音量控制卡片，更新 `build_deb.py` 生成新版 `.deb` 并完成全量校验。

### 6.3 v0.2.0 完成标准
1. `python -B -m unittest discover -s "apps/screen-cast/tests" -v` 全量通过。
2. 本地用真实 `ffmpeg ... -f avi http://127.0.0.1:<port>/stream` 推送测试视频流，验证服务端实时解出 `108,800` 字节 RGB565 画面帧与 PCM 音频字节且帧数/采样计数增长正常。
3. `node --check "apps/screen-cast/web/app.js"` 通过，网页控台选择本地视频可正常抽帧推屏与推音频。
4. 重新生成 `dist/cp0-screen-cast_0.2.0_arm64.deb` 并通过包结构检查；经用户确认后部署或提供给设备安装验证。
