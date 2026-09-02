/* CD2 上传触发 115 STRM：Vue 联邦远程入口。 */

const currentImports = {};
const moduleCache = {};

function flattenModule(module, name) {
  /* 将联邦共享模块整理为 Vue 组件代码可直接使用的对象。 */
  if (typeof module?.default === "function") {
    Object.keys(module).forEach((key) => {
      if (key !== "default") module.default[key] = module[key];
    });
    return module.default;
  }
  if (module?.default) return Object.assign({}, module.default, module);
  return module;
}

async function importShared(name) {
  /* 优先使用 MoviePilot 宿主提供的 Vue，避免重复加载运行时。 */
  if (moduleCache[name]) return moduleCache[name];
  const runtime = globalThis?.__federation_shared__?.default?.[name];
  if (runtime) {
    const versions = Object.keys(runtime);
    if (versions.length) {
      const shared = runtime[versions[0]];
      const module = await (await shared.get())();
      moduleCache[name] = flattenModule(module, name);
      return moduleCache[name];
    }
  }
  currentImports[name] ??= import(name);
  moduleCache[name] = flattenModule(await currentImports[name], name);
  return moduleCache[name];
}

function clone(value) {
  /* 深复制配置，避免编辑表单直接修改宿主传入对象。 */
  if (value === undefined || value === null) return {};
  return JSON.parse(JSON.stringify(value));
}

function injectStyle() {
  /* 注入组件局部样式，不依赖额外 CSS 文件。 */
  if (typeof document === "undefined" || document.getElementById("cd2-upload-strm-trigger-style")) return;
  const style = document.createElement("style");
  style.id = "cd2-upload-strm-trigger-style";
  style.textContent = `
    .cd2-trigger-config,.cd2-trigger-page{padding:16px;color:var(--v-theme-on-surface,#e5e7eb)}
    .cd2-trigger-card{border:1px solid rgba(127,127,127,.25);border-radius:10px;padding:16px;margin-bottom:14px;background:rgba(127,127,127,.04)}
    .cd2-trigger-title{font-size:18px;font-weight:600;margin-bottom:6px}.cd2-trigger-subtitle{opacity:.7;font-size:13px;margin-bottom:16px}
    .cd2-trigger-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
    .cd2-trigger-field{display:flex;flex-direction:column;gap:6px;font-size:13px}.cd2-trigger-field input,.cd2-trigger-field textarea{box-sizing:border-box;width:100%;border:1px solid rgba(127,127,127,.4);border-radius:6px;padding:9px;background:transparent;color:inherit;font:inherit}
    .cd2-trigger-field textarea{min-height:78px;resize:vertical}.cd2-trigger-check{display:flex;gap:8px;align-items:center;margin:10px 0;font-size:14px}
    .cd2-trigger-actions{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;margin-top:14px}.cd2-trigger-btn,.cd2-trigger-btn:visited,.cd2-trigger-btn:hover,.cd2-trigger-btn:focus{color:#fff !important;-webkit-text-fill-color:#fff !important}.cd2-trigger-btn{appearance:none;border:0;border-radius:6px;padding:9px 14px;cursor:pointer;background:#424242;font:inherit;line-height:1.25}.cd2-trigger-btn.primary{background:#1976d2}.cd2-trigger-btn.danger{background:#b3261e}.cd2-trigger-btn:disabled{opacity:.55;cursor:default}
    .cd2-trigger-rule{border:1px solid rgba(127,127,127,.25);border-radius:8px;padding:12px;margin:10px 0}.cd2-trigger-rule-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;font-weight:600}.cd2-trigger-hint{font-size:12px;opacity:.7;line-height:1.6;margin-top:8px}.cd2-trigger-message{border-radius:6px;padding:10px;margin-top:12px;background:rgba(25,118,210,.12)}.cd2-trigger-error{background:rgba(211,47,47,.15)}
    .cd2-trigger-stat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}.cd2-trigger-stat{padding:12px;border-radius:8px;background:rgba(127,127,127,.08)}.cd2-trigger-stat strong{display:block;font-size:20px;margin-top:4px}.cd2-trigger-muted{opacity:.68}.cd2-trigger-path{margin:8px 0;word-break:break-all;font-family:monospace;font-size:12px}.cd2-trigger-row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:8px 0}.cd2-trigger-pill{display:inline-flex;border-radius:999px;padding:4px 9px;font-size:12px;background:rgba(127,127,127,.16)}.cd2-trigger-pill.ok{background:rgba(46,125,50,.2)}.cd2-trigger-pill.bad{background:rgba(211,47,47,.2)}
    .cd2-trigger-help-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px}.cd2-trigger-help-item{padding:12px;border-radius:8px;background:rgba(127,127,127,.08);line-height:1.65}.cd2-trigger-help-item strong{display:block;margin-bottom:4px}.cd2-trigger-help-code{display:inline-block;padding:2px 5px;border-radius:4px;background:rgba(127,127,127,.14);font-family:monospace;word-break:break-all}.cd2-trigger-help-flow{font-size:13px;line-height:1.8}
  `;
  document.head.appendChild(style);
}

function apiResult(response) {
  /* 兼容 MoviePilot API 客户端可能返回的单层或嵌套响应。 */
  let value = response;
  if (value?.data?.success !== undefined) value = value.data;
  return value;
}

function createUsageView(h, onBack, onClose) {
  /* 插件内置使用说明，避免用户反复退出页面查找配置含义。 */
  return h("div", { class: "cd2-trigger-page" }, [
    h("div", { class: "cd2-trigger-title" }, "使用说明"),
    h("div", { class: "cd2-trigger-subtitle" }, "CD2 上传完成后，媒体文件生成 STRM，字幕文件下载到同一媒体目录。"),
    h("div", { class: "cd2-trigger-card" }, [
      h("strong", "处理流程"),
      h("div", { class: "cd2-trigger-help-flow" }, "CD2 上传完成 → PushMessage/文件变更消息或快速补扫捕获 → 命中目录规则 → 媒体文件调用 115 STRM 助手生成 STRM → 本插件按批次调用 Emby 刷新；字幕文件由本插件从 CD2 下载到本地。插件启动后的第一次成功扫描只建立状态基线，已存在的完成任务不会补处理。"),
    ]),
    h("div", { class: "cd2-trigger-card" }, [
      h("strong", "网页/公网远程上传"),
      h("div", { class: "cd2-trigger-help-flow" }, "通过 CD2 网页、反向代理或公网 IPv6 上传属于 RemoteUpload，不要求上传客户端位于局域网。插件会记录 operatorType=RemoteUpload，并同时监听上传状态和文件系统 CREATE/RENAME 事件；上传数量变化后还会执行多次快速补扫。"),
      h("div", { class: "cd2-trigger-hint" }, "CD2 API 根目录必须填写令牌创建时的 RootDirectory，例如令牌 RootDirectory=/115 就填写 /115。"),
    ]),
    h("div", { class: "cd2-trigger-card" }, [
      h("strong", "目录映射三段的实际用途"),
      h("div", { class: "cd2-trigger-help-grid" }, [
        h("div", { class: "cd2-trigger-help-item" }, [h("strong", "CD2 目标目录前缀"), h("span", "CD2 任务的 destPath 起始目录，只监控这个目录及其子目录。/CloudNAS/115/影视库、/115/影视库、/影视库会自动按同一目录处理。")]),
        h("div", { class: "cd2-trigger-help-item" }, [h("strong", "115 网盘路径前缀"), h("span", "对应 115 网盘中的媒体库根目录，用来组成 STRM 的 pan_path。例如 /影视库。")]),
        h("div", { class: "cd2-trigger-help-item" }, [h("strong", "本地 STRM 根目录"), h("span", "MoviePilot/Emby 实际能看到的本地媒体目录。STRM 和字幕会按相同相对目录落在这里。")]),
      ]),
      h("div", { class: "cd2-trigger-hint" }, "示例：/CloudNAS/115/影视库/电影/a.mkv、/115/影视库/电影/a.mkv 或 /影视库/电影/a.mkv → 115 /影视库/电影/a.mkv → 本地 /media/MP_movieDB/影视库/电影下的对应 STRM 文件。"),
    ]),
    h("div", { class: "cd2-trigger-card" }, [
      h("strong", "媒体、字幕和附加动作"),
      h("div", { class: "cd2-trigger-help-grid" }, [
        h("div", { class: "cd2-trigger-help-item" }, [h("strong", "媒体扩展名"), h("span", "命中后提交给 115 STRM 助手生成 STRM，不下载原媒体文件。")]),
        h("div", { class: "cd2-trigger-help-item" }, [h("strong", "字幕扩展名"), h("span", "默认 srt、ssa、ass、vtt、sub、idx、sup；由本插件直接从 CD2 下载，不生成 STRM。")]),
        h("div", { class: "cd2-trigger-help-item" }, [h("strong", "字幕下载间隔"), h("span", "单线程串行下载，控制每次字幕下载请求的最小间隔；设置为 0 表示不额外等待。")]),
        h("div", { class: "cd2-trigger-help-item" }, [h("strong", "字幕稳定等待"), h("span", "字幕事件入队后先等待，再连续读取两次 CD2 文件大小；大小稳定后才开始下载，避免远程上传尚未结束。")]),
      ]),
      h("div", { class: "cd2-trigger-hint" }, "“自动下载媒体元数据”是 115 STRM 助手按自身 user_download_mediaext 配置下载 .nfo、图片等文件的开关，不等于本插件的字幕下载；本插件的字幕任务不会把这个开关传给 115 助手。"),
    ]),
    h("div", { class: "cd2-trigger-card" }, [
      h("strong", "四个生成后选项由谁执行"),
      h("div", { class: "cd2-trigger-help-flow" }, "“自动刮削元数据”由 115 STRM 助手调用 MoviePilot 的元数据刮削链路执行，不是 Emby MediaInfoKeeper；“刷新媒体服务器”由本插件调用 MoviePilot 已配置的 Emby API，并在每批 STRM 生成完成后每个 Emby 只请求一次；“自动下载媒体元数据”由 115 STRM 助手的 MediaInfoDownloader 按自身扩展名配置执行。本插件只把媒体任务参数交给 115 助手，并负责字幕下载和批次 Emby 刷新。“发送生成结果通知”由本插件调用 MoviePilot 的 post_message，使用 MP 已配置的通知渠道（例如 Telegram），通知的是 STRM 批次结果，不会逐个发送字幕通知。"),
    ]),
    h("div", { class: "cd2-trigger-actions" }, [
      h("button", { type: "button", class: "cd2-trigger-btn primary", onClick: onBack }, "返回"),
      h("button", { type: "button", class: "cd2-trigger-btn", onClick: onClose }, "关闭"),
    ]),
  ]);
}

async function createConfigModule() {
  /* 创建插件配置组件。 */
  const vue = await importShared("vue");
  const { defineComponent, h, onMounted, reactive, ref } = vue;
  injectStyle();

  const Config = defineComponent({
    name: "Cd2UploadStrmTriggerConfig",
    props: {
      initialConfig: { type: Object, default: () => ({}) },
      api: { type: Object, default: () => ({}) },
    },
    emits: ["save", "close", "switch"],
    setup(props, { emit }) {
      /* 配置表单的默认值。 */
      const defaults = {
        enabled: false,
        cd2_endpoint: "http://172.17.0.1:19798",
        cd2_token: "",
        cd2_api_root: "/115",
        moviepilot_url: "http://127.0.0.1:3001",
        moviepilot_api_key: "",
        rules: [],
        poll_interval: 5,
        batch_window: 5,
        page_size: 200,
        include_extensions: "mkv,mp4,ts,avi,mov,m4v,wmv,flv,m2ts,iso,rmvb,webm,mpeg,mpg,3gp,asf,tp,f4v",
        subtitle_extensions: "srt,ssa,ass,vtt,sub,idx,sup",
        subtitle_interval: 3,
        subtitle_stability_delay: 3,
        scrape_metadata: false,
        media_server_refresh: false,
        auto_download_mediainfo: false,
        notify: false,
      };
      const config = reactive({ ...defaults, ...clone(props.initialConfig) });
      config.rules = Array.isArray(config.rules) ? config.rules : [];
      const message = ref("");
      const messageError = ref(false);
      const testing = ref(false);
      const showHelp = ref(false);

      function setMessage(text, error = false) {
        /* 更新配置页面提示信息。 */
        message.value = text || "";
        messageError.value = error;
      }

      function addRule() {
        /* 添加一条 CD2 到 115 的目录映射规则。 */
        config.rules.push({ enabled: true, name: "", cd2_prefix: "/影视库", pan_prefix: "/影视库", local_path: "/media/MP_movieDB/影视库" });
      }

      function removeRule(index) {
        /* 删除指定的目录映射规则。 */
        config.rules.splice(index, 1);
      }

      function field(label, key, placeholder = "", secret = false) {
        /* 创建普通文本配置控件。 */
        return h("label", { class: "cd2-trigger-field" }, [
          h("span", label),
          h("input", {
            type: secret ? "password" : "text",
            value: config[key] ?? "",
            placeholder,
            autocomplete: secret ? "new-password" : "off",
            onInput: (event) => { config[key] = event.target.value; },
          }),
        ]);
      }

      function numberField(label, key, min, max, step = 1) {
        /* 创建数字配置控件。 */
        return h("label", { class: "cd2-trigger-field" }, [
          h("span", label),
          h("input", {
            type: "number", min, max, step, value: config[key],
            onInput: (event) => { config[key] = Number(event.target.value); },
          }),
        ]);
      }

      function checkField(label, key) {
        /* 创建布尔配置控件。 */
        return h("label", { class: "cd2-trigger-check" }, [
          h("input", { type: "checkbox", checked: !!config[key], onChange: (event) => { config[key] = event.target.checked; } }),
          h("span", label),
        ]);
      }

      async function testConnection() {
        /* 调用后端测试 CD2 和 MoviePilot API。 */
        testing.value = true;
        setMessage("");
        try {
          const response = apiResult(await props.api.post("/plugin/Cd2UploadStrmTrigger/test", clone(config)));
          setMessage(response?.success ? (response.message || "连接测试成功") : (response?.message || "连接测试失败"), !response?.success);
        } catch (error) {
          setMessage(error?.message || "连接测试失败", true);
        } finally {
          testing.value = false;
        }
      }

      function save() {
        /* 将配置提交给 MoviePilot 宿主保存。 */
        emit("save", clone(config));
      }

      function closeHelp() {
        /* 返回配置表单。 */
        showHelp.value = false;
      }

      onMounted(() => {
        /* 确保旧版本配置缺少规则数组时仍可编辑。 */
        if (!Array.isArray(config.rules)) config.rules = [];
      });

      return () => showHelp.value
        ? createUsageView(h, closeHelp, () => emit("close"))
        : h("form", { class: "cd2-trigger-config", onSubmit: (event) => { event.preventDefault(); save(); } }, [
        h("div", { class: "cd2-trigger-title" }, "CD2 上传触发 115 STRM"),
        h("div", { class: "cd2-trigger-subtitle" }, "监听 CloudDrive2 上传完成状态：媒体生成 STRM，字幕按限速下载。"),
        h("div", { class: "cd2-trigger-card" }, [
          checkField("启用插件", "enabled"),
          h("div", { class: "cd2-trigger-grid" }, [
            field("CD2 gRPC 地址", "cd2_endpoint", "http://172.17.0.1:19798"),
            field("CD2 API Token", "cd2_token", "仅填写 Token，不要写 Bearer", true),
            field("CD2 API 根目录（Token RootDirectory）", "cd2_api_root", "/115"),
            field("MoviePilot 地址", "moviepilot_url", "http://127.0.0.1:3001"),
            field("MoviePilot API Key（可选）", "moviepilot_api_key", "留空则使用系统 API_TOKEN", true),
          ]),
          h("div", { class: "cd2-trigger-hint" }, "CD2 Token 需要开启“获取传输任务”和“接收推送消息”权限；要下载字幕，还需开启文件读取里的“列出文件、读取文件、查看属性”。API 根目录必须与令牌 RootDirectory 一致，例如令牌为 /115 就填写 /115；插件会自动兼容 /CloudNAS/115、/115、/影视库 三种路径。MoviePilot API Key 留空时，插件会尝试使用当前实例的系统 API_TOKEN。"),
        ]),
        h("div", { class: "cd2-trigger-card" }, [
          h("div", { class: "cd2-trigger-row" }, [h("strong", "目录映射规则"), h("button", { type: "button", class: "cd2-trigger-btn", onClick: addRule }, "添加规则")]),
          h("div", { class: "cd2-trigger-hint" }, "CD2 前缀负责监控范围；网页/公网远程上传可能使用 /115 或 /影视库，插件会自动归一化，不要求你把 /CloudNAS/115 改成其他写法。115 前缀负责生成 STRM 的网盘路径；本地根目录是 MP/Emby 读取 STRM 和字幕的位置。匹配采用目录边界，不会把 /电影2 误判为 /电影。"),
          ...config.rules.map((rule, index) => h("div", { class: "cd2-trigger-rule", key: index }, [
            h("div", { class: "cd2-trigger-rule-head" }, [h("span", `规则 ${index + 1}`), h("button", { type: "button", class: "cd2-trigger-btn danger", onClick: () => removeRule(index) }, "删除")]),
            h("label", { class: "cd2-trigger-check" }, [h("input", { type: "checkbox", checked: !!rule.enabled, onChange: (event) => { rule.enabled = event.target.checked; } }), h("span", "启用此规则")]),
            h("div", { class: "cd2-trigger-grid" }, [
              h("label", { class: "cd2-trigger-field" }, [h("span", "规则名称"), h("input", { value: rule.name || "", onInput: (event) => { rule.name = event.target.value; } })]),
              h("label", { class: "cd2-trigger-field" }, [h("span", "CD2 目标目录前缀（挂载/源/API 均可）"), h("input", { value: rule.cd2_prefix || "", placeholder: "/影视库", onInput: (event) => { rule.cd2_prefix = event.target.value; } })]),
              h("label", { class: "cd2-trigger-field" }, [h("span", "115 网盘路径前缀"), h("input", { value: rule.pan_prefix || "", placeholder: "/影视库", onInput: (event) => { rule.pan_prefix = event.target.value; } })]),
              h("label", { class: "cd2-trigger-field" }, [h("span", "本地 STRM 根目录"), h("input", { value: rule.local_path || "", placeholder: "/media/MP_movieDB/影视库", onInput: (event) => { rule.local_path = event.target.value; } })]),
            ]),
          ])),
          config.rules.length === 0 ? h("div", { class: "cd2-trigger-muted" }, "还没有规则，请添加至少一条目录映射。") : null,
        ]),
        h("div", { class: "cd2-trigger-card" }, [
          h("div", { class: "cd2-trigger-grid" }, [
            numberField("轮询间隔（秒）", "poll_interval", 2, 60),
            numberField("批处理等待（秒）", "batch_window", 0, 120),
            numberField("每页任务数", "page_size", 20, 1000),
            field("媒体扩展名（逗号分隔）", "include_extensions", "mkv,mp4,ts"),
            field("字幕扩展名（下载，逗号分隔）", "subtitle_extensions", "srt,ssa,ass,vtt,sub,idx,sup"),
            numberField("字幕下载间隔（秒）", "subtitle_interval", 0, 60, 0.5),
            numberField("字幕稳定等待（秒）", "subtitle_stability_delay", 0, 60, 0.5),
          ]),
          checkField("由 115 STRM 助手刮削元数据", "scrape_metadata"),
          checkField("由本插件刷新 Emby（每批一次）", "media_server_refresh"),
          checkField("由 115 STRM 助手下载 .nfo/.jpg 等媒体元数据", "auto_download_mediainfo"),
          checkField("发送 STRM 生成结果通知（使用 MoviePilot 通知渠道）", "notify"),
          h("div", { class: "cd2-trigger-hint" }, "启动后的第一次成功扫描固定只建立基线，已有完成任务不会处理；后续新完成任务才会触发。PushMessage 优先，轮询作断线兜底；STRM 最多 100 个一批提交；开启 Emby 刷新后，115 STRM 生成成功的每一批向每个已配置 Emby 发送一次 Library/Refresh 请求，字幕单线程按间隔下载。"),
        ]),
        message.value ? h("div", { class: `cd2-trigger-message${messageError.value ? " cd2-trigger-error" : ""}` }, message.value) : null,
        h("div", { class: "cd2-trigger-actions" }, [
          h("button", { type: "button", class: "cd2-trigger-btn", onClick: () => { showHelp.value = true; } }, "使用说明"),
          h("button", { type: "button", class: "cd2-trigger-btn", disabled: testing.value, onClick: testConnection }, testing.value ? "测试中…" : "测试连接"),
          h("button", { type: "submit", class: "cd2-trigger-btn primary" }, "保存配置"),
          h("button", { type: "button", class: "cd2-trigger-btn", onClick: () => emit("close") }, "关闭"),
        ]),
      ]);
    },
  });
  return () => Config;
}

async function createPageModule() {
  /* 创建插件状态页面组件。 */
  const vue = await importShared("vue");
  const { defineComponent, h, onMounted, onUnmounted, ref } = vue;
  injectStyle();

  const Page = defineComponent({
    name: "Cd2UploadStrmTriggerPage",
    props: {
      api: { type: Object, default: () => ({}) },
      pluginId: { type: String, default: "Cd2UploadStrmTrigger" },
      initialConfig: { type: Object, default: () => ({}) },
    },
    emits: ["close", "switch"],
    setup(props, { emit }) {
      /* 管理状态页的数据和按钮状态。 */
      const status = ref({});
      const loading = ref(false);
      const triggering = ref(false);
      const message = ref("");
      const showHelp = ref(false);
      let timer = null;

      async function loadStatus() {
        /* 从后端读取监听器状态。 */
        loading.value = true;
        try {
          const response = apiResult(await props.api.get(`/plugin/${props.pluginId || "Cd2UploadStrmTrigger"}/status`));
          status.value = response?.data || response || {};
        } catch (error) {
          message.value = error?.message || "读取状态失败";
        } finally {
          loading.value = false;
        }
      }

      async function trigger() {
        /* 请求后台立即检查一次 CD2 上传任务。 */
        triggering.value = true;
        try {
          const response = apiResult(await props.api.post(`/plugin/${props.pluginId || "Cd2UploadStrmTrigger"}/trigger`, {}));
          message.value = response?.message || "已请求检查";
          await loadStatus();
        } catch (error) {
          message.value = error?.message || "触发失败";
        } finally {
          triggering.value = false;
        }
      }

      function stat(label, value) {
        /* 创建状态统计卡片。 */
        return h("div", { class: "cd2-trigger-stat" }, [h("span", { class: "cd2-trigger-muted" }, label), h("strong", String(value ?? 0))]);
      }

      function closeHelp() {
        /* 返回状态页。 */
        showHelp.value = false;
      }

      onMounted(() => {
        loadStatus();
        timer = setInterval(loadStatus, 10000);
      });
      onUnmounted(() => { if (timer) clearInterval(timer); });

      return () => {
        if (showHelp.value) return createUsageView(h, closeHelp, () => emit("close"));
        const last = status.value.last_trigger || {};
        const connected = !!status.value.connected;
        return h("div", { class: "cd2-trigger-page" }, [
          h("div", { class: "cd2-trigger-title" }, "CD2 上传触发 115 STRM"),
          h("div", { class: "cd2-trigger-subtitle" }, "后台监听状态与最近一次 STRM 生成结果"),
          h("div", { class: "cd2-trigger-card" }, [
            h("div", { class: "cd2-trigger-row" }, [
              h("span", { class: `cd2-trigger-pill ${connected ? "ok" : "bad"}` }, connected ? "CD2 已连接" : "CD2 未连接"),
              h("span", { class: `cd2-trigger-pill ${status.value.running ? "ok" : "bad"}` }, status.value.running ? "监听运行中" : "监听未运行"),
              h("span", { class: "cd2-trigger-muted" }, status.value.last_poll_at ? `最近轮询：${status.value.last_poll_at}` : "尚未轮询"),
            ]),
            h("div", { class: "cd2-trigger-stat-grid" }, [
              stat("CD2 当前任务", status.value.upload_count),
              stat("本轮列表任务", status.value.task_count),
              stat("命中规则", status.value.matched_count),
              stat("待生成 STRM", status.value.strm_pending_count ?? status.value.pending_count),
              stat("待下载字幕", status.value.subtitle_pending_count),
              stat("已处理", status.value.processed_count),
              stat("轮询次数", status.value.poll_count),
              stat("快速补扫", status.value.rapid_rescan_count),
              stat("文件变更事件", status.value.filesystem_event_count),
            ]),
          ]),
          h("div", { class: "cd2-trigger-card" }, [
            h("strong", "最近收到的 CD2 事件"),
            h("div", { class: "cd2-trigger-row" }, [
              h("span", `来源：${status.value.last_event_source || "暂无"}`),
              h("span", `类型：${status.value.last_message_type || status.value.last_event || "暂无"}`),
              h("span", `任务类型：${status.value.last_operator_type || "暂无"}`),
              h("span", `状态：${status.value.last_task_status || "暂无"}`),
            ]),
            h("div", { class: "cd2-trigger-path" }, status.value.last_dest_path || "暂无原始 destPath"),
            h("div", { class: "cd2-trigger-muted" }, status.value.last_message_at ? `最近消息：${status.value.last_message_at}` : "尚未收到上传/文件变更推送"),
          ]),
          h("div", { class: "cd2-trigger-card" }, [
            h("strong", "最近一次生成"),
            h("div", { class: "cd2-trigger-row" }, [
              h("span", `成功：${last.success_count ?? 0}`),
              h("span", `失败：${last.fail_count ?? 0}`),
              h("span", `助手元数据：${last.download_success_count ?? 0}`),
              h("span", { class: "cd2-trigger-muted" }, status.value.last_trigger_at || "暂无记录"),
            ]),
          ]),
          h("div", { class: "cd2-trigger-card" }, [
            h("strong", "本插件 Emby 批次刷新"),
            h("div", { class: "cd2-trigger-row" }, [
              h("span", `批次：${status.value.emby_refresh_batch_count ?? 0}`),
              h("span", `API请求：${status.value.emby_refresh_request_count ?? 0}`),
              h("span", `服务器：${(status.value.last_emby_refresh_servers || []).join(", ") || "暂无"}`),
              h("span", { class: "cd2-trigger-muted" }, status.value.last_emby_refresh_at || "暂无记录"),
            ]),
            status.value.last_emby_refresh_error ? h("div", { class: "cd2-trigger-message cd2-trigger-error" }, `最近刷新错误：${status.value.last_emby_refresh_error}`) : null,
          ]),
          h("div", { class: "cd2-trigger-card" }, [
            h("strong", "字幕下载"),
            h("div", { class: "cd2-trigger-row" }, [
              h("span", `成功：${status.value.subtitle_success_count ?? 0}`),
              h("span", `失败：${status.value.subtitle_fail_count ?? 0}`),
              h("span", { class: "cd2-trigger-muted" }, status.value.last_subtitle_file ? `最近：${status.value.last_subtitle_file}` : "暂无记录"),
            ]),
          ]),
          status.value.last_error ? h("div", { class: "cd2-trigger-message cd2-trigger-error" }, status.value.last_error) : null,
          status.value.last_subtitle_error ? h("div", { class: "cd2-trigger-message cd2-trigger-error" }, `最近字幕错误：${status.value.last_subtitle_error}`) : null,
          message.value ? h("div", { class: "cd2-trigger-message" }, message.value) : null,
          h("div", { class: "cd2-trigger-actions" }, [
            h("button", { class: "cd2-trigger-btn", disabled: loading.value, onClick: loadStatus }, loading.value ? "刷新中…" : "刷新状态"),
            h("button", { class: "cd2-trigger-btn primary", disabled: triggering.value, onClick: trigger }, triggering.value ? "触发中…" : "立即检查上传"),
            h("button", { class: "cd2-trigger-btn", onClick: () => { showHelp.value = true; } }, "使用说明"),
            h("button", { class: "cd2-trigger-btn", onClick: () => emit("switch") }, "设置"),
            h("button", { class: "cd2-trigger-btn", onClick: () => emit("close") }, "关闭"),
          ]),
        ]);
      };
    },
  });
  return () => Page;
}

const moduleMap = {
  "./Config": () => createConfigModule(),
  "./Page": () => createPageModule(),
};

function get(module) {
  /* 返回宿主请求的联邦组件模块。 */
  if (!moduleMap[module]) throw new Error(`Can not find remote module ${module}`);
  return moduleMap[module]();
}

function init(shareScope) {
  /* 接收 MoviePilot 前端提供的共享 Vue 运行时。 */
  globalThis.__federation_shared__ = globalThis.__federation_shared__ || {};
  globalThis.__federation_shared__.default = globalThis.__federation_shared__.default || {};
  Object.entries(shareScope || {}).forEach(([key, value]) => {
    Object.entries(value || {}).forEach(([versionKey, versionValue]) => {
      const scope = versionValue.scope || "default";
      globalThis.__federation_shared__[scope] = globalThis.__federation_shared__[scope] || {};
      const shared = globalThis.__federation_shared__[scope];
      (shared[key] = shared[key] || {})[versionKey] = versionValue;
    });
  });
}

export { get, init };
