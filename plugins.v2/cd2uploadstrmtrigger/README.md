# CD2 上传触发 115 STRM

前端与市场元数据版本：`v0.8.0`。

插件监听 CloudDrive2 的上传任务和文件变更：媒体文件交给 `P115StrmHelper` 生成增量 STRM，字幕文件由本插件从 CD2 下载到本地；可选统一刷新 Emby、同步删除和发送生成结果通知。状态页会保留最近至少 10 条分类事件，设置页按功能拆分为多个子页。

## 设置页导航

设置页分为五个子页，可用顶部页签或“上一页 / 下一页”切换，避免所有选项堆在一张长表单中：

1. **连接与监听**：CD2/MoviePilot 地址、令牌、启用开关、Push 主触发和轮询兜底。
2. **目录规则**：规则增删和 CD2 → 115 → 本地三段路径映射。
3. **文件与限速**：批处理、分页、媒体/字幕扩展名、字幕下载间隔和稳定等待。
4. **生成后动作**：刮削、媒体元数据下载、通知、Emby 刷新防抖和删除同步。
5. **使用说明**：流程、路径、权限和动作归属的内置说明。

保存、关闭、测试连接、手动测试和规则增删仍保留；令牌输入使用密码控件，不在页面中硬编码令牌或主机敏感信息。

## 监听策略

- `PushMessage` 是主触发方式，包含 `UPLOADER_COUNT`、`uploadFileStatusChanges` 和文件系统 CREATE/RENAME 事件。
- `poll_fallback_enabled` 默认关闭。启动时只建立一次状态基线，Push 为主，只有数量变化按需补扫、手动检查或开启兜底时才轮询；开启兜底后才使用 `GetUploadFileCount` / `GetUploadFileList` 做断线补偿。
- 关闭轮询兜底不会关闭 Push，也不会把启动前已经是 `Finish` 的任务重新处理；后续新变为 `Finish` 且命中目录规则的文件才会进入处理流程。
- 上传数量变化会触发多次快速补扫，降低小文件在监听间隔内完成而漏掉的概率；任务键会持久化，STRM 单批最多提交 100 个文件。

## 目录规则

每条规则包含三段，三段保持同一相对目录结构：

```text
CD2 目标目录前缀 -> 115 网盘路径前缀 -> 本地 STRM 根目录
```

推荐示例：

```text
/影视库（对应 CD2 目标 /115/影视库） -> /影视库 -> /media/MP_movieDB/影视库
```

- **CD2 目标目录前缀**：`destPath` 的监控范围，只匹配该目标目录及子目录；支持挂载路径、目标路径和 API 路径归一化，例如 `/CloudNAS/115/影视库`、`/115/影视库`、`/影视库`。CD2 备份源 `/Sort` 不属于插件监控前缀。
- **115 网盘路径前缀**：用于构造 STRM 请求的 `pan_path`，例如 `/影视库`；这里填写 115 助手使用的网盘相对路径，不要把 CD2 Token 的 `/115` 根目录再次拼进去。
- **本地 STRM 根目录**：MoviePilot/Emby 读取 STRM 和字幕的本地根目录，两类文件按相同相对目录落盘。

例如：

```text
CD2:   /115/影视库/电影/a.mkv（/Sort 是备份源目录）
115:   /影视库/电影/a.mkv
本地:  /media/MP_movieDB/影视库/电影/a.strm 与对应字幕
```

`/Sort` 源文件删除属于非监控事件，已忽略，不会显示为错误；只有监控目录中的删除事件才会按 `delete_sync` 开关同步本地 STRM/字幕。

## 状态页与事件历史

状态页分为“总览 / 事件 / 说明”：

- **总览**：连接和监听模式、任务/队列/处理统计、最近 CD2 事件、生成、元数据、字幕、删除同步、Emby 刷新和错误摘要。主要卡片都提供“去设置”。
- **事件**：从后端 `event_history` 按时间倒序显示最近 10 条，分类使用中文标签和颜色。支持 `cd2_event`、`generate_event`、`delete_event`、`refresh_event`、`metadata_event`、`subtitle_event`。
- **事件详情**：点击事件即可折叠/展开，查看 `id`、`at`、`category`、`level`、`title`、`message`、`source`、`status`、原始 `raw_dest_path`、规范化 `path` 和 `details`，并可直接去设置。

## 生成、字幕、Emby 和删除

- **媒体生成**：媒体扩展名命中后调用 115 STRM 助手，不下载原媒体文件；助手可按自身配置刮削和下载 `.nfo`、图片等媒体元数据。
- **字幕下载**：默认扩展名为 `srt,ssa,ass,vtt,sub,idx,sup`，独立单线程串行下载；按“字幕下载间隔”限速，并在下载前等待、连续读取两次文件大小确认稳定，失败按后端策略重试。
- **Emby 刷新**：开启后，媒体 STRM 生成成功、字幕下载成功或删除同步成功都会进入同一个防抖窗口；窗口结束后每个已配置 Emby 只发送一次刷新请求。
- **删除同步**：默认关闭。开启后仅删除监控目录中对应的本地字幕/STRM，并逐级清理确实为空的目录，不递归删除其他文件。
- **通知**：由本插件调用 MoviePilot 已配置的通知渠道发送批次结果，不逐个发送字幕通知。

## 配置字段

配置字段保持兼容：

```text
enabled, cd2_endpoint, cd2_token, cd2_api_root, moviepilot_url,
moviepilot_api_key, rules[], poll_interval, batch_window, page_size,
poll_fallback_enabled, include_extensions, subtitle_extensions,
subtitle_interval, subtitle_stability_delay, emby_refresh_debounce,
delete_sync, scrape_metadata, media_server_refresh,
auto_download_mediainfo, notify
```

## API 与权限

前端继续调用既有接口：

```text
GET  /plugin/Cd2UploadStrmTrigger/status
POST /plugin/Cd2UploadStrmTrigger/test
POST /plugin/Cd2UploadStrmTrigger/trigger
```

`status` 新增 `event_history`、`push_primary`、`poll_fallback_enabled`，并保留原有统计、`last_trigger`、Emby、字幕和删除字段。CD2 Token 需要“获取传输任务”和“接收推送消息”；下载字幕还需要列出文件、读取文件、查看属性以及对应的 HTTP 下载能力。API 根目录必须填写 Token 的 `RootDirectory`，例如 Token 为 `/115` 就填写 `/115`。
