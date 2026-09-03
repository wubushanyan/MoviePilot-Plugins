# CD2 上传触发 115 STRM

MoviePilot V2 插件（前端与市场元数据 v0.8.0）：以 CloudDrive2 `PushMessage` 为主触发，按目录规则调用 115 STRM 助手生成增量 STRM，并将字幕限速下载到本地；可选统一刷新 Emby、同步删除和发送生成结果通知。

## 项目结构

- `package.v2.json`：MoviePilot V2 本地插件市场元数据与版本历史
- `plugins.v2/cd2uploadstrmtrigger/`：插件后端、CloudDrive2 协议客户端和 Vue 联邦组件
- `tests/`：路径映射与任务转换测试

## v0.8.0 的界面与监听策略

- 状态页拆成“总览 / 事件 / 说明”三个子页。总览用紧凑卡片展示连接、监听模式、任务队列、生成、字幕、元数据、删除、Emby 和错误摘要。
- 状态页读取后端 `event_history`，默认按时间倒序显示最近 10 条；每条事件可展开查看 `id`、时间、分类、级别、标题、消息、来源、状态、原始 `destPath`、规范化 `path` 和 `details`，并可直接去设置。
- 事件分类包括 `cd2_event`、`generate_event`、`delete_event`、`refresh_event`、`metadata_event`、`subtitle_event`，不同分类使用不同颜色；`/Sort` 源文件删除属于非监控事件，已忽略，不显示为错误。
- 设置页拆成“连接与监听 / 目录规则 / 文件与限速 / 生成后动作 / 使用说明”五个子页，保留测试连接、保存、关闭、规则增删和立即检查等原有交互。
- `PushMessage` 是主触发。`poll_fallback_enabled` 默认关闭；启动只建立状态基线，Push 为主，只有数量变化按需补扫、手动检查或开启兜底才轮询。关闭兜底不会处理启动前已有的 `Finish` 任务。

## 工作方式

- 通过 CloudDrive2 `PushMessage` 接收上传任务变化和文件系统 CREATE/RENAME 事件。
- 开启轮询兜底后，使用 `GetUploadFileCount`、`GetUploadFileList` 补偿断线期间的任务；上传数量变化仍可按需触发快速补扫。
- 启动后的第一次成功扫描只建立基线，不处理当前已经是 `Finish` 的任务；后续只处理新变为 `Finish` 且命中监控目录的文件。
- 媒体文件去重后批量调用 `P115StrmHelper/api_strm_sync_creata`，并显式禁止 115 助手逐文件刷新。若开启 Emby 刷新，媒体 STRM、外挂字幕下载和删除同步会进入同一个防抖窗口，由本插件向每个已配置的 Emby 服务发送一次刷新请求。
- `srt,ssa,ass,vtt,sub,idx,sup` 等字幕由独立线程从 CD2 下载，按配置的最小间隔串行限速，并在下载前确认文件大小稳定。
- 可选同步 CD2 删除：只处理监控目录中对应的本地字幕/STRM，并只清理确实为空的目录，不递归删除其他内容。`/Sort` 源文件删除属于非监控事件，已忽略。

## 目录规则

每条规则包含三段映射：

```text
CD2 目标目录前缀 -> 115 网盘路径前缀 -> 本地 STRM 根目录
```

常见示例：

```text
/影视库（对应 CD2 目标 /115/影视库） -> /影视库 -> /media/MP_movieDB/影视库
```

三段可以使用同一相对目录结构。插件会将任务的 `destPath` 相对于 CD2 目标前缀转换为 115 `pan_path`，STRM 与字幕则落在本地根目录下的相同相对位置。CD2 前缀支持挂载路径、目标路径和 API 路径归一化，例如 `/CloudNAS/115/影视库`、`/115/影视库`、`/影视库`。`/Sort` 是 CD2 备份源目录，不应填写为插件监控前缀。

配置字段保持兼容：`enabled`、`cd2_endpoint`、`cd2_token`、`cd2_api_root`、`moviepilot_url`、`moviepilot_api_key`、`rules`、`poll_interval`、`batch_window`、`page_size`、`poll_fallback_enabled`、`include_extensions`、`subtitle_extensions`、`subtitle_interval`、`subtitle_stability_delay`、`emby_refresh_debounce`、`delete_sync`、`scrape_metadata`、`media_server_refresh`、`auto_download_mediainfo`、`notify`。

## API 与权限

前端继续使用既有接口：

- `GET /plugin/Cd2UploadStrmTrigger/status`
- `POST /plugin/Cd2UploadStrmTrigger/test`
- `POST /plugin/Cd2UploadStrmTrigger/trigger`

状态响应新增 `event_history`、`push_primary`、`poll_fallback_enabled`，并保留既有统计、`last_trigger`、Emby、字幕和删除字段。CD2 Token 需要“获取传输任务”和“接收推送消息”权限；下载字幕还需要列出文件、读取文件、查看属性以及对应的 HTTP 下载能力。API 根目录必须与 Token 的 `RootDirectory` 一致，例如令牌为 `/115` 就填写 `/115`。

## 发布到 GitHub 并由插件市场在线安装

本仓库已经按 MoviePilot V2 的在线市场结构整理好。创建公开 GitHub 仓库 `MoviePilot-Plugins`，将本目录的 `main` 分支推送到仓库根目录即可；后续插件继续放在同一个仓库中。

MoviePilot V2 会读取仓库根目录的 `package.v2.json`，并从 `plugins.v2/cd2uploadstrmtrigger/` 下载插件；当前索引未声明 `release: true`，因此不需要创建 GitHub Release。

在 MP 中打开“插件 → 插件市场设置”，将仓库地址加入 `PLUGIN_MARKET`，例如：

```text
https://github.com/wubushanyan/MoviePilot-Plugins
```

多个仓库用英文逗号分隔。首次切换到在线版本前，先移除本地插件仓库配置 `/media/MP_movieDB/local-plugins`，再从市场安装或强制更新本插件；移除配置不会删除这个 Git 仓库。

后续更新时，至少同步修改 `package.v2.json` 中的 `version`、历史说明和前端联邦入口；若发布流程同时维护后端版本字段，再按同一版本同步后端元数据。

## 本地部署说明

当前 MoviePilot 容器只挂载宿主机 `/media`，因此本目录是 Git 源码仓库；MP 使用的本地部署副本仍在：

```text
/media/MP_movieDB/local-plugins
```

修改本仓库后，需要将对应文件同步到部署副本，再通过 MoviePilot 的本地插件安装/刷新流程部署。本次任务只修改源码、前端联邦入口和版本文档，不执行部署、重启、提交或推送。
