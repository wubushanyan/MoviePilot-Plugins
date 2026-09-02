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
    .cd2-trigger-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}.cd2-trigger-btn{border:0;border-radius:6px;padding:9px 14px;cursor:pointer;background:#424242;color:#fff}.cd2-trigger-btn.primary{background:#1976d2}.cd2-trigger-btn.danger{background:#b3261e}.cd2-trigger-btn:disabled{opacity:.55;cursor:default}
    .cd2-trigger-rule{border:1px solid rgba(127,127,127,.25);border-radius:8px;padding:12px;margin:10px 0}.cd2-trigger-rule-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;font-weight:600}.cd2-trigger-hint{font-size:12px;opacity:.7;line-height:1.6;margin-top:8px}.cd2-trigger-message{border-radius:6px;padding:10px;margin-top:12px;background:rgba(25,118,210,.12)}.cd2-trigger-error{background:rgba(211,47,47,.15)}
    .cd2-trigger-stat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}.cd2-trigger-stat{padding:12px;border-radius:8px;background:rgba(127,127,127,.08)}.cd2-trigger-stat strong{display:block;font-size:20px;margin-top:4px}.cd2-trigger-muted{opacity:.68}.cd2-trigger-row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:8px 0}.cd2-trigger-pill{display:inline-flex;border-radius:999px;padding:4px 9px;font-size:12px;background:rgba(127,127,127,.16)}.cd2-trigger-pill.ok{background:rgba(46,125,50,.2)}.cd2-trigger-pill.bad{background:rgba(211,47,47,.2)}
  `;
  document.head.appendChild(style);
}

function apiResult(response) {
  /* 兼容 MoviePilot API 客户端可能返回的单层或嵌套响应。 */
  let value = response;
  if (value?.data?.success !== undefined) value = value.data;
  return value;
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
        moviepilot_url: "http://127.0.0.1:3001",
        moviepilot_api_key: "",
        rules: [],
        poll_interval: 5,
        batch_window: 5,
        page_size: 200,
        baseline_on_start: true,
        include_extensions: "mkv,mp4,ts,avi,mov,m4v,wmv,flv,m2ts,iso,rmvb,webm",
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

      function setMessage(text, error = false) {
        /* 更新配置页面提示信息。 */
        message.value = text || "";
        messageError.value = error;
      }

      function addRule() {
        /* 添加一条 CD2 到 115 的目录映射规则。 */
        config.rules.push({ enabled: true, name: "", cd2_prefix: "/CloudNAS/115/影视库", pan_prefix: "/影视库", local_path: "/media/MP_movieDB/影视库" });
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

      function numberField(label, key, min, max) {
        /* 创建数字配置控件。 */
        return h("label", { class: "cd2-trigger-field" }, [
          h("span", label),
          h("input", {
            type: "number", min, max, value: config[key],
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

      onMounted(() => {
        /* 确保旧版本配置缺少规则数组时仍可编辑。 */
        if (!Array.isArray(config.rules)) config.rules = [];
      });

      return () => h("form", { class: "cd2-trigger-config", onSubmit: (event) => { event.preventDefault(); save(); } }, [
        h("div", { class: "cd2-trigger-title" }, "CD2 上传触发 115 STRM"),
        h("div", { class: "cd2-trigger-subtitle" }, "监听 CloudDrive2 上传完成状态，只为命中目录规则的媒体文件生成精确增量 STRM。"),
        h("div", { class: "cd2-trigger-card" }, [
          checkField("启用插件", "enabled"),
          h("div", { class: "cd2-trigger-grid" }, [
            field("CD2 gRPC 地址", "cd2_endpoint", "http://172.17.0.1:19798"),
            field("CD2 API Token", "cd2_token", "仅填写 Token，不要写 Bearer", true),
            field("MoviePilot 地址", "moviepilot_url", "http://127.0.0.1:3001"),
            field("MoviePilot API Key（可选）", "moviepilot_api_key", "留空则使用系统 API_TOKEN", true),
          ]),
          h("div", { class: "cd2-trigger-hint" }, "CD2 Token 需要开启“获取传输任务”和“接收推送消息”权限。MoviePilot API Key 留空时，插件会尝试使用当前实例的系统 API_TOKEN。"),
        ]),
        h("div", { class: "cd2-trigger-card" }, [
          h("div", { class: "cd2-trigger-row" }, [h("strong", "目录映射规则"), h("button", { type: "button", class: "cd2-trigger-btn", onClick: addRule }, "添加规则")]),
          h("div", { class: "cd2-trigger-hint" }, "每条规则把 CD2 的目标路径转换成 115 网盘路径和本地 STRM 根目录；匹配采用目录边界，不会把 /电影2 误判为 /电影。"),
          ...config.rules.map((rule, index) => h("div", { class: "cd2-trigger-rule", key: index }, [
            h("div", { class: "cd2-trigger-rule-head" }, [h("span", `规则 ${index + 1}`), h("button", { type: "button", class: "cd2-trigger-btn danger", onClick: () => removeRule(index) }, "删除")]),
            h("label", { class: "cd2-trigger-check" }, [h("input", { type: "checkbox", checked: !!rule.enabled, onChange: (event) => { rule.enabled = event.target.checked; } }), h("span", "启用此规则")]),
            h("div", { class: "cd2-trigger-grid" }, [
              h("label", { class: "cd2-trigger-field" }, [h("span", "规则名称"), h("input", { value: rule.name || "", onInput: (event) => { rule.name = event.target.value; } })]),
              h("label", { class: "cd2-trigger-field" }, [h("span", "CD2 目标目录前缀"), h("input", { value: rule.cd2_prefix || "", placeholder: "/CloudNAS/115/影视库", onInput: (event) => { rule.cd2_prefix = event.target.value; } })]),
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
          ]),
          checkField("启动时仅建立基线，不处理已有完成任务", "baseline_on_start"),
          checkField("生成后自动刮削元数据", "scrape_metadata"),
          checkField("生成后刷新媒体服务器", "media_server_refresh"),
          checkField("自动下载媒体元数据", "auto_download_mediainfo"),
          checkField("发送生成结果通知", "notify"),
          h("div", { class: "cd2-trigger-hint" }, "状态监听优先使用 PushMessage，轮询作为断线兜底；任务会按最多 100 个一批提交给 115 助手。"),
        ]),
        message.value ? h("div", { class: `cd2-trigger-message${messageError.value ? " cd2-trigger-error" : ""}` }, message.value) : null,
        h("div", { class: "cd2-trigger-actions" }, [
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

      onMounted(() => {
        loadStatus();
        timer = setInterval(loadStatus, 10000);
      });
      onUnmounted(() => { if (timer) clearInterval(timer); });

      return () => {
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
              stat("待生成", status.value.pending_count),
              stat("已处理", status.value.processed_count),
              stat("轮询次数", status.value.poll_count),
            ]),
          ]),
          h("div", { class: "cd2-trigger-card" }, [
            h("strong", "最近一次生成"),
            h("div", { class: "cd2-trigger-row" }, [
              h("span", `成功：${last.success_count ?? 0}`),
              h("span", `失败：${last.fail_count ?? 0}`),
              h("span", `元数据：${last.download_success_count ?? 0}`),
              h("span", { class: "cd2-trigger-muted" }, status.value.last_trigger_at || "暂无记录"),
            ]),
          ]),
          status.value.last_error ? h("div", { class: "cd2-trigger-message cd2-trigger-error" }, status.value.last_error) : null,
          message.value ? h("div", { class: "cd2-trigger-message" }, message.value) : null,
          h("div", { class: "cd2-trigger-actions" }, [
            h("button", { class: "cd2-trigger-btn", disabled: loading.value, onClick: loadStatus }, loading.value ? "刷新中…" : "刷新状态"),
            h("button", { class: "cd2-trigger-btn primary", disabled: triggering.value, onClick: trigger }, triggering.value ? "触发中…" : "立即检查上传"),
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
