/* 程序说明：CardputerZero 320×170 网页控台与无线投屏前端交互脚本（含 En/Cn 双语实时切换，零第三方依赖） */

(() => {
  'use strict';

  const I18N = {
    zh: {
      doc_title: 'CardputerZero 投屏与画面测试控台',
      h1_title: 'CardputerZero 画面测试与投屏控台',
      quick_actions_aria: '即时屏幕操作',
      lang_toggle_aria: '切换界面语言 (当前中文，点击切换英文)',
      badge_connecting: '连接中...',
      badge_online: '设备在线',
      badge_paused: '已冻结接收',
      badge_offline: '连接断开',
      btn_prev: '◀ 上一张',
      btn_next: '下一张 ▶',
      btn_pause: '冻结接收',
      btn_resume: '恢复接收',
      btn_waiting: '回待机页',
      preview_heading: '设备屏幕实时预览（320×170 RGB565）',
      preview_alt: 'CardputerZero 当前 320×170 RGB565 屏幕实时画面预览',
      pixel_sharp: '像素锐利',
      pixel_smooth: '平滑缩放',
      meta_mode_prefix: '状态：',
      meta_sha_prefix: '哈希：',
      meta_ms_prefix: '耗时：',
      mode_waiting: '待机等待页',
      mode_casting: '外部推流画面',
      mode_pattern_prefix: '样张: ',
      drop_zone_aria: '上传、拖拽或剪贴板粘贴图片上屏',
      file_label: '选图 / 拖拽 / Ctrl+V 贴图',
      btn_upload_push: '推送上屏',
      media_heading: '本地音视频文件投播（网页解码音画同传）',
      media_idle: '选择 MP4/WebM/MP3/WAV 即可播放上屏',
      media_file_label: '选择音视频',
      btn_media_play: '▶ 播放投屏',
      btn_media_pause: '⏸ 暂停投播',
      btn_media_stop: '⏹ 停止',
      lbl_media_seek: '媒体播放进度',
      lbl_media_loop: '循环播放',
      lbl_local_audio: '浏览器同时发声',
      media_playing: (name) => `投播中：${name}`,
      media_paused: (name) => `已暂停：${name}`,
      media_ready: (name) => `已就绪：${name}`,
      legend_audio: '设备音频输出控制（全局音量 / 静音）',
      lbl_audio_vol: '设备音量（0–150%）',
      lbl_audio_mute: '设备静音',
      audio_tag_fmt: (bk, kb) => `输出: ${bk} (${kb} KB)`,
      pattern_heading: '内置屏幕评估样张库（点击即刻上屏）',
      pattern_hint_default: '选择下方样张检验 UI 排版、色彩与字号',
      cat_app_ui: 'App UI 模拟',
      cat_photo: '测试图片',
      cat_cal: '屏幕标定',
      telemetry_heading: '设备硬件与推流状态',
      btn_refresh_status: '刷新状态',
      dt_mode: '当前模式',
      dt_frames: '收图 / 刷屏',
      dt_fps: '帧率 / 耗时',
      dt_fb: '显存后端',
      dt_addr: '设备地址',
      dt_wifi: 'Wi-Fi 信号',
      dt_bat: '电池状态',
      dt_sys: '温度 / 内存',
      wifi_sim: '本地模拟',
      wifi_off: '未连接',
      bat_charging: ' (充电)',
      bat_ac: '外接供电',
      last_err_prefix: '最近提示：',
      config_heading: '显示效果实时调参与持久化（.env）',
      btn_reset_tone: '重置画质 100%',
      legend_fps: '推流帧率控制（视频播放 / 游戏推流）',
      fps_presets_aria: '常用帧率档位',
      fps_unlimited: '不限速 MAX',
      lbl_target_fps: '固定上限',
      hint_target_fps: '0=不限 (0–120)',
      err_target_fps: '请输入 0–120 之间的整数（0 为不限速）。',
      val_fps_range: '帧率需为 0–120 整数',
      fps_cap_unlimited: '不限',
      fps_cap_fixed: (n) => `限${n}`,
      legend_color: '色彩量化与尺寸适配（切换即时生效）',
      lbl_color_mode: '色彩渲染模式（COLOR_MODE）',
      cm_rgb565: 'RGB565 原生彩屏',
      cm_dither: 'RGB565 抖动防色带',
      cm_gray: '8-bit 灰度',
      cm_floyd: '黑白 Floyd',
      cm_thresh: '黑白硬阈值',
      lbl_fit_mode: '缩放策略（FIT_MODE）',
      fit_contain: 'Contain 留边',
      fit_cover: 'Cover 铺满',
      fit_stretch: 'Stretch 拉伸',
      lbl_rotate: '顺时针旋转（ROTATE）',
      legend_tone: '亮度、对比度、饱和度与叠加项',
      lbl_brightness: '亮度（20–200%）',
      lbl_contrast: '对比度（20–200%）',
      lbl_saturation: '饱和度（0–200%）',
      lbl_threshold: '黑白阈值（0–255）',
      lbl_invert: '反相画面颜色（INVERT）',
      lbl_overlay: '设备右上角显示模式角标（7键）',
      lbl_bg_color: '留边色',
      legend_net: '服务端口、自动回退与鉴权',
      lbl_listen_host: '绑定地址',
      hint_listen_host: '默认 0.0.0.0',
      err_listen_host: '请输入合法监听 IP（如 0.0.0.0）。',
      lbl_listen_port: '端口',
      err_listen_port: '请输入 1–65535 之间的整数端口。',
      val_port_range: '端口需为 1–65535 整数',
      lbl_timeout: '无信号回退(s)',
      hint_timeout: '0常驻不退',
      err_timeout: '请输入 0–86400 之间的整数秒数。',
      val_timeout_range: '超时需为 0–86400 整数',
      lbl_token: '推送鉴权 Token（可选）',
      hint_token: '对应请求头 X-Cast-Token，留空允许局域网免密推送',
      err_token: 'Token 不能包含控制字符。',
      err_icon_aria: '错误',
      btn_show: '显示',
      btn_hide: '隐藏',
      lbl_diag_log: '开启内存盘按秒诊断日志（/tmp/cp0-screen-cast.log）',
      btn_open_logs: '查看日志',
      btn_clear_logs: '清空',
      msg_logs_empty: '当前暂无诊断日志（勾选开启后推流即按秒记录）。',
      msg_logs_cleared: '已清空 /tmp 内存盘诊断日志。',
      btn_save_config: '保存当前参数到 .env',
      api_heading: '任意设备推送命令示例（图片 / 视频 / 音频）',
      btn_copy_curl: '复制示例',
      curl_comment_1: '# 1. curl 推送单张 PNG/JPEG 图片上屏 (/push)',
      curl_comment_2: '# 2. ffmpeg 音视频合流实时投屏 (/stream，电脑解码零负担)',
      curl_comment_3: '# 3. curl 直接投送本地 .mp4 或 .wav 文件 (/play)',
      curl_comment_4: '# 4. 单独推送 16-bit PCM 音频流 (/audio)',
      msg_parse_err: '响应解析失败',
      msg_req_err: '请求失败',
      msg_pat_ok: (id, ms) => `已切换屏幕样张：${id}（耗时 ${ms} ms）`,
      msg_pat_err: (m) => `切换样张失败：${m}`,
      msg_ctrl_err: (m) => `控制操作失败：${m}`,
      msg_pick_img: '请先选择、拖入或粘贴图片。',
      msg_push_ok: (w, h, b, ms) => `图片已推送上屏（${w}×${h}，${b} 字节，耗时 ${ms} ms）。`,
      msg_push_err: (m) => `推送失败：${m}`,
      msg_form_invalid: '部分字段格式有误，请修正高亮输入框后再保存。',
      msg_save_ok: '参数已写入 .env 并刷新设备画面。',
      msg_save_err: (m) => `保存失败：${m}`,
      msg_reset_tone: '已恢复 100% 原始亮度、对比度与饱和度。',
      msg_copy_ok: '推送命令示例已复制到剪贴板。',
      msg_copy_err: '复制受限，请手动选择复制。',
      msg_init_err: (m) => `初始化失败：${m}`,
      msg_lang_switched: '已切换为中文界面（设备端同步刷新）。',
      msg_media_err: (m) => `音视频加载或播放失败：${m}`,
      msg_media_stopped: '已停止本地音视频投播。',
    },
    en: {
      doc_title: 'CardputerZero Display & Cast Console',
      h1_title: 'CardputerZero Display & Cast Console',
      quick_actions_aria: 'Quick screen actions',
      lang_toggle_aria: 'Switch UI language (Currently English, click for Chinese)',
      badge_connecting: 'Connecting...',
      badge_online: 'Online',
      badge_paused: 'Paused',
      badge_offline: 'Disconnected',
      btn_prev: '◀ Prev',
      btn_next: 'Next ▶',
      btn_pause: 'Freeze Rx',
      btn_resume: 'Resume Rx',
      btn_waiting: 'Standby',
      preview_heading: 'Live Device Screen (320×170 RGB565)',
      preview_alt: 'CardputerZero live 320×170 RGB565 screen preview',
      pixel_sharp: 'Pixel Sharp',
      pixel_smooth: 'Smooth',
      meta_mode_prefix: 'Mode: ',
      meta_sha_prefix: 'SHA: ',
      meta_ms_prefix: 'Time: ',
      mode_waiting: 'Standby Screen',
      mode_casting: 'External Cast',
      mode_pattern_prefix: 'Pattern: ',
      drop_zone_aria: 'Upload, drag-drop, or paste image to screen',
      file_label: 'Select / Drop / Ctrl+V Paste',
      btn_upload_push: 'Push Image',
      media_heading: 'Local Video & Audio Cast (Browser A/V Sync)',
      media_idle: 'Pick MP4/WebM/MP3/WAV to cast video & sound',
      media_file_label: 'Pick Media',
      btn_media_play: '▶ Play & Cast',
      btn_media_pause: '⏸ Pause Cast',
      btn_media_stop: '⏹ Stop',
      lbl_media_seek: 'Playback position',
      lbl_media_loop: 'Loop',
      lbl_local_audio: 'Play in Browser Too',
      media_playing: (name) => `Casting: ${name}`,
      media_paused: (name) => `Paused: ${name}`,
      media_ready: (name) => `Ready: ${name}`,
      legend_audio: 'Device Audio Output (Volume & Mute)',
      lbl_audio_vol: 'Device Volume (0–150%)',
      lbl_audio_mute: 'Mute Device',
      audio_tag_fmt: (bk, kb) => `Out: ${bk} (${kb} KB)`,
      pattern_heading: 'Built-in Test Patterns (Click to Cast)',
      pattern_hint_default: 'Pick a sample below to inspect UI layout, color & fonts',
      cat_app_ui: 'App UI',
      cat_photo: 'Photos',
      cat_cal: 'Calibrate',
      telemetry_heading: 'Device Hardware & Cast Telemetry',
      btn_refresh_status: 'Refresh',
      dt_mode: 'Mode',
      dt_frames: 'Rx / Blit',
      dt_fps: 'FPS / Time',
      dt_fb: 'Framebuffer',
      dt_addr: 'Endpoint',
      dt_wifi: 'Wi-Fi',
      dt_bat: 'Battery',
      dt_sys: 'Temp / RAM',
      wifi_sim: 'Local Sim',
      wifi_off: 'Offline',
      bat_charging: ' (Chg)',
      bat_ac: 'AC Power',
      last_err_prefix: 'Last notice: ',
      config_heading: 'Live Display Tuning & Persistence (.env)',
      btn_reset_tone: 'Reset Tone 100%',
      legend_fps: 'Stream FPS Control (Video / Game Cast)',
      fps_presets_aria: 'FPS rate presets',
      fps_unlimited: 'Unlimited MAX',
      lbl_target_fps: 'FPS Cap',
      hint_target_fps: '0=Max (0–120)',
      err_target_fps: 'Enter an integer 0–120 (0 = unlimited).',
      val_fps_range: 'FPS must be an integer 0–120',
      fps_cap_unlimited: 'MAX',
      fps_cap_fixed: (n) => `Cap ${n}`,
      legend_color: 'Color Quantization & Fit (Live Apply)',
      lbl_color_mode: 'Color Mode (COLOR_MODE)',
      cm_rgb565: 'RGB565 Native',
      cm_dither: 'RGB565 Dither',
      cm_gray: '8-bit Gray',
      cm_floyd: '1-bit Floyd',
      cm_thresh: '1-bit Threshold',
      lbl_fit_mode: 'Fit Mode (FIT_MODE)',
      fit_contain: 'Contain',
      fit_cover: 'Cover',
      fit_stretch: 'Stretch',
      lbl_rotate: 'Clockwise Rotate (ROTATE)',
      legend_tone: 'Brightness, Contrast, Saturation & Overlay',
      lbl_brightness: 'Brightness (20–200%)',
      lbl_contrast: 'Contrast (20–200%)',
      lbl_saturation: 'Saturation (0–200%)',
      lbl_threshold: 'Threshold (0–255)',
      lbl_invert: 'Invert Colors (INVERT)',
      lbl_overlay: 'Show Top-Right HUD Tag (Key 7)',
      lbl_bg_color: 'Pad Bg',
      legend_net: 'Network Port, Idle Fallback & Auth',
      lbl_listen_host: 'Bind Host',
      hint_listen_host: 'Default 0.0.0.0',
      err_listen_host: 'Enter a valid listen IP or host (e.g. 0.0.0.0).',
      lbl_listen_port: 'Port',
      err_listen_port: 'Enter an integer port between 1 and 65535.',
      val_port_range: 'Port must be an integer 1–65535',
      lbl_timeout: 'Timeout(s)',
      hint_timeout: '0 = Stay',
      err_timeout: 'Enter integer seconds between 0 and 86400.',
      val_timeout_range: 'Timeout must be an integer 0–86400',
      lbl_token: 'Push Auth Token (Optional)',
      hint_token: 'Matches header X-Cast-Token; leave blank for open LAN push',
      err_token: 'Token cannot contain control characters.',
      err_icon_aria: 'Error',
      btn_show: 'Show',
      btn_hide: 'Hide',
      lbl_diag_log: 'Per-second RAM diagnostic log (/tmp/cp0-screen-cast.log)',
      btn_open_logs: 'View Log',
      btn_clear_logs: 'Clear',
      msg_logs_empty: 'Diagnostic log is currently empty (enable the toggle to record).',
      msg_logs_cleared: 'Cleared /tmp diagnostic log.',
      btn_save_config: 'Save Settings to .env',
      api_heading: 'Cross-Device Push Examples (Image / Video / Audio)',
      btn_copy_curl: 'Copy',
      curl_comment_1: '# 1. curl push a single PNG/JPEG image (/push)',
      curl_comment_2: '# 2. ffmpeg live audio+video stream (/stream, decoded on PC)',
      curl_comment_3: '# 3. curl direct .mp4 or .wav file upload (/play)',
      curl_comment_4: '# 4. Stream raw 16-bit PCM audio (/audio)',
      msg_parse_err: 'Failed to parse response',
      msg_req_err: 'Request failed',
      msg_pat_ok: (id, ms) => `Pattern switched: ${id} (${ms} ms)`,
      msg_pat_err: (m) => `Pattern switch failed: ${m}`,
      msg_ctrl_err: (m) => `Control command failed: ${m}`,
      msg_pick_img: 'Select, drag-drop, or paste an image first.',
      msg_push_ok: (w, h, b, ms) => `Image pushed to screen (${w}×${h}, ${b} bytes, ${ms} ms).`,
      msg_push_err: (m) => `Push failed: ${m}`,
      msg_form_invalid: 'Some fields are invalid; fix highlighted inputs before saving.',
      msg_save_ok: 'Settings saved to .env and applied to screen.',
      msg_save_err: (m) => `Save failed: ${m}`,
      msg_reset_tone: 'Restored 100% brightness, contrast, and saturation.',
      msg_copy_ok: 'Push command copied to clipboard.',
      msg_copy_err: 'Clipboard unavailable; select and copy manually.',
      msg_init_err: (m) => `Initialization failed: ${m}`,
      msg_lang_switched: 'Switched to English UI (synced with device).',
      msg_media_err: (m) => `Media playback failed: ${m}`,
      msg_media_stopped: 'Stopped local media casting.',
    },
  };

  const form = document.getElementById('config-form');
  const statusBanner = document.getElementById('global-status');
  const previewImg = document.getElementById('preview-img');
  const serviceBadge = document.getElementById('service-badge');
  const toggleLangBtn = document.getElementById('btn-toggle-lang');
  const togglePauseBtn = document.getElementById('btn-toggle-pause');
  const pixelModeBtn = document.getElementById('btn-pixel-mode');
  const fileInput = document.getElementById('image-file-input');
  const dropZone = document.getElementById('drop-zone');
  const patternGroupsEl = document.getElementById('pattern-groups');
  const patternDescEl = document.getElementById('pattern-desc');
  const curlBox = document.getElementById('curl-example');
  const toggleTokenBtn = document.getElementById('toggle-token-btn');
  const tokenInput = document.getElementById('CAST_TOKEN');
  const targetFpsInput = document.getElementById('TARGET_FPS');
  const fpsChips = [...document.querySelectorAll('.fps-chip')];
  const audioVolSlider = document.getElementById('AUDIO_VOLUME');
  const audioVolLabel = document.getElementById('audio-vol-val');
  const audioMuteCheck = document.getElementById('AUDIO_MUTE');
  const audioBackendTag = document.getElementById('audio-backend-tag');

  const mediaZone = document.getElementById('media-zone');
  const mediaFileInput = document.getElementById('media-file-input');
  const mediaToggleBtn = document.getElementById('btn-media-toggle');
  const mediaStopBtn = document.getElementById('btn-media-stop');
  const mediaSeek = document.getElementById('media-seek');
  const mediaTimeEl = document.getElementById('media-time');
  const mediaStateTag = document.getElementById('media-state-tag');
  const mediaLoopCheck = document.getElementById('media-loop');
  const mediaLocalAudioCheck = document.getElementById('media-local-audio');
  const castVideo = document.getElementById('cast-video');
  const castCanvas = document.getElementById('cast-canvas');
  const castCtx = castCanvas.getContext('2d', { willReadFrequently: true });

  const sliders = {
    BRIGHTNESS: document.getElementById('BRIGHTNESS'),
    CONTRAST: document.getElementById('CONTRAST'),
    SATURATION: document.getElementById('SATURATION'),
    THRESHOLD: document.getElementById('THRESHOLD'),
  };
  const sliderLabels = {
    BRIGHTNESS: document.getElementById('brightness-val'),
    CONTRAST: document.getElementById('contrast-val'),
    SATURATION: document.getElementById('saturation-val'),
    THRESHOLD: document.getElementById('threshold-val'),
  };

  let currentLang = 'zh';
  let currentPaused = false;
  let activePatternId = '';
  let patternCatalog = [];
  let lastHealthSnapshot = null;
  let lastDeviceInfo = { ip: '127.0.0.1', port: 8787 };
  let healthInFlight = false;
  let liveApplyTimer = null;
  let lastPreviewKey = '';
  let lastPreviewFetchAt = 0;

  const t = (key) => I18N[currentLang]?.[key] ?? I18N.zh[key] ?? key;

  /* 单一全页 polite live region，延迟 500ms 播报交互后出现的字段校验错误 */
  const announcer = document.createElement('div');
  announcer.setAttribute('aria-live', 'polite');
  announcer.classList.add('visually-hidden');
  document.body.append(announcer);
  let announceTimer = null;
  let announcedField = null;

  const linkError = (el, shown) => {
    const errorId = el.dataset?.error;
    if (!errorId) return;
    const ids = (el.getAttribute('aria-describedby') || '')
      .split(/\s+/)
      .filter((id) => id && id !== errorId);
    if (shown) ids.push(errorId);
    if (ids.length) el.setAttribute('aria-describedby', ids.join(' '));
    else el.removeAttribute('aria-describedby');
  };

  const spokenText = (node) => {
    const copy = node.cloneNode(true);
    copy.querySelectorAll('[aria-hidden="true"]').forEach((n) => n.remove());
    copy.querySelectorAll('[role="img"][aria-label]').forEach((n) => {
      n.replaceWith(`${n.getAttribute('aria-label')}: `);
    });
    return copy.textContent.replace(/\s+/g, ' ').trim();
  };

  const announceError = (el) => {
    const errNode = document.getElementById(el.dataset.error);
    if (!errNode) return;
    const labelText = el.labels?.[0] ? `${spokenText(el.labels[0])}: ` : '';
    clearTimeout(announceTimer);
    announcer.textContent = '';
    announcedField = el;
    announceTimer = setTimeout(() => {
      announcer.textContent = labelText + spokenText(errNode);
    }, 500);
  };

  const customRangeValidators = {
    TARGET_FPS: (v) => {
      const n = Number(v);
      return Number.isInteger(n) && n >= 0 && n <= 120 ? '' : t('val_fps_range');
    },
    LISTEN_PORT: (v) => {
      const n = Number(v);
      return Number.isInteger(n) && n >= 1 && n <= 65535 ? '' : t('val_port_range');
    },
    CAST_TIMEOUT_SEC: (v) => {
      const n = Number(v);
      return Number.isInteger(n) && n >= 0 && n <= 86400 ? '' : t('val_timeout_range');
    },
  };

  const applyCustomConstraint = (el) => {
    const checker = customRangeValidators[el.name];
    if (!checker) return;
    el.setCustomValidity('');
    if (el.validity.valid) {
      const msg = checker(el.value.trim());
      if (msg) el.setCustomValidity(msg);
    }
  };

  const flagged = new WeakSet();
  const announced = new WeakSet();
  const dirtyMap = new WeakMap();
  const supportsUserInvalid = CSS.supports('selector(:user-invalid)');
  const supportsAccentColor = CSS.supports('accent-color', 'auto');

  const updateSliderFallbackProgress = (sliderEl) => {
    if (supportsAccentColor || !sliderEl) return;
    const min = Number(sliderEl.min || 0);
    const max = Number(sliderEl.max || 100);
    const val = Number(sliderEl.value || 0);
    const pct = max > min ? ((val - min) * 100) / (max - min) : 0;
    sliderEl.style.setProperty('--progress', `${pct}%`);
  };

  const syncFieldAria = (el, announce = false) => {
    if (!el || !el.matches?.('input, select, textarea')) return;
    applyCustomConstraint(el);
    const invalid = supportsUserInvalid
      ? el.matches(':user-invalid')
      : el.classList.contains('user-invalid-fallback');

    if (invalid) {
      if (announce && !announced.has(el)) {
        announceError(el);
        announced.add(el);
      }
      el.setAttribute('aria-invalid', 'true');
      linkError(el, true);
      flagged.add(el);
    } else if (flagged.has(el) || el.getAttribute('aria-invalid') !== 'true') {
      el.setAttribute('aria-invalid', 'false');
      linkError(el, false);
      flagged.delete(el);
      announced.delete(el);
      if (announcedField === el) {
        clearTimeout(announceTimer);
        announcer.textContent = '';
      }
    }
  };

  const initFormAccessibility = () => {
    form.querySelectorAll('input, select, textarea').forEach((el) => {
      el.setAttribute('aria-invalid', 'false');
    });

    form.addEventListener('blur', (e) => {
      const el = e.target;
      if (!supportsUserInvalid && el.checkValidity) {
        applyCustomConstraint(el);
        const st = dirtyMap.get(el) || { hasInteracted: false, hasBlurred: false };
        st.hasBlurred = true;
        dirtyMap.set(el, st);
        if (st.hasInteracted) {
          el.classList.toggle('user-invalid-fallback', !el.validity.valid);
          el.classList.toggle('user-valid-fallback', el.validity.valid);
        }
      }
      syncFieldAria(el, true);
    }, true);

    form.addEventListener('input', (e) => {
      const el = e.target;
      applyCustomConstraint(el);
      if (!supportsUserInvalid && el.checkValidity) {
        const st = dirtyMap.get(el) || { hasInteracted: false, hasBlurred: false };
        st.hasInteracted = true;
        dirtyMap.set(el, st);
        if (st.hasBlurred) {
          el.classList.toggle('user-invalid-fallback', !el.validity.valid);
          el.classList.toggle('user-valid-fallback', el.validity.valid);
        }
      }
      if (el.hasAttribute('aria-invalid')) syncFieldAria(el, false);
    });

    form.addEventListener('change', (e) => syncFieldAria(e.target, true), true);

    form.addEventListener('invalid', (e) => {
      const el = e.target;
      if (!supportsUserInvalid) {
        dirtyMap.set(el, { hasInteracted: true, hasBlurred: true });
        el.classList.add('user-invalid-fallback');
        el.classList.remove('user-valid-fallback');
      }
      announced.add(el);
      syncFieldAria(el, false);
    }, true);

    form.addEventListener('reset', (e) => {
      setTimeout(() => {
        [...e.target.elements].forEach((el) => {
          dirtyMap.delete(el);
          el.classList?.remove('user-invalid-fallback', 'user-valid-fallback');
          syncFieldAria(el, false);
        });
      });
    }, true);
  };

  const showStatus = (msg, isError = false) => {
    statusBanner.textContent = msg;
    statusBanner.classList.add('visible');
    statusBanner.classList.toggle('error', isError);
  };

  const fetchJson = async (url, options = {}) => {
    const resp = await fetch(url, options);
    const raw = await resp.text();
    let data = {};
    if (raw) {
      try {
        data = JSON.parse(raw);
      } catch {
        throw new Error(`${t('msg_parse_err')} (${resp.status})`);
      }
    }
    if (!resp.ok || data.ok === false) {
      const err = new Error(data.error || `${t('msg_req_err')} (${resp.status})`);
      err.fields = data.fields || {};
      throw err;
    }
    return data;
  };

  const getHeadersWithToken = (extra = {}) => {
    const tok = tokenInput.value.trim();
    return tok ? { ...extra, 'X-Cast-Token': tok } : { ...extra };
  };

  const refreshPreviewImage = (key = '') => {
    const ver = key ? `v=${encodeURIComponent(key)}&` : '';
    previewImg.src = `/preview.png?${ver}ts=${Date.now()}`;
  };

  const patternTitle = (item) =>
    (currentLang === 'en' ? item.title_en : item.title_zh) || item.title || item.id;
  const patternDesc = (item) =>
    (currentLang === 'en' ? item.desc_en : item.desc_zh) || item.desc || '';

  const updatePatternButtonsHighlight = () => {
    patternGroupsEl.querySelectorAll('.pattern-btn').forEach((btn) => {
      const isMatch = btn.dataset.pattern === activePatternId;
      btn.classList.toggle('active', isMatch);
      btn.setAttribute('aria-pressed', isMatch ? 'true' : 'false');
    });
    const found = patternCatalog.find((p) => p.id === activePatternId);
    if (found) {
      const sep = currentLang === 'en' ? ': ' : '：';
      patternDescEl.textContent = `${patternTitle(found)}${sep}${patternDesc(found)}`;
    } else {
      patternDescEl.textContent = t('pattern_hint_default');
    }
  };

  const renderPatternButtons = (patterns) => {
    patternCatalog = patterns;
    patternGroupsEl.textContent = '';
    const groups = [
      { key: 'app_ui', label: t('cat_app_ui') },
      { key: 'photo', label: t('cat_photo') },
      { key: 'calibration', label: t('cat_cal') },
    ];

    for (const grp of groups) {
      const items = patterns.filter((p) => p.category === grp.key);
      if (!items.length) continue;
      const row = document.createElement('div');
      row.className = 'pattern-group-row';

      const tag = document.createElement('span');
      tag.className = 'pattern-cat-tag';
      tag.textContent = grp.label;
      row.append(tag);

      for (const item of items) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'pattern-btn';
        btn.dataset.pattern = item.id;
        btn.title = patternDesc(item);
        btn.textContent = patternTitle(item);
        btn.addEventListener('click', () => triggerPattern(item.id));
        row.append(btn);
      }
      patternGroupsEl.append(row);
    }
    updatePatternButtonsHighlight();
  };

  const updateCurlExample = (ip, port) => {
    const targetOrigin = ip && ip !== '127.0.0.1' ? `http://${ip}:${port}` : window.location.origin;
    const tok = tokenInput.value.trim();
    const tokFlag = tok ? ` -H "X-Cast-Token: ${tok}"` : '';
    const ffHdr = tok ? ` -headers "X-Cast-Token: ${tok}\\r\\n"` : '';
    curlBox.textContent =
      `${t('curl_comment_1')}\n` +
      `curl -X POST "${targetOrigin}/push"${tokFlag} -H "Content-Type: image/png" --data-binary @screen.png\n` +
      `${t('curl_comment_2')}\n` +
      `ffmpeg -re -i movie.mp4 -vf "fps=24,scale=320:170:force_original_aspect_ratio=decrease,pad=320:170:(ow-iw)/2:(oh-ih)/2" -c:v mjpeg -q:v 7 -ar 24000 -ac 1 -c:a pcm_s16le -flush_packets 1 -avioflags direct -f avi${ffHdr} "${targetOrigin}/stream"\n` +
      `${t('curl_comment_3')}\n` +
      `curl -X POST "${targetOrigin}/play"${tokFlag} --data-binary @clip.mp4\n` +
      `${t('curl_comment_4')}\n` +
      `ffmpeg -re -i music.mp3 -ar 24000 -ac 1 -f s16le${ffHdr} "${targetOrigin}/audio?rate=24000&channels=1"`;
  };

  const renderHealthView = (h) => {
    if (!h) return;
    currentPaused = Boolean(h.paused);
    activePatternId = h.mode === 'pattern' ? (h.active_pattern || '') : '';
    updatePatternButtonsHighlight();

    serviceBadge.textContent = currentPaused ? t('badge_paused') : t('badge_online');
    serviceBadge.classList.toggle('ok', !currentPaused);
    serviceBadge.classList.toggle('paused', currentPaused);
    togglePauseBtn.textContent = currentPaused ? t('btn_resume') : t('btn_pause');

    const modeMap = {
      waiting: t('mode_waiting'),
      casting: t('mode_casting'),
      pattern: `${t('mode_pattern_prefix')}${h.active_pattern}`,
    };
    const modeText = modeMap[h.mode] || h.mode;
    document.getElementById('meta-mode').textContent = `${t('meta_mode_prefix')}${modeText}`;
    document.getElementById('meta-sha').textContent = `${t('meta_sha_prefix')}${(h.frame_sha256 || '').slice(0, 10) || '--'}`;
    const ms = h.stats?.last_process_ms;
    document.getElementById('meta-ms').textContent = `${t('meta_ms_prefix')}${ms !== null && ms !== undefined ? `${ms} ms` : '--'}`;

    const capFps = Number(h.config?.TARGET_FPS ?? 0);
    const capTag = capFps > 0 ? t('fps_cap_fixed')(capFps) : t('fps_cap_unlimited');
    document.getElementById('stat-mode').textContent = modeText;
    document.getElementById('stat-frames').textContent = `${h.stats?.received_frames ?? 0} / ${h.stats?.blitted_frames ?? 0}`;
    document.getElementById('stat-fps').textContent = `${h.fps ?? 0} FPS (${capTag}) / ${ms ?? '--'}ms`;
    if (document.activeElement !== targetFpsInput && String(capFps) !== targetFpsInput.value.trim()) {
      targetFpsInput.value = String(capFps);
      syncFpsChipsHighlight(capFps);
    }

    const dev = h.device || {};
    lastDeviceInfo = { ip: dev.ip || '127.0.0.1', port: dev.port || 8787 };
    document.getElementById('stat-fb').textContent = `${dev.fb_backend || '--'} (${dev.fb_device || ''})`;
    document.getElementById('dev-addr').textContent = `${lastDeviceInfo.ip}:${lastDeviceInfo.port}`;
    document.getElementById('dev-wifi').textContent =
      dev.wifi_strength !== null && dev.wifi_strength !== undefined
        ? `${dev.wifi_strength}%`
        : (dev.fb_backend === 'memory' ? t('wifi_sim') : t('wifi_off'));
    document.getElementById('dev-bat').textContent =
      dev.battery_percent !== null && dev.battery_percent !== undefined
        ? `${dev.battery_percent}%${dev.battery_charging ? t('bat_charging') : ''}`
        : t('bat_ac');
    const tempStr = dev.cpu_temp_c !== null && dev.cpu_temp_c !== undefined ? `${dev.cpu_temp_c}°C` : '--';
    const memStr = dev.mem_total_mb ? `${dev.mem_used_mb}/${dev.mem_total_mb}M` : '--';
    document.getElementById('dev-sys').textContent = `${tempStr} / ${memStr}`;

    if (h.audio) {
      const playedKb = Math.round((h.audio.played_bytes || 0) / 1024);
      audioBackendTag.textContent = t('audio_tag_fmt')(h.audio.backend || 'memory', playedKb);
      if (document.activeElement !== audioVolSlider && h.audio.volume !== undefined) {
        audioVolSlider.value = String(h.audio.volume);
        audioVolLabel.textContent = String(h.audio.volume);
        audioVolSlider.setAttribute('aria-valuetext', `${h.audio.volume}%`);
        updateSliderFallbackProgress(audioVolSlider);
      }
      if (document.activeElement !== audioMuteCheck && h.audio.muted !== undefined) {
        audioMuteCheck.checked = Boolean(h.audio.muted);
      }
    }

    updateCurlExample(lastDeviceInfo.ip, lastDeviceInfo.port);

    const errEl = document.getElementById('last-error-text');
    if (h.stats?.last_error) {
      errEl.textContent = `${t('last_err_prefix')}${h.stats.last_error}`;
      errEl.hidden = false;
    } else {
      errEl.hidden = true;
    }
  };

  /* 切换网页全量静态/动态文案与无障碍属性 */
  const applyLanguage = (lang) => {
    currentLang = String(lang).toLowerCase() === 'en' ? 'en' : 'zh';
    document.documentElement.lang = currentLang === 'en' ? 'en' : 'zh-CN';
    document.title = t('doc_title');

    toggleLangBtn.querySelectorAll('[data-lang-pill]').forEach((pill) => {
      pill.classList.toggle('active', pill.dataset.langPill === currentLang);
    });

    document.querySelectorAll('[data-i18n]').forEach((el) => {
      el.textContent = t(el.dataset.i18n);
    });
    document.querySelectorAll('[data-i18n-aria]').forEach((el) => {
      el.setAttribute('aria-label', t(el.dataset.i18nAria));
    });
    document.querySelectorAll('[data-i18n-alt]').forEach((el) => {
      el.setAttribute('alt', t(el.dataset.i18nAlt));
    });

    const isPixel = previewImg.classList.contains('pixelated');
    pixelModeBtn.textContent = isPixel ? t('pixel_sharp') : t('pixel_smooth');
    const showingTok = tokenInput.type === 'text';
    toggleTokenBtn.textContent = showingTok ? t('btn_hide') : t('btn_show');
    togglePauseBtn.textContent = currentPaused ? t('btn_resume') : t('btn_pause');
    syncMediaStatusText();

    if (patternCatalog.length) {
      renderPatternButtons(patternCatalog);
    } else {
      patternDescEl.textContent = t('pattern_hint_default');
    }

    if (lastHealthSnapshot) {
      renderHealthView(lastHealthSnapshot);
    } else {
      serviceBadge.textContent = t('badge_connecting');
      updateCurlExample(lastDeviceInfo.ip, lastDeviceInfo.port);
    }

    form.querySelectorAll('input').forEach((el) => applyCustomConstraint(el));
  };

  const syncFpsChipsHighlight = (val) => {
    const num = Number(String(val).trim());
    fpsChips.forEach((chip) => {
      const match = !Number.isNaN(num) && Number(chip.dataset.fps) === num;
      chip.classList.toggle('active', match);
      chip.setAttribute('aria-pressed', match ? 'true' : 'false');
    });
  };

  const fillConfigForm = (cfg) => {
    if (cfg.UI_LANG) {
      applyLanguage(cfg.UI_LANG);
    }
    targetFpsInput.value = cfg.TARGET_FPS ?? 0;
    syncFpsChipsHighlight(targetFpsInput.value);
    document.getElementById('LISTEN_HOST').value = cfg.LISTEN_HOST ?? '0.0.0.0';
    document.getElementById('LISTEN_PORT').value = cfg.LISTEN_PORT ?? 8787;
    document.getElementById('CAST_TIMEOUT_SEC').value = cfg.CAST_TIMEOUT_SEC ?? 0;
    tokenInput.value = cfg.CAST_TOKEN ?? '';
    document.getElementById('BG_COLOR').value = cfg.BG_COLOR ?? '#000000';
    document.getElementById('INVERT').checked = Boolean(cfg.INVERT);
    document.getElementById('SHOW_OVERLAY').checked = Boolean(cfg.SHOW_OVERLAY);
    document.getElementById('DIAG_LOG').checked = Boolean(cfg.DIAG_LOG);
    if (cfg.AUDIO_VOLUME !== undefined) {
      audioVolSlider.value = String(cfg.AUDIO_VOLUME);
      audioVolLabel.textContent = String(cfg.AUDIO_VOLUME);
      audioVolSlider.setAttribute('aria-valuetext', `${cfg.AUDIO_VOLUME}%`);
      updateSliderFallbackProgress(audioVolSlider);
    }
    if (cfg.AUDIO_MUTE !== undefined) {
      audioMuteCheck.checked = Boolean(cfg.AUDIO_MUTE);
    }

    for (const key of Object.keys(sliders)) {
      if (cfg[key] !== undefined) {
        sliders[key].value = String(cfg[key]);
        sliderLabels[key].textContent = String(cfg[key]);
        updateSliderFallbackProgress(sliders[key]);
      }
    }

    const cmRadio = form.querySelector(`input[name="COLOR_MODE"][value="${cfg.COLOR_MODE}"]`);
    if (cmRadio) cmRadio.checked = true;
    const fitRadio = form.querySelector(`input[name="FIT_MODE"][value="${cfg.FIT_MODE}"]`);
    if (fitRadio) fitRadio.checked = true;
    const rotRadio = form.querySelector(`input[name="ROTATE"][value="${cfg.ROTATE}"]`);
    if (rotRadio) rotRadio.checked = true;
  };

  const collectConfigPayload = (saveToDisk = true) => {
    const fd = new FormData(form);
    return {
      save: saveToDisk,
      UI_LANG: currentLang,
      TARGET_FPS: Number(fd.get('TARGET_FPS') || 0),
      LISTEN_HOST: String(fd.get('LISTEN_HOST') || '0.0.0.0').trim(),
      LISTEN_PORT: Number(fd.get('LISTEN_PORT') || 8787),
      CAST_TIMEOUT_SEC: Number(fd.get('CAST_TIMEOUT_SEC') || 0),
      CAST_TOKEN: String(fd.get('CAST_TOKEN') || ''),
      COLOR_MODE: String(fd.get('COLOR_MODE') || 'rgb565'),
      FIT_MODE: String(fd.get('FIT_MODE') || 'contain'),
      ROTATE: Number(fd.get('ROTATE') || 0),
      BG_COLOR: String(document.getElementById('BG_COLOR').value || '#000000'),
      BRIGHTNESS: Number(sliders.BRIGHTNESS.value),
      CONTRAST: Number(sliders.CONTRAST.value),
      SATURATION: Number(sliders.SATURATION.value),
      THRESHOLD: Number(sliders.THRESHOLD.value),
      INVERT: document.getElementById('INVERT').checked,
      SHOW_OVERLAY: document.getElementById('SHOW_OVERLAY').checked,
      DIAG_LOG: document.getElementById('DIAG_LOG').checked,
      AUDIO_VOLUME: Number(audioVolSlider.value || 100),
      AUDIO_MUTE: audioMuteCheck.checked,
    };
  };

  const refreshHealth = async () => {
    if (healthInFlight) return;
    healthInFlight = true;
    try {
      const h = await fetchJson('/health');
      lastHealthSnapshot = h;
      const srvLang = h.config?.UI_LANG === 'en' ? 'en' : 'zh';
      if (srvLang !== currentLang) {
        applyLanguage(srvLang);
      } else {
        renderHealthView(h);
      }

      const key = `${h.frame_seq ?? 0}:${h.frame_sha256 || ''}`;
      if (key !== lastPreviewKey) {
        const localVideoLive = mediaCastingActive && !castVideo.paused && !castVideo.ended && castVideo.videoWidth > 0;
        if (localVideoLive) {
          /* 网页本地视频投播期间直接展示同源 #cast-canvas，零反向拉取 /preview.png，释放设备 CPU 与 Wi-Fi 带宽 */
          lastPreviewKey = key;
        } else {
          const nowMs = Date.now();
          const minGap = Number(h.fps || 0) >= 4 ? 2000 : 0;
          if (!minGap || nowMs - lastPreviewFetchAt >= minGap) {
            lastPreviewKey = key;
            lastPreviewFetchAt = nowMs;
            refreshPreviewImage(key);
          }
        }
      }
    } catch {
      serviceBadge.textContent = t('badge_offline');
      serviceBadge.classList.remove('ok');
      serviceBadge.classList.add('paused');
    } finally {
      healthInFlight = false;
    }
  };

  const triggerPattern = async (patternId) => {
    stopMediaCast(false);
    try {
      const prevKey = lastPreviewKey;
      const res = await fetchJson('/api/test-pattern', {
        method: 'POST',
        headers: getHeadersWithToken({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ pattern: patternId }),
      });
      activePatternId = res.active_pattern || patternId;
      updatePatternButtonsHighlight();
      showStatus(t('msg_pat_ok')(activePatternId, res.process_ms));
      await refreshHealth();
      if (lastPreviewKey === prevKey) refreshPreviewImage(lastPreviewKey);
    } catch (err) {
      showStatus(t('msg_pat_err')(err.message), true);
    }
  };

  const runControl = async (action) => {
    try {
      const prevKey = lastPreviewKey;
      const res = await fetchJson('/api/control', {
        method: 'POST',
        headers: getHeadersWithToken({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ action }),
      });
      if (res.config?.UI_LANG) {
        applyLanguage(res.config.UI_LANG);
      }
      await refreshHealth();
      if (lastPreviewKey === prevKey) refreshPreviewImage(lastPreviewKey);
      return res;
    } catch (err) {
      showStatus(t('msg_ctrl_err')(err.message), true);
      return null;
    }
  };

  const isMediaFile = (file) => {
    if (!file) return false;
    const tp = (file.type || '').toLowerCase();
    if (tp.startsWith('video/') || tp.startsWith('audio/')) return true;
    return /\.(mp4|webm|mov|mkv|avi|mp3|wav|ogg|m4a|flac)$/i.test(file.name || '');
  };

  /* -----------------------------------------------------------------------
   * 网页本地音视频解码与同步推流引擎（<video> + <canvas> RGB565 + Web Audio PCM）
   * ----------------------------------------------------------------------- */
  let mediaObjectUrl = '';
  let currentMediaName = '';
  let mediaCastingActive = false;
  let mediaFrameTimer = null;
  let videoInFlightCount = 0;
  let videoEncodeBusy = false;
  let clientFrameSeq = 0;
  let streamSessionId = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
  let audioPushInFlight = 0;
  let audioCtx = null;
  let monitorGainNode = null;
  let pcmBatchChunks = [];
  let pcmBatchSamples = 0;
  let audioApplyTimer = null;
  const TARGET_AUDIO_RATE = 24000;
  const MAX_VIDEO_INFLIGHT = 3;

  const fmtMediaSec = (sec) => {
    if (!Number.isFinite(sec) || sec < 0) return '00:00';
    const total = Math.floor(sec);
    const m = String(Math.floor(total / 60)).padStart(2, '0');
    const s = String(total % 60).padStart(2, '0');
    return `${m}:${s}`;
  };

  const syncLocalCanvasVisibility = () => {
    const showLocal = mediaCastingActive && !castVideo.paused && !castVideo.ended && castVideo.videoWidth > 0;
    castCanvas.hidden = !showLocal;
    previewImg.hidden = showLocal;
  };

  const syncMediaStatusText = () => {
    syncLocalCanvasVisibility();
    const playing = mediaCastingActive && !castVideo.paused && !castVideo.ended;
    mediaToggleBtn.textContent = playing ? t('btn_media_pause') : t('btn_media_play');
    if (!currentMediaName) {
      mediaStateTag.textContent = t('media_idle');
    } else if (playing) {
      mediaStateTag.textContent = t('media_playing')(currentMediaName);
    } else if (castVideo.currentTime > 0 && !castVideo.ended) {
      mediaStateTag.textContent = t('media_paused')(currentMediaName);
    } else {
      mediaStateTag.textContent = t('media_ready')(currentMediaName);
    }
  };

  const updateMediaSeekUi = () => {
    const dur = Number.isFinite(castVideo.duration) && castVideo.duration > 0 ? castVideo.duration : 0;
    const cur = Math.min(dur || 0, castVideo.currentTime || 0);
    const ratio = dur > 0 ? Math.round((cur / dur) * 1000) : 0;
    mediaSeek.value = String(ratio);
    updateSliderFallbackProgress(mediaSeek);
    const timeLabel = `${fmtMediaSec(cur)} / ${fmtMediaSec(dur)}`;
    mediaTimeEl.textContent = timeLabel;
    mediaSeek.setAttribute('aria-valuetext', timeLabel);
  };

  const flushPcmBatch = () => {
    if (!pcmBatchSamples) return;
    const merged = new Int16Array(pcmBatchSamples);
    let offset = 0;
    for (const part of pcmBatchChunks) {
      merged.set(part, offset);
      offset += part.length;
    }
    pcmBatchChunks = [];
    pcmBatchSamples = 0;
    if (audioPushInFlight >= 2) return;
    audioPushInFlight += 1;
    fetch(`/audio?rate=${TARGET_AUDIO_RATE}&channels=1`, {
      method: 'POST',
      headers: getHeadersWithToken({ 'Content-Type': 'application/octet-stream' }),
      body: new Uint8Array(merged.buffer),
    })
      .catch(() => {})
      .finally(() => {
        audioPushInFlight = Math.max(0, audioPushInFlight - 1);
      });
  };

  const ensureWebAudioGraph = () => {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    if (!audioCtx) {
      audioCtx = new Ctx();
      const srcNode = audioCtx.createMediaElementSource(castVideo);
      const scriptNode = audioCtx.createScriptProcessor(4096, 2, 1);
      const silentGain = audioCtx.createGain();
      silentGain.gain.value = 0;
      monitorGainNode = audioCtx.createGain();
      monitorGainNode.gain.value = mediaLocalAudioCheck.checked ? 1 : 0;

      srcNode.connect(scriptNode);
      scriptNode.connect(silentGain);
      silentGain.connect(audioCtx.destination);
      srcNode.connect(monitorGainNode);
      monitorGainNode.connect(audioCtx.destination);

      scriptNode.onaudioprocess = (ev) => {
        if (!mediaCastingActive || castVideo.paused || castVideo.ended) return;
        const inBuf = ev.inputBuffer;
        const chCount = inBuf.numberOfChannels;
        if (!chCount) return;
        const ch0 = inBuf.getChannelData(0);
        const ch1 = chCount > 1 ? inBuf.getChannelData(1) : null;
        const inRate = audioCtx.sampleRate || 48000;
        const step = inRate / TARGET_AUDIO_RATE;
        const outLen = Math.max(1, Math.floor(ch0.length / step));
        const pcm = new Int16Array(outLen);
        for (let i = 0; i < outLen; i += 1) {
          const idx = Math.min(ch0.length - 1, Math.floor(i * step));
          const mono = ch1 ? (ch0[idx] + ch1[idx]) * 0.5 : ch0[idx];
          const clamped = Math.max(-1, Math.min(1, mono));
          pcm[i] = clamped < 0 ? Math.round(clamped * 32768) : Math.round(clamped * 32767);
        }
        pcmBatchChunks.push(pcm);
        pcmBatchSamples += pcm.length;
        if (pcmBatchSamples >= 1920) {
          flushPcmBatch();
        }
      };
    }
    if (audioCtx.state === 'suspended') {
      void audioCtx.resume();
    }
  };

  const buildCanvasGpuFilter = () => {
    const parts = [];
    const br = Number(sliders.BRIGHTNESS.value || 100);
    const ct = Number(sliders.CONTRAST.value || 100);
    const sat = Number(sliders.SATURATION.value || 100);
    const cmRadio = form.querySelector('input[name="COLOR_MODE"]:checked');
    const cm = cmRadio ? cmRadio.value : 'rgb565';
    if (br !== 100) parts.push(`brightness(${br}%)`);
    if (ct !== 100) parts.push(`contrast(${ct}%)`);
    if (cm === 'gray') {
      parts.push('grayscale(100%)');
    } else if (sat !== 100) {
      parts.push(`saturate(${sat}%)`);
    }
    if (document.getElementById('INVERT').checked) {
      parts.push('invert(100%)');
    }
    return parts.length ? parts.join(' ') : 'none';
  };

  const encodeCanvasJpegBlob = () =>
    new Promise((resolve) => {
      castCanvas.toBlob((blob) => resolve(blob), 'image/jpeg', 0.76);
    });

  const captureAndPushVideoFrame = async () => {
    if (
      !mediaCastingActive ||
      castVideo.paused ||
      castVideo.ended ||
      videoEncodeBusy ||
      videoInFlightCount >= MAX_VIDEO_INFLIGHT
    ) {
      return;
    }
    const vw = castVideo.videoWidth;
    const vh = castVideo.videoHeight;
    if (!vw || !vh) return;
    syncLocalCanvasVisibility();

    const fitRadio = form.querySelector('input[name="FIT_MODE"]:checked');
    const fitMode = fitRadio ? fitRadio.value : 'contain';
    const rotRadio = form.querySelector('input[name="ROTATE"]:checked');
    const rotDeg = rotRadio ? Number(rotRadio.value) || 0 : 0;
    const isQuarterTurn = rotDeg === 90 || rotDeg === 270;
    const effW = isQuarterTurn ? vh : vw;
    const effH = isQuarterTurn ? vw : vh;

    /* 在 PC/手机浏览器 GPU 端一次性完成留边填充、旋转、缩放与亮度/对比度/饱和度/灰度/反相滤镜 */
    castCtx.filter = 'none';
    castCtx.fillStyle = document.getElementById('BG_COLOR').value || '#000000';
    castCtx.fillRect(0, 0, 320, 170);

    let boxW = 320;
    let boxH = 170;
    if (fitMode === 'cover') {
      const scale = Math.max(320 / effW, 170 / effH);
      boxW = effW * scale;
      boxH = effH * scale;
    } else if (fitMode !== 'stretch') {
      const scale = Math.min(320 / effW, 170 / effH);
      boxW = effW * scale;
      boxH = effH * scale;
    }

    const drawW = isQuarterTurn ? boxH : boxW;
    const drawH = isQuarterTurn ? boxW : boxH;
    castCtx.save();
    castCtx.filter = buildCanvasGpuFilter();
    castCtx.translate(160, 85);
    if (rotDeg) {
      castCtx.rotate((rotDeg * Math.PI) / 180);
    }
    castCtx.drawImage(castVideo, -drawW * 0.5, -drawH * 0.5, drawW, drawH);
    castCtx.restore();

    videoEncodeBusy = true;
    const jpegBlob = await encodeCanvasJpegBlob();
    videoEncodeBusy = false;
    if (!jpegBlob || !mediaCastingActive) return;

    clientFrameSeq += 1;
    const seq = clientFrameSeq;
    videoInFlightCount += 1;
    fetch('/push?pre_processed=1&fast=1', {
      method: 'POST',
      headers: getHeadersWithToken({
        'Content-Type': 'image/jpeg',
        'X-Stream-Session': streamSessionId,
        'X-Frame-Seq': String(seq),
      }),
      body: jpegBlob,
    })
      .catch(() => {})
      .finally(() => {
        videoInFlightCount = Math.max(0, videoInFlightCount - 1);
      });
  };

  const restartMediaFrameLoop = () => {
    clearInterval(mediaFrameTimer);
    mediaFrameTimer = null;
    if (!mediaCastingActive) return;
    if (castVideo.readyState >= 1 && !castVideo.videoWidth) return;
    const cap = Number(targetFpsInput.value) || 0;
    const fps = cap > 0 ? Math.min(60, Math.max(5, cap)) : 24;
    mediaFrameTimer = setInterval(() => {
      void captureAndPushVideoFrame();
    }, Math.round(1000 / fps));
  };

  const clearRemoteAudioBuffer = () => {
    pcmBatchChunks = [];
    pcmBatchSamples = 0;
    fetch('/api/audio', {
      method: 'POST',
      headers: getHeadersWithToken({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ clear: true }),
    }).catch(() => {});
  };

  const startMediaCast = async () => {
    if (!currentMediaName) return;
    try {
      ensureWebAudioGraph();
      mediaCastingActive = true;
      castVideo.loop = mediaLoopCheck.checked;
      await castVideo.play();
      restartMediaFrameLoop();
      syncMediaStatusText();
    } catch (err) {
      mediaCastingActive = false;
      syncMediaStatusText();
      showStatus(t('msg_media_err')(err.message), true);
    }
  };

  const pauseMediaCast = () => {
    castVideo.pause();
    clearInterval(mediaFrameTimer);
    mediaFrameTimer = null;
    clearRemoteAudioBuffer();
    syncMediaStatusText();
  };

  const stopMediaCast = (notify = false) => {
    mediaCastingActive = false;
    castVideo.pause();
    try {
      castVideo.currentTime = 0;
    } catch {
      /* 未就绪时忽略 */
    }
    clearInterval(mediaFrameTimer);
    mediaFrameTimer = null;
    clearRemoteAudioBuffer();
    updateMediaSeekUi();
    syncMediaStatusText();
    if (notify) showStatus(t('msg_media_stopped'));
  };

  const loadLocalMedia = async (file, autoPlay = true) => {
    if (!file) return;
    stopMediaCast(false);
    streamSessionId = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
    clientFrameSeq = 0;
    if (mediaObjectUrl) URL.revokeObjectURL(mediaObjectUrl);
    mediaObjectUrl = URL.createObjectURL(file);
    currentMediaName = file.name || 'media';
    castVideo.src = mediaObjectUrl;
    castVideo.loop = mediaLoopCheck.checked;
    mediaToggleBtn.disabled = false;
    mediaStopBtn.disabled = false;
    mediaSeek.disabled = false;
    syncMediaStatusText();
    if (autoPlay) {
      await startMediaCast();
    }
  };

  const uploadFile = async (file) => {
    if (!file) {
      showStatus(t('msg_pick_img'), true);
      return;
    }
    if (isMediaFile(file)) {
      await loadLocalMedia(file, true);
      return;
    }
    stopMediaCast(false);
    try {
      const fd = new FormData();
      fd.append('image', file);
      const prevKey = lastPreviewKey;
      const res = await fetchJson('/push', {
        method: 'POST',
        headers: getHeadersWithToken(),
        body: fd,
      });
      showStatus(t('msg_push_ok')(res.width, res.height, res.frame_bytes, res.process_ms ?? '--'));
      await refreshHealth();
      if (lastPreviewKey === prevKey) refreshPreviewImage(lastPreviewKey);
    } catch (err) {
      showStatus(t('msg_push_err')(err.message), true);
    }
  };

  /* 调整色彩、缩放、滑块或勾选框时 120ms 防抖实时刷新设备屏幕（不频繁写盘磨损 SD 卡） */
  const scheduleLivePreviewApply = () => {
    clearTimeout(liveApplyTimer);
    liveApplyTimer = setTimeout(async () => {
      if (!form.checkValidity()) return;
      try {
        const prevKey = lastPreviewKey;
        await fetchJson('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(collectConfigPayload(false)),
        });
        await refreshHealth();
        if (lastPreviewKey === prevKey) refreshPreviewImage(lastPreviewKey);
      } catch {
        /* 实时预览静默忽略瞬时网络波动 */
      }
    }, 120);
  };

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    form.querySelectorAll('input').forEach((el) => applyCustomConstraint(el));
    if (!form.checkValidity()) {
      form.reportValidity();
      const firstInvalid = form.querySelector(':invalid');
      if (firstInvalid) firstInvalid.focus();
      showStatus(t('msg_form_invalid'), true);
      return;
    }

    const saveBtn = document.getElementById('btn-save-config');
    saveBtn.disabled = true;
    try {
      const res = await fetchJson('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(collectConfigPayload(true)),
      });
      fillConfigForm(res.config);
      showStatus(t('msg_save_ok'));
      await refreshHealth();
    } catch (err) {
      showStatus(t('msg_save_err')(err.message), true);
    } finally {
      saveBtn.disabled = false;
    }
  });

  for (const [key, slider] of Object.entries(sliders)) {
    slider.addEventListener('input', () => {
      sliderLabels[key].textContent = slider.value;
      updateSliderFallbackProgress(slider);
      scheduleLivePreviewApply();
    });
  }

  form.querySelectorAll('input[type="radio"], input[type="checkbox"], input[type="color"]').forEach((el) => {
    if (el === audioMuteCheck) return;
    el.addEventListener('change', scheduleLivePreviewApply);
  });

  const scheduleAudioSettingsApply = () => {
    clearTimeout(audioApplyTimer);
    audioApplyTimer = setTimeout(() => {
      fetchJson('/api/audio', {
        method: 'POST',
        headers: getHeadersWithToken({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          volume: Number(audioVolSlider.value || 100),
          muted: audioMuteCheck.checked,
          save: false,
        }),
      }).catch(() => {});
    }, 80);
  };

  audioVolSlider.addEventListener('input', () => {
    audioVolLabel.textContent = audioVolSlider.value;
    audioVolSlider.setAttribute('aria-valuetext', `${audioVolSlider.value}%`);
    updateSliderFallbackProgress(audioVolSlider);
    scheduleAudioSettingsApply();
  });

  audioMuteCheck.addEventListener('change', scheduleAudioSettingsApply);

  fpsChips.forEach((chip) => {
    chip.addEventListener('click', () => {
      targetFpsInput.value = chip.dataset.fps;
      syncFpsChipsHighlight(chip.dataset.fps);
      syncFieldAria(targetFpsInput, false);
      restartMediaFrameLoop();
      scheduleLivePreviewApply();
    });
  });

  targetFpsInput.addEventListener('input', () => {
    syncFpsChipsHighlight(targetFpsInput.value);
    applyCustomConstraint(targetFpsInput);
    if (targetFpsInput.validity.valid) {
      restartMediaFrameLoop();
      scheduleLivePreviewApply();
    }
  });

  document.getElementById('btn-reset-tone').addEventListener('click', () => {
    sliders.BRIGHTNESS.value = '100';
    sliders.CONTRAST.value = '100';
    sliders.SATURATION.value = '100';
    sliders.THRESHOLD.value = '128';
    document.getElementById('INVERT').checked = false;
    for (const [k, s] of Object.entries(sliders)) {
      sliderLabels[k].textContent = s.value;
      updateSliderFallbackProgress(s);
    }
    scheduleLivePreviewApply();
    showStatus(t('msg_reset_tone'));
  });

  pixelModeBtn.addEventListener('click', () => {
    const nowPixel = !previewImg.classList.contains('pixelated');
    previewImg.classList.toggle('pixelated', nowPixel);
    castCanvas.classList.toggle('pixelated', nowPixel);
    pixelModeBtn.setAttribute('aria-pressed', nowPixel ? 'true' : 'false');
    pixelModeBtn.textContent = nowPixel ? t('pixel_sharp') : t('pixel_smooth');
  });

  toggleTokenBtn.addEventListener('click', () => {
    const showing = tokenInput.type === 'text';
    tokenInput.type = showing ? 'password' : 'text';
    toggleTokenBtn.setAttribute('aria-pressed', showing ? 'false' : 'true');
    toggleTokenBtn.textContent = showing ? t('btn_show') : t('btn_hide');
  });

  document.getElementById('btn-open-logs').addEventListener('click', async () => {
    try {
      const snap = await fetchJson('/api/logs?tail=250', { headers: getHeadersWithToken() });
      const lines = snap.lines || [];
      if (!lines.length) {
        showStatus(t('msg_logs_empty'));
        return;
      }
      const txt = `# path=${snap.path} enabled=${snap.enabled} size=${snap.size_bytes}B\n` + lines.join('\n') + '\n';
      const url = URL.createObjectURL(new Blob([txt], { type: 'text/plain;charset=utf-8' }));
      window.open(url, '_blank', 'noopener');
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch (err) {
      showStatus(err.message, true);
    }
  });

  document.getElementById('btn-clear-logs').addEventListener('click', async () => {
    try {
      await fetchJson('/api/logs', {
        method: 'POST',
        headers: getHeadersWithToken({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ action: 'clear' }),
      });
      showStatus(t('msg_logs_cleared'));
    } catch (err) {
      showStatus(err.message, true);
    }
  });

  toggleLangBtn.addEventListener('click', async () => {
    const targetLang = currentLang === 'en' ? 'zh' : 'en';
    applyLanguage(targetLang);
    const res = await runControl('toggle_lang');
    if (res?.ok) {
      showStatus(t('msg_lang_switched'));
    }
  });

  document.getElementById('btn-prev-pattern').addEventListener('click', () => triggerPattern('prev'));
  document.getElementById('btn-next-pattern').addEventListener('click', () => triggerPattern('next'));
  document.getElementById('btn-toggle-pause').addEventListener('click', () =>
    runControl(currentPaused ? 'resume' : 'pause')
  );
  document.getElementById('btn-waiting').addEventListener('click', () => {
    stopMediaCast(false);
    void runControl('waiting');
  });
  document.getElementById('btn-refresh-status').addEventListener('click', refreshHealth);
  document.getElementById('btn-upload-push').addEventListener('click', () => uploadFile(fileInput.files?.[0]));
  fileInput.addEventListener('change', () => {
    if (fileInput.files?.[0]) void uploadFile(fileInput.files[0]);
  });

  mediaFileInput.addEventListener('change', () => {
    if (mediaFileInput.files?.[0]) void loadLocalMedia(mediaFileInput.files[0], true);
  });
  mediaToggleBtn.addEventListener('click', () => {
    if (!currentMediaName) return;
    if (mediaCastingActive && !castVideo.paused && !castVideo.ended) {
      pauseMediaCast();
    } else {
      void startMediaCast();
    }
  });
  mediaStopBtn.addEventListener('click', () => stopMediaCast(true));
  mediaLoopCheck.addEventListener('change', () => {
    castVideo.loop = mediaLoopCheck.checked;
  });
  mediaLocalAudioCheck.addEventListener('change', () => {
    if (monitorGainNode && audioCtx) {
      monitorGainNode.gain.value = mediaLocalAudioCheck.checked ? 1 : 0;
    }
  });
  mediaSeek.addEventListener('input', () => {
    const dur = Number.isFinite(castVideo.duration) && castVideo.duration > 0 ? castVideo.duration : 0;
    if (dur > 0) {
      const targetSec = (Number(mediaSeek.value) / 1000) * dur;
      castVideo.currentTime = targetSec;
      clearRemoteAudioBuffer();
      updateMediaSeekUi();
    }
  });
  castVideo.addEventListener('loadedmetadata', updateMediaSeekUi);
  castVideo.addEventListener('timeupdate', updateMediaSeekUi);
  castVideo.addEventListener('ended', () => {
    if (!castVideo.loop) {
      clearInterval(mediaFrameTimer);
      mediaFrameTimer = null;
      flushPcmBatch();
      syncMediaStatusText();
    }
  });
  mediaZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    mediaZone.classList.add('drag-over');
  });
  mediaZone.addEventListener('dragleave', () => mediaZone.classList.remove('drag-over'));
  mediaZone.addEventListener('drop', (e) => {
    e.preventDefault();
    mediaZone.classList.remove('drag-over');
    const dropped = e.dataTransfer?.files?.[0];
    if (dropped) void loadLocalMedia(dropped, true);
  });

  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
  });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    const dropped = e.dataTransfer?.files?.[0];
    if (dropped) void uploadFile(dropped);
  });

  /* 支持页面任意位置 Ctrl+V 粘贴截图直接推上设备屏幕 */
  document.addEventListener('paste', (e) => {
    const items = e.clipboardData?.items || [];
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        const blob = item.getAsFile();
        if (blob) {
          e.preventDefault();
          void uploadFile(blob);
          break;
        }
      }
    }
  });

  document.getElementById('btn-copy-curl').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(curlBox.textContent);
      showStatus(t('msg_copy_ok'));
    } catch {
      showStatus(t('msg_copy_err'), true);
    }
  });

  const boot = async () => {
    initFormAccessibility();
    try {
      const [cfgRes, patRes] = await Promise.all([fetchJson('/api/config'), fetchJson('/api/patterns')]);
      patternCatalog = patRes.patterns || [];
      fillConfigForm(cfgRes.config);
      renderPatternButtons(patternCatalog);
      await refreshHealth();
    } catch (err) {
      showStatus(t('msg_init_err')(err.message), true);
    }

    setInterval(() => {
      if (document.visibilityState === 'visible') {
        void refreshHealth();
      }
    }, 1000);
  };

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') void refreshHealth();
  });

  void boot();
})();
