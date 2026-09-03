/* CD2 上传触发 115 STRM：Vue 联邦远程入口。 */

const currentImports = {};
const moduleCache = {};

function flattenModule(module) {
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
      moduleCache[name] = flattenModule(module);
      return moduleCache[name];
    }
  }
  currentImports[name] ??= import(name);
  moduleCache[name] = flattenModule(await currentImports[name]);
  return moduleCache[name];
}

function clone(value) {
  /* 深复制配置，避免编辑表单直接修改宿主传入对象。 */
  if (value === undefined || value === null) return {};
  return JSON.parse(JSON.stringify(value));
}

function injectStyle() {
  /* 注入组件局部样式，不依赖额外 CSS 文件或第三方组件库。 */
  if (typeof document === "undefined" || document.getElementById("cd2-upload-strm-trigger-style")) return;
  const style = document.createElement("style");
  style.id = "cd2-upload-strm-trigger-style";
  style.textContent = `
    .cd2-trigger-config,.cd2-trigger-page{box-sizing:border-box;width:100%;padding:12px;color:var(--v-theme-on-surface,#e5e7eb);font-size:14px;line-height:1.45}
    .cd2-trigger-title{font-size:18px;font-weight:650;margin-bottom:3px}.cd2-trigger-subtitle{font-size:12px;opacity:.72;margin-bottom:10px}
    .cd2-trigger-card{box-sizing:border-box;border:1px solid rgba(127,127,127,.27);border-radius:9px;padding:11px;margin-bottom:9px;background:rgba(127,127,127,.045)}
    .cd2-trigger-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:8px}.cd2-trigger-card-head strong{font-size:14px}.cd2-trigger-card-head small{display:block;opacity:.68;font-weight:400;margin-top:2px}
    .cd2-trigger-overview-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:9px;min-width:0}.cd2-trigger-card-wide{grid-column:1/-1}
    .cd2-trigger-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,210px),1fr));gap:9px;min-width:0}.cd2-trigger-grid-wide{grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr))}
    .cd2-trigger-field{display:flex;flex-direction:column;gap:4px;min-width:0;font-size:12px}.cd2-trigger-field input,.cd2-trigger-field textarea{box-sizing:border-box;width:100%;min-width:0;border:1px solid rgba(127,127,127,.42);border-radius:6px;padding:7px 8px;background:transparent;color:inherit;font:inherit;line-height:1.35}.cd2-trigger-field input:focus,.cd2-trigger-field textarea:focus{outline:2px solid rgba(33,150,243,.42);outline-offset:1px}.cd2-trigger-field textarea{min-height:68px;resize:vertical}
    .cd2-trigger-check{display:flex;gap:7px;align-items:flex-start;margin:7px 0;font-size:13px;line-height:1.4}.cd2-trigger-check input{flex:0 0 auto;margin-top:3px}
    .cd2-trigger-actions{display:flex;gap:7px;flex-wrap:wrap;align-items:center;justify-content:flex-end}.cd2-trigger-footer{position:sticky;bottom:0;z-index:2;padding:9px 0 1px;background:var(--v-theme-background,rgba(20,20,20,.96))}
    .cd2-trigger-btn,.cd2-trigger-btn:visited,.cd2-trigger-btn:hover,.cd2-trigger-btn:active,.cd2-trigger-btn:focus,.cd2-trigger-config button,.cd2-trigger-page button{appearance:none;box-sizing:border-box;border:1px solid transparent;border-radius:6px;padding:7px 11px;cursor:pointer;background:#424242;font:inherit;line-height:1.25;text-decoration:none;color:#fff !important;-webkit-text-fill-color:#fff !important;text-shadow:none}.cd2-trigger-config button *,.cd2-trigger-page button *{color:#fff !important;-webkit-text-fill-color:#fff !important}.cd2-trigger-btn.primary{background:#1976d2}.cd2-trigger-btn.danger{background:#b3261e}.cd2-trigger-btn.subtle{background:#5d5d5d}.cd2-trigger-btn.small{padding:5px 8px;font-size:12px}.cd2-trigger-btn:disabled{opacity:.52;cursor:default}.cd2-trigger-btn:hover:not(:disabled){filter:brightness(1.12)}
    .cd2-trigger-tabs{display:flex;gap:6px;overflow-x:auto;padding:1px 0 8px;margin-bottom:1px}.cd2-trigger-tab{flex:0 0 auto;white-space:nowrap;background:#3b3b3b}.cd2-trigger-tab.active{background:#1976d2;border-color:rgba(255,255,255,.3)}
    .cd2-trigger-row{display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin:5px 0}.cd2-trigger-muted{opacity:.68}.cd2-trigger-hint,.cd2-trigger-note{font-size:12px;opacity:.78;line-height:1.58;margin-top:7px}.cd2-trigger-note{box-sizing:border-box;border-left:3px solid #42a5f5;padding:7px 9px;background:rgba(33,150,243,.11);opacity:.96}.cd2-trigger-message{border-radius:6px;padding:8px 10px;margin:8px 0;background:rgba(25,118,210,.13);white-space:pre-wrap;word-break:break-word}.cd2-trigger-error{background:rgba(211,47,47,.16);border-left:3px solid #ef5350}.cd2-trigger-callout{box-sizing:border-box;border:1px solid #ef9a9a;border-left:4px solid #d32f2f;border-radius:7px;padding:9px 11px;margin:9px 0;background:rgba(211,47,47,.2);white-space:pre-wrap;word-break:break-word}.cd2-trigger-callout strong{display:block;margin-bottom:4px}.cd2-trigger-callout ul{margin:4px 0 0 18px;padding:0}
    .cd2-trigger-pill{display:inline-flex;align-items:center;border-radius:999px;padding:3px 8px;font-size:12px;background:rgba(127,127,127,.17);white-space:nowrap}.cd2-trigger-pill.ok{background:rgba(46,125,50,.23)}.cd2-trigger-pill.bad{background:rgba(211,47,47,.23)}.cd2-trigger-pill.info{background:rgba(33,150,243,.2)}.cd2-trigger-pill.warn{background:rgba(245,124,0,.23)}
    .cd2-trigger-stat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(112px,1fr));gap:7px}.cd2-trigger-stat{min-width:0;padding:8px;border-radius:7px;background:rgba(127,127,127,.085)}.cd2-trigger-stat span{display:block;font-size:11px;opacity:.72;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.cd2-trigger-stat strong{display:block;font-size:18px;line-height:1.15;margin-top:3px}.cd2-trigger-path{margin:5px 0;word-break:break-all;white-space:pre-wrap;font-family:monospace;font-size:11px}.cd2-trigger-stack{min-width:0}
    .cd2-trigger-rule{border:1px solid rgba(127,127,127,.25);border-radius:7px;padding:9px;margin:8px 0;background:rgba(127,127,127,.035)}.cd2-trigger-rule-head{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px;font-weight:600}.cd2-trigger-rule .cd2-trigger-grid{grid-template-columns:repeat(auto-fit,minmax(190px,1fr))}
    .cd2-trigger-help-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:8px}.cd2-trigger-help-item{padding:9px;border-radius:7px;background:rgba(127,127,127,.085);line-height:1.55;font-size:12px}.cd2-trigger-help-item strong{display:block;margin-bottom:3px;font-size:13px}.cd2-trigger-help-flow{font-size:13px;line-height:1.7}.cd2-trigger-help-code{display:inline-block;padding:1px 4px;border-radius:4px;background:rgba(127,127,127,.14);font-family:monospace;word-break:break-all}
    .cd2-trigger-event-list{max-height:min(58vh,560px);overflow:auto;padding-right:2px}.cd2-trigger-event-item{border:1px solid rgba(127,127,127,.24);border-radius:7px;margin:6px 0;overflow:hidden}.cd2-trigger-event-toggle{display:grid!important;grid-template-columns:auto minmax(0,1fr) auto auto auto;align-items:center;width:100%;gap:8px;text-align:left;background:rgba(127,127,127,.07)!important;border:0!important;border-radius:0!important;padding:9px!important}.cd2-trigger-event-toggle:hover{background:rgba(33,150,243,.14)!important}.cd2-trigger-event-main{min-width:0}.cd2-trigger-event-main strong,.cd2-trigger-event-main span{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.cd2-trigger-event-main span{font-size:12px;opacity:.72;margin-top:2px}.cd2-trigger-event-at{font-size:11px;opacity:.68;white-space:nowrap}.cd2-trigger-event-arrow{font-size:12px;opacity:.85;white-space:nowrap}
    .cd2-trigger-category,.cd2-trigger-level{display:inline-flex;border-radius:999px;padding:3px 7px;font-size:11px;white-space:nowrap}.cd2-trigger-category{background:rgba(127,127,127,.2)}.cd2-trigger-category.cd2-category-cd2{background:rgba(33,150,243,.25)}.cd2-trigger-category.cd2-category-generate{background:rgba(46,125,50,.25)}.cd2-trigger-category.cd2-category-delete{background:rgba(245,124,0,.28)}.cd2-trigger-category.cd2-category-refresh{background:rgba(123,31,162,.28)}.cd2-trigger-category.cd2-category-metadata{background:rgba(0,137,123,.28)}.cd2-trigger-category.cd2-category-subtitle{background:rgba(0,121,107,.28)}.cd2-trigger-level{background:rgba(127,127,127,.18)}.cd2-trigger-level.ok{background:rgba(46,125,50,.25)}.cd2-trigger-level.warn{background:rgba(245,124,0,.25)}.cd2-trigger-level.bad{background:rgba(211,47,47,.25)}
    .cd2-trigger-event-detail{padding:9px 10px;border-top:1px solid rgba(127,127,127,.22);background:rgba(0,0,0,.06)}.cd2-trigger-detail-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:7px}.cd2-trigger-detail-item{min-width:0;padding:6px 7px;border-radius:5px;background:rgba(127,127,127,.07)}.cd2-trigger-detail-item strong{display:block;font-size:11px;opacity:.68;margin-bottom:2px}.cd2-trigger-detail-item span{display:block;white-space:pre-wrap;word-break:break-word;font-size:12px}.cd2-trigger-json{box-sizing:border-box;max-height:190px;overflow:auto;margin:8px 0 0;padding:8px;border-radius:6px;background:rgba(0,0,0,.2);font:11px/1.5 monospace;white-space:pre-wrap;word-break:break-word}.cd2-trigger-event-empty{padding:16px;text-align:center;opacity:.68}
    .cd2-trigger-field>span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}.cd2-trigger-rule{min-width:0}.cd2-trigger-stack,.cd2-trigger-card{min-width:0}
    @media (max-width:600px){.cd2-trigger-config,.cd2-trigger-page{padding:8px}.cd2-trigger-overview-grid,.cd2-trigger-grid,.cd2-trigger-grid-wide,.cd2-trigger-rule .cd2-trigger-grid{grid-template-columns:minmax(0,1fr)}.cd2-trigger-field>span{white-space:normal;overflow-wrap:anywhere;overflow:visible;text-overflow:clip}.cd2-trigger-card-head{flex-wrap:wrap}.cd2-trigger-event-toggle{grid-template-columns:auto minmax(0,1fr) auto}.cd2-trigger-event-at{grid-column:2;grid-row:2}.cd2-trigger-event-arrow{grid-column:3;grid-row:1/3}.cd2-trigger-footer{position:static}}
  `;
  document.head.appendChild(style);
}

function apiResult(response) {
  /* 兼容 MoviePilot API 客户端可能返回的单层或嵌套响应。 */
  let value = response;
  if (value?.data?.success !== undefined) value = value.data;
  return value;
}

function apiPayload(response) {
  const value = apiResult(response);
  if (value?.data && typeof value.data === "object" && !Array.isArray(value.data)) return value.data;
  return value || {};
}

function displayValue(value, fallback = "暂无") {
  if (value === undefined || value === null || value === "") return fallback;
  if (typeof value === "object") {
    try { return JSON.stringify(value); } catch (error) { return String(value); }
  }
  return String(value);
}

function jsonText(value) {
  try { return JSON.stringify(value, null, 2); } catch (error) { return String(value); }
}

function eventField(event, keys, fallback = "暂无") {
  const detailObject = event?.details && typeof event.details === "object" && !Array.isArray(event.details)
    ? event.details
    : {};
  for (const key of keys) {
    const direct = event?.[key];
    if (direct !== undefined && direct !== null && direct !== "") return displayValue(direct, fallback);
    const nested = detailObject[key];
    if (nested !== undefined && nested !== null && nested !== "") return displayValue(nested, fallback);
  }
  return fallback;
}

const categoryMeta = {
  cd2_event: { label: "CD2 事件", className: "cd2-category-cd2" },
  generate_event: { label: "生成", className: "cd2-category-generate" },
  delete_event: { label: "删除", className: "cd2-category-delete" },
  refresh_event: { label: "刷新", className: "cd2-category-refresh" },
  metadata_event: { label: "元数据", className: "cd2-category-metadata" },
  subtitle_event: { label: "字幕", className: "cd2-category-subtitle" },
};

function categoryInfo(category) {
  return categoryMeta[category] || { label: displayValue(category, "其他事件"), className: "" };
}

function levelInfo(level, status, ignored = false) {
  if (ignored) return { label: "已忽略", className: "" };
  const value = String(level || status || "info").toLowerCase();
  if (value.includes("error") || value.includes("fail") || value.includes("critical")) return { label: "错误", className: "bad" };
  if (value.includes("warn") || value.includes("pending")) return { label: "注意", className: "warn" };
  if (value.includes("success") || value.includes("ok") || value.includes("done")) return { label: "成功", className: "ok" };
  return { label: displayValue(level || status, "记录"), className: "" };
}

function createUsageView(h, onBack, options = {}) {
  /* 插件内置使用说明；导航动作由所属页面的全局页签和底栏负责。 */
  const actions = [];
  if (onBack) actions.push(h("button", { type: "button", class: "cd2-trigger-btn primary", onClick: onBack }, options.backLabel || "返回总览"));
  return h("div", { class: `cd2-trigger-page cd2-trigger-usage${options.compact ? " cd2-trigger-usage-compact" : ""}` }, [
    h("div", { class: "cd2-trigger-title" }, "使用说明"),
    h("div", { class: "cd2-trigger-subtitle" }, "Push 主触发、分类事件、目录映射和生成后动作的快速说明。"),
    h("div", { class: "cd2-trigger-card" }, [
      h("div", { class: "cd2-trigger-card-head" }, [h("strong", "处理流程"), h("span", { class: "cd2-trigger-pill info" }, "Push 优先")]),
      h("div", { class: "cd2-trigger-help-flow" }, "CD2 上传完成 → PushMessage/文件变更消息捕获 → 命中目录规则 → 媒体交给 115 STRM 助手生成 STRM，字幕由本插件下载到本地 → 生成、字幕、删除和刷新事件按批次记录并进入 Emby 刷新防抖窗口。插件启动后的第一次成功扫描只建立状态基线，已有完成任务不会补处理。"),
    ]),
    h("div", { class: "cd2-trigger-card" }, [
      h("div", { class: "cd2-trigger-card-head" }, [h("strong", "监听模式"), h("span", { class: "cd2-trigger-pill ok" }, "Push 主触发")]),
      h("div", { class: "cd2-trigger-help-flow" }, "PushMessage 是主触发方式；“轮询兜底”默认关闭。开启后，启动时仍只建立一次基线，Push 仍然是主路径，只有上传数量变化需要补扫、手动检查，或明确开启兜底开关时才进行轮询。关闭兜底可减少 CD2 API 轮询压力，断线补偿则依赖手动检查或再次收到 Push。"),
      h("div", { class: "cd2-trigger-note" }, "轮询兜底默认关闭；它不会改变启动基线规则，也不会把已有 Finish 任务批量重新处理。"),
    ]),
    h("div", { class: "cd2-trigger-card" }, [
      h("div", { class: "cd2-trigger-card-head" }, [h("strong", "目录映射"), h("span", { class: "cd2-trigger-pill info" }, "三段映射")]),
      h("div", { class: "cd2-trigger-help-grid" }, [
        h("div", { class: "cd2-trigger-help-item" }, [h("strong", "CD2 目标目录前缀"), h("span", "监控任务 destPath 的范围，只匹配该目录及子目录；/CloudNAS/115/影视库、/115/影视库、/影视库会按同一目录归一化。")]),
        h("div", { class: "cd2-trigger-help-item" }, [h("strong", "115 网盘路径前缀"), h("span", "对应 115 网盘媒体库根目录，用来组成 STRM 请求里的 pan_path。按当前 115 助手 API 传网盘相对根目录，例如 /影视库。")]),
        h("div", { class: "cd2-trigger-help-item" }, [h("strong", "本地 STRM 根目录"), h("span", "MoviePilot/Emby 读取 STRM 和字幕的本地根目录；两类文件沿相同相对路径落盘。")]),
      ]),
      h("div", { class: "cd2-trigger-note" }, "示例：CD2 目标 /115/影视库/电影/a.mkv（归一化为 /影视库/电影/a.mkv）→ 115 /影视库/电影/a.mkv → 本地 /media/MP_movieDB/影视库/电影/a.strm。"),
    ]),
    h("div", { class: "cd2-trigger-card" }, [
      h("div", { class: "cd2-trigger-card-head" }, [h("strong", "文件、字幕和附加动作"), h("span", { class: "cd2-trigger-pill info" }, "按开关执行")]),
      h("div", { class: "cd2-trigger-help-grid" }, [
        h("div", { class: "cd2-trigger-help-item" }, [h("strong", "媒体扩展名"), h("span", "命中后提交给 115 STRM 助手生成 STRM，不下载原媒体文件；单批最多提交 100 个任务。")]),
        h("div", { class: "cd2-trigger-help-item" }, [h("strong", "字幕扩展名/限速"), h("span", "默认 srt、ssa、ass、vtt、sub、idx、sup。字幕由本插件单线程串行下载，按下载间隔限速，并在下载前等待文件大小稳定。")]),
        h("div", { class: "cd2-trigger-help-item" }, [h("strong", "自动下载媒体元数据"), h("span", "由 115 STRM 助手按自身 user_download_mediaext 配置处理 .nfo、图片等文件，不等于本插件字幕下载。")]),
        h("div", { class: "cd2-trigger-help-item" }, [h("strong", "Emby 刷新与删除"), h("span", "媒体、字幕和删除同步成功后进入同一防抖窗口；删除同步默认关闭，仅删除对应 STRM/字幕和确实为空的目录。")]),
      ]),
    ]),
    h("div", { class: "cd2-trigger-card" }, [
      h("div", { class: "cd2-trigger-card-head" }, [h("strong", "CD2 Token 权限"), h("span", { class: "cd2-trigger-pill warn" }, "按需授权")]),
      h("div", { class: "cd2-trigger-help-flow" }, "监听需要“获取传输任务”和“接收推送消息”；下载字幕还需要文件读取相关权限，包括列出文件、读取文件、查看属性，以及对应的 HTTP 下载能力。CD2 API 根目录必须与 Token 的 RootDirectory 一致，例如 Token RootDirectory=/115 就填写 /115。"),
    ]),
    actions.length ? h("div", { class: "cd2-trigger-actions" }, actions) : null,
  ]);
}

async function createConfigModule() {
  /* 创建插件配置组件，使用多个紧凑子页避免长表单整页滚动。 */
  const vue = await importShared("vue");
  const { defineComponent, h, onMounted, reactive, ref } = vue;
  injectStyle();

  const Config = defineComponent({
    name: "Cd2UploadStrmTriggerConfig",
    props: {
      initialConfig: { type: Object, default: () => ({}) },
      api: { type: Object, default: () => ({}) },
      pluginId: { type: String, default: "Cd2UploadStrmTrigger" },
    },
    emits: ["save", "close", "switch"],
    setup(props, { emit }) {
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
        poll_fallback_enabled: false,
        include_extensions: "mkv,mp4,ts,avi,mov,m4v,wmv,flv,m2ts,iso,rmvb,webm,mpeg,mpg,3gp,asf,tp,f4v",
        subtitle_extensions: "srt,ssa,ass,vtt,sub,idx,sup",
        subtitle_interval: 3,
        subtitle_stability_delay: 3,
        emby_refresh_debounce: 5,
        delete_sync: false,
        scrape_metadata: false,
        media_server_refresh: false,
        auto_download_mediainfo: false,
        notify: false,
      };
      const config = reactive({ ...defaults, ...clone(props.initialConfig) });
      config.rules = Array.isArray(config.rules) ? config.rules : [];
      config.rules.forEach((rule, index) => {
        if (!rule || typeof rule !== "object") config.rules[index] = { enabled: true, name: "", cd2_prefix: "", pan_prefix: "", local_path: "" };
      });
      const tabs = [
        { key: "connection", label: "连接与监听" },
        { key: "rules", label: "目录规则" },
        { key: "files", label: "文件与限速" },
        { key: "actions", label: "生成后动作" },
        { key: "usage", label: "使用说明" },
      ];
      const activeTab = ref("connection");
      const message = ref("");
      const messageError = ref(false);
      const testing = ref(false);
      const validating = ref(false);
      const saving = ref(false);
      const validationMessage = ref("");
      const validationErrors = ref([]);
      let validationGeneration = 0;
      let validationPending = 0;

      const validationKeys = new Set([
        "enabled",
        "poll_fallback_enabled",
        "delete_sync",
        "media_server_refresh",
        "scrape_metadata",
        "auto_download_mediainfo",
      ]);

      function setMessage(value, error = false) {
        message.value = value || "";
        messageError.value = error;
      }

      function clearValidation() {
        validationMessage.value = "";
        validationErrors.value = [];
      }

      function normalizeValidationResponse(response) {
        const value = apiResult(response) || {};
        const data = value?.data && typeof value.data === "object" && !Array.isArray(value.data)
          ? value.data
          : value;
        return {
          ...data,
          valid: data.valid !== undefined ? !!data.valid : value.success !== false,
          message: data.message || value.message || "配置校验失败",
          errors: Array.isArray(data.errors) ? data.errors : [],
        };
      }

      function showValidation(result, fallback = "配置校验失败，请先处理提示") {
        const errors = Array.isArray(result?.errors) ? result.errors.filter((item) => item && item.message) : [];
        validationErrors.value = errors;
        validationMessage.value = result?.message || fallback;
        const firstTab = errors.find((item) => item.tab)?.tab;
        if (firstTab && tabs.some((tab) => tab.key === firstTab)) activeTab.value = firstTab;
      }

      function revertInvalidFeatures(result) {
        const features = new Set((result?.errors || []).map((item) => item?.feature).filter(Boolean));
        if (features.has("media_server_refresh")) config.media_server_refresh = false;
        if (features.has("delete_sync")) config.delete_sync = false;
        if (features.has("poll_fallback_enabled")) config.poll_fallback_enabled = false;
        if (features.has("moviepilot_actions")) {
          config.scrape_metadata = false;
          config.auto_download_mediainfo = false;
        }
      }

      function snapshotKey(value) {
        try { return JSON.stringify(value); } catch (error) { return String(value); }
      }

      function matchesCurrentConfig(snapshot) {
        return snapshotKey(snapshot) === snapshotKey(clone(config));
      }

      async function validateConfiguration(snapshot = clone(config)) {
        /* 每次校验固定发送调用时的快照；响应过期时不覆盖当前表单状态。 */
        const requestConfig = clone(snapshot);
        const generation = ++validationGeneration;
        validationPending += 1;
        validating.value = true;
        try {
          let result;
          try {
            const response = await props.api.post(
              `/plugin/${props.pluginId || "Cd2UploadStrmTrigger"}/validate`,
              requestConfig,
            );
            result = normalizeValidationResponse(response);
          } catch (error) {
            result = {
              valid: false,
              message: "配置校验请求失败，请稍后重试",
              errors: [{ field: "", tab: activeTab.value, message: "无法完成前置校验" }],
            };
          }
          result._generation = generation;
          if (generation === validationGeneration) {
            if (result.valid) clearValidation();
            else showValidation(result);
          }
          return result;
        } finally {
          validationPending -= 1;
          if (validationPending <= 0) validating.value = false;
        }
      }

      function button(label, onClick, className = "", extra = {}) {
        return h("button", { type: "button", class: `cd2-trigger-btn ${className}`.trim(), onClick, ...extra }, label);
      }

      function cardHead(title, subtitle = "") {
        return h("div", { class: "cd2-trigger-card-head" }, [
          h("div", [h("strong", title), subtitle ? h("small", subtitle) : null]),
        ]);
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
        return h("label", { class: "cd2-trigger-field" }, [
          h("span", label),
          h("input", {
            type: "number", min, max, step, value: config[key],
            onInput: (event) => {
              const next = Number(event.target.value);
              config[key] = Number.isNaN(next) ? 0 : next;
            },
          }),
        ]);
      }

      function checkField(label, key) {
        return h("label", { class: "cd2-trigger-check" }, [
          h("input", {
            type: "checkbox",
            checked: !!config[key],
            onChange: async (event) => {
              const checked = !!event.target.checked;
              config[key] = checked;
              if (!checked || !validationKeys.has(key)) return;
              clearValidation();
              const snapshot = clone(config);
              const result = await validateConfiguration(snapshot);
              if (result._generation !== validationGeneration || !matchesCurrentConfig(snapshot)) return;
              if (!result.valid) {
                config[key] = false;
                revertInvalidFeatures(result);
                showValidation(result);
              }
            },
          }),
          h("span", label),
        ]);
      }

      function ruleCheckField(rule) {
        return h("label", { class: "cd2-trigger-check" }, [
          h("input", { type: "checkbox", checked: !!rule.enabled, onChange: (event) => { rule.enabled = event.target.checked; } }),
          h("span", "启用此规则"),
        ]);
      }

      function ruleField(rule, label, key, placeholder = "") {
        return h("label", { class: "cd2-trigger-field" }, [
          h("span", label),
          h("input", { value: rule[key] || "", placeholder, onInput: (event) => { rule[key] = event.target.value; } }),
        ]);
      }

      async function testConnection() {
        /* 调用后端测试 CD2 和 MoviePilot API。 */
        testing.value = true;
        setMessage("");
        try {
          const response = apiResult(await props.api.post(`/plugin/${props.pluginId || "Cd2UploadStrmTrigger"}/test`, clone(config)));
          setMessage(response?.success ? (response.message || "连接测试成功") : (response?.message || "连接测试失败"), !response?.success);
        } catch (error) {
          setMessage(error?.message || "连接测试失败", true);
        } finally {
          testing.value = false;
        }
      }

      async function save() {
        /* 保存前再次校验，避免绕过开关事件直接提交无效配置。 */
        if (saving.value) return;
        saving.value = true;
        try {
          let snapshot = clone(config);
          clearValidation();
          let result = await validateConfiguration(snapshot);
          if (result._generation !== validationGeneration || !matchesCurrentConfig(snapshot)) {
            snapshot = clone(config);
            result = await validateConfiguration(snapshot);
          }
          if (!matchesCurrentConfig(snapshot)) {
            showValidation({
              valid: false,
              message: "配置在校验期间发生变化，请重新保存",
              errors: [{ field: "", tab: activeTab.value, message: "请确认当前配置后重试" }],
            });
            return;
          }
          if (!result.valid) {
            revertInvalidFeatures(result);
            showValidation(result);
            return;
          }
          emit("save", clone(snapshot));
        } finally {
          saving.value = false;
        }
      }

      function moveTab(delta) {
        const index = tabs.findIndex((tab) => tab.key === activeTab.value);
        const next = Math.max(0, Math.min(tabs.length - 1, index + delta));
        activeTab.value = tabs[next].key;
      }

      function tabButton(tab) {
        return button(tab.label, () => { activeTab.value = tab.key; }, `cd2-trigger-tab${activeTab.value === tab.key ? " active" : ""}`);
      }

      function renderValidationCallout() {
        if (!validationMessage.value && !validationErrors.value.length) return null;
        return h("div", { class: "cd2-trigger-callout", role: "alert" }, [
          h("strong", validationMessage.value || "请先处理配置校验提示"),
          validationErrors.value.length ? h("ul", validationErrors.value.map((error, index) => h("li", { key: `${error.field || "error"}-${index}` }, error.message))) : null,
        ]);
      }

      function renderConnectionTab() {
        return h("div", { class: "cd2-trigger-stack" }, [
          h("div", { class: "cd2-trigger-card" }, [
            cardHead("基本连接", "填写 CD2 与 MoviePilot 地址、令牌；令牌不会在页面中回显。"),
            checkField("启用插件", "enabled"),
            h("div", { class: "cd2-trigger-grid cd2-trigger-grid-wide" }, [
              field("CD2 gRPC 地址", "cd2_endpoint", "例如 CD2 服务地址"),
              field("CD2 API Token", "cd2_token", "仅填写 Token，不要写 Bearer", true),
              field("CD2 API 根目录（Token RootDirectory）", "cd2_api_root", "/115"),
              field("MoviePilot 地址", "moviepilot_url", "例如 MoviePilot 服务地址"),
              field("MoviePilot API Key（可选）", "moviepilot_api_key", "留空则使用系统 API_TOKEN", true),
            ]),
            h("div", { class: "cd2-trigger-hint" }, "CD2 Token 需要开启“获取传输任务”和“接收推送消息”；下载字幕还需列出文件、读取文件、查看属性等文件读取权限。API 根目录必须与令牌 RootDirectory 一致。MoviePilot API Key 留空时使用当前实例的系统 API_TOKEN。"),
          ]),
          h("div", { class: "cd2-trigger-card" }, [
            cardHead("监听模式", "PushMessage 是主触发路径，轮询只是可选补偿。"),
            h("div", { class: "cd2-trigger-row" }, [
              h("span", { class: "cd2-trigger-pill ok" }, "Push 主触发"),
              h("span", { class: `cd2-trigger-pill ${config.poll_fallback_enabled ? "warn" : "info"}` }, `轮询兜底：${config.poll_fallback_enabled ? "已开启" : "默认关闭"}`),
            ]),
            checkField("开启轮询兜底（默认关闭）", "poll_fallback_enabled"),
            h("div", { class: "cd2-trigger-note" }, "启动时只建立一次状态基线；Push 为主，只有数量变化按需补扫、手动检查或开启兜底才轮询。关闭此开关不会关闭 Push，也不会处理启动前已有的 Finish 任务。"),
            h("div", { class: "cd2-trigger-grid" }, [numberField("轮询间隔（秒）", "poll_interval", 2, 60)]),
            h("div", { class: "cd2-trigger-actions" }, [button(testing.value ? "测试中…" : "手动测试连接", testConnection, "primary", { disabled: testing.value })]),
          ]),
        ]);
      }

      function renderRulesTab() {
        return h("div", { class: "cd2-trigger-stack" }, [
          h("div", { class: "cd2-trigger-card" }, [
            h("div", { class: "cd2-trigger-card-head" }, [
              h("div", [h("strong", "目录映射规则"), h("small", "CD2 目标目录前缀 → 115 网盘路径前缀 → 本地 STRM 根目录")]),
              button("添加规则", addRule, "primary small"),
            ]),
            h("div", { class: "cd2-trigger-hint" }, "CD2 前缀负责监控范围，支持挂载/源/API 路径归一化；115 前缀负责生成 STRM 的 pan_path；本地根目录是 MoviePilot/Emby 读取 STRM 和字幕的位置。匹配采用目录边界，不会把 /电影2 误判为 /电影。"),
            ...config.rules.map((rule, index) => h("div", { class: "cd2-trigger-rule", key: index }, [
              h("div", { class: "cd2-trigger-rule-head" }, [
                h("span", `规则 ${index + 1}`),
                button("删除", () => removeRule(index), "danger small"),
              ]),
              ruleCheckField(rule),
              h("div", { class: "cd2-trigger-grid" }, [
                ruleField(rule, "规则名称", "name", "例如电影库"),
                ruleField(rule, "CD2 目标目录前缀（挂载/源/API 均可）", "cd2_prefix", "/影视库"),
                ruleField(rule, "115 网盘路径前缀", "pan_prefix", "/影视库"),
                ruleField(rule, "本地 STRM 根目录", "local_path", "/media/MP_movieDB/影视库"),
              ]),
            ])),
            config.rules.length === 0 ? h("div", { class: "cd2-trigger-event-empty" }, "还没有规则，请添加至少一条目录映射。") : null,
          ]),
        ]);
      }

      function renderFilesTab() {
        return h("div", { class: "cd2-trigger-stack" }, [
          h("div", { class: "cd2-trigger-card" }, [
            cardHead("文件与批处理", "控制单次读取和提交的节奏；媒体 STRM 单批最多提交 100 个任务。"),
            h("div", { class: "cd2-trigger-grid" }, [
              numberField("批处理等待（秒）", "batch_window", 0, 120),
              numberField("每页任务数", "page_size", 20, 1000),
              field("媒体扩展名（逗号分隔）", "include_extensions", "mkv,mp4,ts"),
            ]),
          ]),
          h("div", { class: "cd2-trigger-card" }, [
            cardHead("字幕下载与限速", "字幕不生成 STRM，由本插件独立下载到映射后的本地媒体目录。"),
            h("div", { class: "cd2-trigger-grid" }, [
              field("字幕扩展名（逗号分隔）", "subtitle_extensions", "srt,ssa,ass,vtt,sub,idx,sup"),
              numberField("字幕下载间隔（秒）", "subtitle_interval", 0, 60, 0.5),
              numberField("字幕稳定等待（秒）", "subtitle_stability_delay", 0, 60, 0.5),
            ]),
            h("div", { class: "cd2-trigger-hint" }, "下载前先等待并连续读取两次 CD2 文件大小；大小稳定后才下载，失败会按后端策略重试。间隔设为 0 表示不额外等待。"),
          ]),
        ]);
      }

      function renderActionsTab() {
        return h("div", { class: "cd2-trigger-stack" }, [
          h("div", { class: "cd2-trigger-card" }, [
            cardHead("生成后动作", "这些开关只决定生成成功后的附加动作，不改变 Push/轮询监听。"),
            checkField("由 115 STRM 助手刮削元数据", "scrape_metadata"),
            checkField("由 115 STRM 助手下载 .nfo/.jpg 等媒体元数据", "auto_download_mediainfo"),
            checkField("发送 STRM 生成结果通知（使用 MoviePilot 通知渠道）", "notify"),
            h("div", { class: "cd2-trigger-hint" }, "自动刮削和媒体元数据下载由 115 STRM 助手执行；本插件字幕下载是独立流程，不会把字幕任务传给助手。"),
          ]),
          h("div", { class: "cd2-trigger-card" }, [
            cardHead("Emby 刷新与删除同步", "媒体、字幕、删除同步成功后可合并为一次刷新。"),
            checkField("由本插件刷新 Emby（媒体/字幕/删除，防抖）", "media_server_refresh"),
            h("div", { class: "cd2-trigger-grid" }, [numberField("Emby 刷新防抖（秒）", "emby_refresh_debounce", 0, 120, 0.5)]),
            checkField("同步 CD2 删除到本地（仅删除对应字幕/STRM和空目录）", "delete_sync"),
            h("div", { class: "cd2-trigger-note" }, "删除同步默认关闭；开启后仅处理监控目录中对应的本地字幕/STRM，并只清理确实为空的目录，不递归删除其他文件。"),
          ]),
        ]);
      }

      function renderTabBody() {
        if (activeTab.value === "rules") return renderRulesTab();
        if (activeTab.value === "files") return renderFilesTab();
        if (activeTab.value === "actions") return renderActionsTab();
        if (activeTab.value === "usage") {
          return createUsageView(h, null, { compact: true });
        }
        return renderConnectionTab();
      }

      onMounted(() => {
        if (!Array.isArray(config.rules)) config.rules = [];
      });

      return () => {
        const tabIndex = tabs.findIndex((tab) => tab.key === activeTab.value);
        return h("form", { class: "cd2-trigger-config", onSubmit: (event) => { event.preventDefault(); save(); } }, [
          h("div", { class: "cd2-trigger-title" }, "CD2 上传触发 115 STRM"),
          h("div", { class: "cd2-trigger-subtitle" }, "v0.8.3 · Push 主触发、分类事件历史、多页设置和保存前置校验。"),
          h("div", { class: "cd2-trigger-tabs", role: "tablist" }, tabs.map(tabButton)),
          renderTabBody(),
          renderValidationCallout(),
          message.value ? h("div", { class: `cd2-trigger-message${messageError.value ? " cd2-trigger-error" : ""}` }, message.value) : null,
          h("div", { class: "cd2-trigger-actions cd2-trigger-footer" }, [
            button("上一页", () => moveTab(-1), "subtle", { disabled: tabIndex <= 0 }),
            button("下一页", () => moveTab(1), "subtle", { disabled: tabIndex >= tabs.length - 1 }),
            button(testing.value ? "测试中…" : "测试连接", testConnection, "", { disabled: testing.value || saving.value }),
            h("button", { type: "submit", class: "cd2-trigger-btn primary", disabled: saving.value || validating.value }, saving.value ? "保存中…" : "保存配置"),
            button("关闭", () => emit("close")),
          ]),
        ]);
      };
    },
  });
  return () => Config;
}

async function createPageModule() {
  /* 创建插件状态页面，分为总览、事件和说明三个子页。 */
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
      const status = ref({});
      const manualRefreshing = ref(false);
      const triggering = ref(false);
      const message = ref("");
      const activeTab = ref("overview");
      const expandedEventId = ref("");
      let timer = null;
      let statusRequest = null;

      const endpointId = () => props.pluginId || "Cd2UploadStrmTrigger";

      async function loadStatus(manual = false) {
        /* 状态请求单飞；自动刷新不改变底栏按钮，手动刷新才显示稳定反馈。 */
        if (manual && manualRefreshing.value) return statusRequest;
        if (manual) manualRefreshing.value = true;
        if (statusRequest) {
          try {
            const ok = await statusRequest;
            if (manual && ok) message.value = "状态已刷新";
          } finally {
            if (manual) manualRefreshing.value = false;
          }
          return statusRequest;
        }
        const request = (async () => {
          try {
            const next = apiPayload(await props.api.get(`/plugin/${endpointId()}/status`));
            if (next && typeof next === "object") status.value = { ...status.value, ...next };
            return true;
          } catch (error) {
            message.value = error?.message || "读取状态失败";
            return false;
          }
        })();
        statusRequest = request;
        try {
          const ok = await request;
          if (manual && ok) message.value = "状态已刷新";
        } finally {
          if (statusRequest === request) statusRequest = null;
          if (manual) manualRefreshing.value = false;
        }
      }

      async function trigger() {
        /* 请求后台立即检查一次 CD2 上传任务。 */
        triggering.value = true;
        try {
          const response = apiResult(await props.api.post(`/plugin/${endpointId()}/trigger`, {}));
          const payload = response?.data && typeof response.data === "object" ? response.data : response;
          message.value = response?.message || payload?.message || "已请求检查";
          await loadStatus(false);
        } catch (error) {
          message.value = error?.message || "触发失败";
        } finally {
          triggering.value = false;
        }
      }

      function button(label, onClick, className = "", extra = {}) {
        return h("button", { type: "button", class: `cd2-trigger-btn ${className}`.trim(), onClick, ...extra }, label);
      }

      function cardHead(title, subtitle = "") {
        return h("div", { class: "cd2-trigger-card-head" }, [
          h("div", [h("strong", title), subtitle ? h("small", subtitle) : null]),
        ]);
      }

      function stat(label, value) {
        return h("div", { class: "cd2-trigger-stat" }, [h("span", label), h("strong", displayValue(value, "0"))]);
      }

      function statusFallbackEnabled() {
        if (status.value.poll_fallback_enabled !== undefined) return !!status.value.poll_fallback_enabled;
        return !!props.initialConfig?.poll_fallback_enabled;
      }

      function sortedEvents() {
        const history = Array.isArray(status.value.event_history) ? status.value.event_history : [];
        return history.map((event, index) => ({ event: event || {}, index })).sort((left, right) => {
          const leftAt = Date.parse(String(left.event.at || ""));
          const rightAt = Date.parse(String(right.event.at || ""));
          if (Number.isFinite(leftAt) && Number.isFinite(rightAt) && leftAt !== rightAt) return rightAt - leftAt;
          if (left.event.at && right.event.at && left.event.at !== right.event.at) return String(right.event.at).localeCompare(String(left.event.at));
          return right.index - left.index;
        }).slice(0, 10);
      }

      function eventKey(event, index) {
        return String(event.id ?? `${event.at || "event"}-${index}`);
      }

      function eventDetails(event) {
        return [
          ["原始 destPath", eventField(event, ["raw_dest_path", "rawDestPath", "dest_path", "destPath"])],
          ["规范化 path", eventField(event, ["path", "normalized_path", "normalizedPath"])],
          ["来源", eventField(event, ["source"])],
          ["操作类型", eventField(event, ["operation_type", "operationType", "operation"], categoryInfo(event.category).label)],
          ["操作/处理状态", eventField(event, ["status", "state"])],
          ["消息类型", eventField(event, ["message_type", "messageType"])],
          ["原因", eventField(event, ["reason", "cause"], event.message || "暂无")],
          ["结果", eventField(event, ["result", "outcome"], event.message || "暂无")],
          ["事件时间", eventField(event, ["at", "time", "timestamp"])],
          ["级别", eventField(event, ["level"])],
        ];
      }

      function renderEvent(event, index) {
        const key = eventKey(event, index);
        const expanded = expandedEventId.value === key;
        const category = categoryInfo(event.category);
        const level = levelInfo(event.level, event.status, event.status === "ignored");
        const title = displayValue(event.title || event.message, "未命名事件");
        const messageText = event.title && event.message ? displayValue(event.message, "") : "";
        const detailRows = eventDetails(event);
        return h("div", { class: "cd2-trigger-event-item", key }, [
          h("button", {
            type: "button",
            class: "cd2-trigger-event-toggle",
            "aria-expanded": expanded,
            onClick: () => { expandedEventId.value = expanded ? "" : key; },
          }, [
            h("span", { class: `cd2-trigger-category ${category.className}` }, category.label),
            h("span", { class: "cd2-trigger-event-main" }, [h("strong", title), messageText ? h("span", messageText) : null]),
            h("span", { class: "cd2-trigger-event-at" }, displayValue(event.at, "时间未知")),
            h("span", { class: `cd2-trigger-level ${level.className}` }, level.label),
            h("span", { class: "cd2-trigger-event-arrow" }, expanded ? "收起" : "详情"),
          ]),
          expanded ? h("div", { class: "cd2-trigger-event-detail" }, [
            h("div", { class: "cd2-trigger-detail-grid" }, detailRows.map(([label, value]) => h("div", { class: "cd2-trigger-detail-item", key: label }, [h("strong", label), h("span", value)]))),
            event.message ? h("div", { class: "cd2-trigger-message" }, `消息：${displayValue(event.message)}`) : null,
            event.details !== undefined && event.details !== null ? h("pre", { class: "cd2-trigger-json" }, jsonText(event.details)) : null,
          ]) : null,
        ]);
      }

      function visibleErrors() {
        return [
          ["监听", status.value.last_error],
          ["字幕", status.value.last_subtitle_error],
          ["Emby 刷新", status.value.last_emby_refresh_error],
        ].filter(([, value]) => value);
      }

      function renderOverview() {
        const current = status.value;
        const last = current.last_trigger || {};
        const connected = !!current.connected;
        const pushPrimary = current.push_primary !== false;
        const fallbackEnabled = statusFallbackEnabled();
        const errors = visibleErrors();
        const localPaths = Array.isArray(current.last_delete_local_paths) ? current.last_delete_local_paths : [];
        return h("div", { class: "cd2-trigger-overview" }, [
          h("div", { class: "cd2-trigger-card cd2-trigger-card-wide" }, [
            cardHead("连接与监听", "Push 主触发，轮询按开关提供断线补偿。"),
            h("div", { class: "cd2-trigger-row" }, [
              h("span", { class: `cd2-trigger-pill ${connected ? "ok" : "bad"}` }, connected ? "CD2 已连接" : "CD2 未连接"),
              h("span", { class: `cd2-trigger-pill ${current.running ? "ok" : "bad"}` }, current.running ? "监听运行中" : "监听未运行"),
              h("span", { class: "cd2-trigger-pill info" }, pushPrimary ? "Push 主触发" : "Push 未启用"),
              h("span", { class: `cd2-trigger-pill ${fallbackEnabled ? "warn" : "info"}` }, `轮询兜底：${fallbackEnabled ? "已开启" : "默认关闭"}`),
            ]),
            h("div", { class: "cd2-trigger-row" }, [
              h("span", `最近 Push：${displayValue(current.last_push_at)}`),
              h("span", `最近轮询：${displayValue(current.last_poll_at)}`),
              h("span", `轮询次数：${displayValue(current.poll_count, "0")}`),
              h("span", `快速补扫：${displayValue(current.rapid_rescan_count, "0")}`),
              h("span", `文件变更：${displayValue(current.filesystem_event_count, "0")}`),
            ]),
          ]),
          h("div", { class: "cd2-trigger-card cd2-trigger-card-wide" }, [
            cardHead("任务、队列与处理统计", "当前状态快照。"),
            h("div", { class: "cd2-trigger-stat-grid" }, [
              stat("CD2 当前任务", current.upload_count),
              stat("本轮列表任务", current.task_count),
              stat("命中规则", current.matched_count),
              stat("待生成 STRM", current.strm_pending_count ?? current.pending_count),
              stat("待下载字幕", current.subtitle_pending_count),
              stat("待处理", current.pending_count),
              stat("已处理", current.processed_count),
              stat("已忽略", current.ignored_count),
            ]),
          ]),
          h("div", { class: "cd2-trigger-overview-grid" }, [
            h("div", { class: "cd2-trigger-card" }, [
              cardHead("最近收到的 CD2 事件", "保留原始路径，便于排查目录匹配。"),
              h("div", { class: "cd2-trigger-row" }, [
                h("span", `来源：${displayValue(current.last_event_source)}`),
                h("span", `消息类型：${displayValue(current.last_message_type || current.last_event)}`),
                h("span", `操作类型：${displayValue(current.last_operator_type)}`),
                h("span", `状态：${displayValue(current.last_task_status)}`),
              ]),
              h("div", { class: "cd2-trigger-path" }, current.last_dest_path || "暂无原始 destPath"),
              h("div", { class: "cd2-trigger-muted" }, current.last_message_at ? `最近消息：${current.last_message_at}` : "尚未收到上传/文件变更推送"),
            ]),
            h("div", { class: "cd2-trigger-card" }, [
              cardHead("最近一次生成", "媒体 STRM 批次结果。"),
              h("div", { class: "cd2-trigger-stat-grid" }, [
                stat("成功", last.success_count ?? 0),
                stat("失败", last.fail_count ?? 0),
                stat("提交", last.total_count ?? last.submitted_count ?? 0),
              ]),
              h("div", { class: "cd2-trigger-muted" }, current.last_trigger_at || "暂无记录"),
              last.message ? h("div", { class: "cd2-trigger-hint" }, displayValue(last.message)) : null,
            ]),
            h("div", { class: "cd2-trigger-card" }, [
              cardHead("元数据", "由 115 STRM 助手按其配置执行。"),
              h("div", { class: "cd2-trigger-row" }, [
                h("span", `助手元数据成功：${displayValue(last.download_success_count ?? current.metadata_success_count, "0")}`),
                h("span", `失败：${displayValue(last.download_fail_count ?? current.metadata_fail_count, "0")}`),
              ]),
              h("div", { class: "cd2-trigger-hint" }, "本插件不把字幕任务传给助手；元数据开关可在生成后动作中调整。"),
            ]),
            h("div", { class: "cd2-trigger-card" }, [
              cardHead("字幕下载", "独立线程、稳定性确认和间隔限速。"),
              h("div", { class: "cd2-trigger-row" }, [
                h("span", `成功：${displayValue(current.subtitle_success_count, "0")}`),
                h("span", `失败：${displayValue(current.subtitle_fail_count, "0")}`),
                h("span", `待下载：${displayValue(current.subtitle_pending_count, "0")}`),
              ]),
              h("div", { class: "cd2-trigger-path" }, current.last_subtitle_file || "暂无最近字幕文件"),
              current.last_subtitle_error ? h("div", { class: "cd2-trigger-message cd2-trigger-error" }, `最近字幕错误：${current.last_subtitle_error}`) : null,
            ]),
            h("div", { class: "cd2-trigger-card" }, [
              cardHead("CD2 删除同步", "仅在启用删除同步时处理本地 STRM/字幕。"),
              h("div", { class: "cd2-trigger-row" }, [
                h("span", `成功：${displayValue(current.delete_sync_count, "0")}`),
                h("span", `未找到本地文件：${displayValue(current.delete_sync_missing_count, "0")}`),
              ]),
              h("div", { class: "cd2-trigger-path" }, current.last_delete_path ? `最近：${current.last_delete_path}` : "暂无删除记录"),
              localPaths.length ? h("div", { class: "cd2-trigger-path" }, localPaths.join("\n")) : null,
            ]),
            h("div", { class: "cd2-trigger-card" }, [
              cardHead("Emby 批次刷新", "媒体、字幕和删除同步共用防抖窗口。"),
              h("div", { class: "cd2-trigger-row" }, [
                h("span", `批次：${displayValue(current.emby_refresh_batch_count, "0")}`),
                h("span", `API 请求：${displayValue(current.emby_refresh_request_count, "0")}`),
                h("span", `待合并：${displayValue(current.emby_refresh_pending_count, "0")}`),
              ]),
              h("div", { class: "cd2-trigger-path" }, `服务器：${Array.isArray(current.last_emby_refresh_servers) ? (current.last_emby_refresh_servers.join(", ") || "暂无") : displayValue(current.last_emby_refresh_servers)}`),
              h("div", { class: "cd2-trigger-muted" }, current.last_emby_refresh_at || "暂无刷新记录"),
              current.last_emby_refresh_error ? h("div", { class: "cd2-trigger-message cd2-trigger-error" }, `最近刷新错误：${current.last_emby_refresh_error}`) : null,
            ]),
            h("div", { class: "cd2-trigger-card" }, [
              cardHead("错误摘要", "只显示需要处理的运行错误。"),
              errors.length ? errors.map(([label, value]) => h("div", { class: "cd2-trigger-message cd2-trigger-error", key: label }, `${label}：${value}`)) : h("div", { class: "cd2-trigger-muted" }, "当前没有可见错误。"),
            ]),
          ]),
        ]);
      }

      function renderEvents() {
        const events = sortedEvents();
        const total = Array.isArray(status.value.event_history) ? status.value.event_history.length : 0;
        return h("div", { class: "cd2-trigger-stack" }, [
          h("div", { class: "cd2-trigger-card" }, [
            cardHead("事件历史", `最近 10 条（当前共 ${total} 条），按时间倒序；点击一条展开详情。`),
            h("div", { class: "cd2-trigger-row" }, Object.entries(categoryMeta).map(([key, info]) => h("span", { class: `cd2-trigger-category ${info.className}`, key }, info.label))),
            events.length ? h("div", { class: "cd2-trigger-event-list" }, events.map(({ event }, index) => renderEvent(event, index))) : h("div", { class: "cd2-trigger-event-empty" }, "后端尚未返回事件历史；收到分类事件后，最近 10 条会显示在这里。"),
            h("div", { class: "cd2-trigger-note" }, "详情包含原始 destPath、规范化 path、来源、操作类型/状态、消息类型、原因和结果。"),
          ]),
        ]);
      }

      onMounted(() => {
        void loadStatus(false);
        timer = setInterval(() => { void loadStatus(false); }, 10000);
      });
      onUnmounted(() => { if (timer) clearInterval(timer); });

      return () => h("div", { class: "cd2-trigger-page" }, [
        h("div", { class: "cd2-trigger-title" }, "CD2 上传触发 115 STRM"),
        h("div", { class: "cd2-trigger-subtitle" }, "v0.8.3 · 紧凑总览、最近 10 条分类事件和可展开详情"),
        h("div", { class: "cd2-trigger-tabs", role: "tablist" }, [
          button("总览", () => { activeTab.value = "overview"; }, `cd2-trigger-tab${activeTab.value === "overview" ? " active" : ""}`),
          button("事件", () => { activeTab.value = "events"; }, `cd2-trigger-tab${activeTab.value === "events" ? " active" : ""}`),
          button("说明", () => { activeTab.value = "usage"; }, `cd2-trigger-tab${activeTab.value === "usage" ? " active" : ""}`),
        ]),
        activeTab.value === "events" ? renderEvents() : activeTab.value === "usage"
          ? createUsageView(h, () => { activeTab.value = "overview"; })
          : renderOverview(),
        message.value ? h("div", { class: "cd2-trigger-message" }, message.value) : null,
        activeTab.value !== "usage"
          ? h("div", { class: "cd2-trigger-actions cd2-trigger-footer" }, [
              button(manualRefreshing.value ? "刷新中…" : "刷新状态", () => { void loadStatus(true); }, "", { disabled: manualRefreshing.value }),
              button(triggering.value ? "触发中…" : "立即检查上传", trigger, "primary", { disabled: triggering.value }),
              button("设置", () => emit("switch")),
              button("关闭", () => emit("close")),
            ])
          : null,
      ]);
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
