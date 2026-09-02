# CD2 上传触发 115 STRM

这个插件监听 CloudDrive2 的上传任务，在任务状态变为 `Finish` 后，按目录映射调用 `P115StrmHelper` 的文件级 STRM API。

## 目录规则

每条规则包含三段：

```text
CD2 目标目录前缀 -> 115 网盘路径前缀 -> 本地 STRM 根目录
```

例如：

```text
/CloudNAS/115/影视库 -> /影视库 -> /media/MP_movieDB/影视库
```

前端会分别填写这三个字段。插件会使用 `destPath` 的相对路径构造 `pan_path`，并将 `local_path`、`pan_media_path` 一并提交给 115 助手。

## 监听策略

- `PushMessage` 中的 `UPLOADER_COUNT` 和 `uploadFileStatusChanges` 用于快速响应。
- `GetUploadFileCount` 和 `GetUploadFileList` 按轮询间隔执行，用于断线补偿。
- 只有 `UploadFileInfo.Status.Finish` 且目标路径命中规则、文件扩展名属于媒体扩展名时才会触发。
- 任务键会持久化，单批最多提交 100 个文件，失败任务最多自动重试 3 次。
