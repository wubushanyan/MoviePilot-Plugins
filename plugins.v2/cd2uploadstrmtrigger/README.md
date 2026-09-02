# CD2 上传触发 115 STRM

这个插件监听 CloudDrive2 的上传任务，在插件启动完成第一次状态扫描后，只有新上传或新建的文件才会处理：媒体文件调用 `P115StrmHelper` 的文件级 STRM API，字幕文件由本插件从 CD2 下载到本地；可选地在每批 STRM 生成成功后由本插件统一刷新 Emby。

## 目录规则

每条规则包含三段，三段必须是同一相对目录结构的映射：

```text
CD2 目标目录前缀 -> 115 网盘路径前缀 -> 本地 STRM 根目录
```

例如：

```text
/CloudNAS/115/影视库 -> /影视库 -> /media/MP_movieDB/影视库
```

前端会分别填写这三个字段。插件会使用 `destPath` 相对于 CD2 前缀的相对路径构造 `pan_path`；STRM 和字幕都按这个相对路径放置。

- `CD2 目标目录前缀`：CloudDrive2 上传任务 `destPath` 的监控范围，只匹配该目录及子目录。支持挂载路径、源目录路径和 API 路径，例如 `/CloudNAS/115/影视库`、`/115/影视库`、`/影视库` 会按同一目录匹配。
- `115 网盘路径前缀`：115 网盘媒体库根目录，用于构造 STRM 请求里的 `pan_path`。
- `本地 STRM 根目录`：MoviePilot/Emby 能看到的本地媒体根目录，STRM 和字幕下载到这里。
- `CD2 API 根目录`：填写 CD2 API Token 的 `RootDirectory`，本例为 `/115`。插件会自动去掉这个根目录后调用 CD2 文件 API。

例如：

```text
CD2:   /CloudNAS/115/影视库/电影/a.mkv
115:   /影视库/电影/a.mkv
本地:  /media/MP_movieDB/影视库/电影/a.mkv 对应的 STRM/字幕位置
```

## 监听策略

- `PushMessage` 中的 `UPLOADER_COUNT` 和 `uploadFileStatusChanges` 用于快速响应，`operatorType=RemoteUpload`（网页/公网远程上传）不再依赖局域网挂载路径。
- `PushMessage` 中的 `FILE_SYSTEM_CHANGE` 的 CREATE/RENAME 文件事件也会直接进入处理流程，用来捕获已经从上传任务列表消失的瞬时文件。
- `GetUploadFileCount` 和 `GetUploadFileList` 按轮询间隔执行，用于断线补偿。
- 每次收到上传数量变化会额外执行 0.2、0.6、1.2、2.5 秒快速补扫，降低小文件在轮询间隔内完成而漏掉的概率。
- 启动后的第一次成功扫描固定只建立状态基线，扫描到的已有 `Finish` 任务不会处理；后续新出现的完成状态才会触发。
- 媒体扩展名默认用于生成 STRM；字幕扩展名默认为 `srt,ssa,ass,vtt,sub,idx,sup`，只下载字幕，不生成 STRM。
- 字幕由独立单线程按“字幕下载间隔”串行处理，默认先等待 3 秒，再连续读取两次 CD2 文件大小确认稳定后下载；失败最多自动重试 3 次。
- 任务键会持久化，STRM 单批最多提交 100 个文件。

插件日志会记录 `messageType`、原始 `destPath`、`operatorType`（包括 `RemoteUpload`）、`statusEnum`、路径匹配结果和入队结果；排查时搜索 `CD2 STRM触发器` 即可。

## 生成后的动作由谁执行

- `由 115 STRM 助手刮削元数据`：由 115 STRM 助手调用 MoviePilot 的元数据刮削链路执行，不是 Emby MediaInfoKeeper。
- `由本插件刷新 Emby（每批一次）`：不再把刷新开关交给 115 STRM 助手。每批 STRM 全部生成成功后，本插件通过 MoviePilot 已配置的 Emby 服务发送一次 `Library/Refresh` 请求；一批最多 100 个媒体文件，因此不会按文件逐个请求。字幕下载不会触发刷新。
- `由 115 STRM 助手下载 .nfo/.jpg 等媒体元数据`：由 115 STRM 助手的 MediaInfoDownloader 按自身 `user_download_mediaext` 配置执行。本插件不会把字幕任务提交给这个流程，因此与本插件字幕下载不冲突。
- `发送 STRM 生成结果通知`：本插件调用 MoviePilot 的 `post_message`，使用 MoviePilot 已配置的通知渠道，例如 Telegram；字幕下载不会逐个发送通知。
- 本插件的字幕下载与 115 助手的“媒体元数据下载”是两条独立流程。如果 115 助手也配置了字幕扩展名，可能重复下载，建议字幕只由本插件负责。

## CD2 Token 权限

监听任务需要“获取传输任务”和“接收推送消息”；下载字幕还需要文件读取相关权限，包括列出文件、读取文件/查看属性，以及对应的 HTTP 下载能力。
