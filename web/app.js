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
      btn_save_config: '保存当前参数到 .env',
      api_heading: '任意设备推送命令示例（HTTP POST）',
      btn_copy_curl: '复制示例',
      curl_comment_1: '# 1. 推送任意 PNG/JPEG 图片到设备屏幕',
      curl_comment_2: '# 2. 表单上传或指定缩放/抖动模式',
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
      btn_save_config: 'Save Settings to .env',
      api_heading: 'Cross-Device Push Examples (HTTP POST)',
      btn_copy_curl: 'Copy',
      curl_comment_1: '# 1. Push any PNG/JPEG image to the device screen',
      curl_comment_2: '# 2. Multipart upload with fit & dither overrides',
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
    const tokFlag = tokenInput.value.trim() ? ` -H "X-Cast-Token: ${tokenInput.value.trim()}"` : '';
    curlBox.textContent =
      `${t('curl_comment_1')}\n` +
      `curl -X POST "${targetOrigin}/push"${tokFlag} -H "Content-Type: image/png" --data-binary @screen.png\n` +
      `${t('curl_comment_2')}\n` +
      `curl -X POST "${targetOrigin}/push?fit_mode=cover&color_mode=rgb565_dither"${tokFlag} -F "image=@photo.jpg"`;
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
        lastPreviewKey = key;
        refreshPreviewImage(key);
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

  const uploadFile = async (file) => {
    if (!file) {
      showStatus(t('msg_pick_img'), true);
      return;
    }
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
    el.addEventListener('change', scheduleLivePreviewApply);
  });

  fpsChips.forEach((chip) => {
    chip.addEventListener('click', () => {
      targetFpsInput.value = chip.dataset.fps;
      syncFpsChipsHighlight(chip.dataset.fps);
      syncFieldAria(targetFpsInput, false);
      scheduleLivePreviewApply();
    });
  });

  targetFpsInput.addEventListener('input', () => {
    syncFpsChipsHighlight(targetFpsInput.value);
    applyCustomConstraint(targetFpsInput);
    if (targetFpsInput.validity.valid) {
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
    pixelModeBtn.setAttribute('aria-pressed', nowPixel ? 'true' : 'false');
    pixelModeBtn.textContent = nowPixel ? t('pixel_sharp') : t('pixel_smooth');
  });

  toggleTokenBtn.addEventListener('click', () => {
    const showing = tokenInput.type === 'text';
    tokenInput.type = showing ? 'password' : 'text';
    toggleTokenBtn.setAttribute('aria-pressed', showing ? 'false' : 'true');
    toggleTokenBtn.textContent = showing ? t('btn_show') : t('btn_hide');
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
  document.getElementById('btn-waiting').addEventListener('click', () => runControl('waiting'));
  document.getElementById('btn-refresh-status').addEventListener('click', refreshHealth);
  document.getElementById('btn-upload-push').addEventListener('click', () => uploadFile(fileInput.files?.[0]));
  fileInput.addEventListener('change', () => {
    if (fileInput.files?.[0]) void uploadFile(fileInput.files[0]);
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
    }, 600);
  };

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') void refreshHealth();
  });

  void boot();
})();
