# CD2 上传触发 115 STRM

这个插件监听 CloudDrive2 的上传任务，在插件启动完成第一次状态扫描后，只有新变为 `Finish` 的任务才会处理：媒体文件调用 `P115StrmHelper` 的文件级 STRM API，字幕文件由本插件从 CD2 下载到本地。

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

- `CD2 目标目录前缀`：CloudDrive2 上传任务 `destPath` 的监控范围，只匹配该目录及子目录。
- `115 网盘路径前缀`：115 网盘媒体库根目录，用于构造 STRM 请求里的 `pan_path`。
- `本地 STRM 根目录`：MoviePilot/Emby 能看到的本地媒体根目录，STRM 和字幕下载到这里。

例如：

```text
CD2:   /CloudNAS/115/影视库/电影/a.mkv
115:   /影视库/电影/a.mkv
本地:  /media/MP_movieDB/影视库/电影/a.mkv 对应的 STRM/字幕位置
```

## 监听策略

- `PushMessage` 中的 `UPLOADER_COUNT` 和 `uploadFileStatusChanges` 用于快速响应。
- `GetUploadFileCount` 和 `GetUploadFileList` 按轮询间隔执行，用于断线补偿。
- 启动后的第一次成功扫描固定只建立状态基线，扫描到的已有 `Finish` 任务不会处理；后续新出现的完成状态才会触发。
- 媒体扩展名默认用于生成 STRM；字幕扩展名默认为 `srt,ssa,ass,vtt,sub,idx`，只下载字幕，不生成 STRM。
- 字幕由独立单线程按“字幕下载间隔”串行处理，默认每次请求至少间隔 3 秒；失败最多自动重试 3 次。
- 任务键会持久化，STRM 单批最多提交 100 个文件。

## 生成后的动作由谁执行

- `由 115 STRM 助手刮削元数据`：由 115 STRM 助手调用 MoviePilot 的元数据刮削链路执行，不是 Emby MediaInfoKeeper。
- `由 115 STRM 助手刷新媒体服务器`：由 115 STRM 助手调用其媒体服务器刷新逻辑，作用是让媒体服务器重新扫描/刷新路径，不负责提取媒体流信息。
- `由 115 STRM 助手下载 .nfo/.jpg 等媒体元数据`：由 115 STRM 助手的 MediaInfoDownloader 按自身 `user_download_mediaext` 配置执行。本插件不会把字幕任务提交给这个流程，因此与本插件字幕下载不冲突。
- `发送 STRM 生成结果通知`：本插件调用 MoviePilot 的 `post_message`，使用 MoviePilot 已配置的通知渠道，例如 Telegram；字幕下载不会逐个发送通知。
- 本插件的字幕下载与 115 助手的“媒体元数据下载”是两条独立流程。如果 115 助手也配置了字幕扩展名，可能重复下载，建议字幕只由本插件负责。

## CD2 Token 权限

监听任务需要“获取传输任务”和“接收推送消息”；下载字幕还需要文件读取相关权限，包括列出文件、读取文件/查看属性，以及对应的 HTTP 下载能力。
