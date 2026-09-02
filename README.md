# CD2 上传触发 115 STRM

MoviePilot V2 插件：监听 CloudDrive2 上传任务完成事件，按配置的多个目录规则调用 115 网盘 STRM 助手生成增量 STRM。

## 项目结构

- `package.v2.json`：MoviePilot V2 本地插件市场元数据
- `plugins.v2/cd2uploadstrmtrigger/`：插件后端、CloudDrive2 协议客户端和 Vue 联邦组件
- `tests/`：路径映射与任务转换测试

## 工作方式

- 通过 CloudDrive2 `PushMessage` 接收上传任务变化
- 通过 `GetUploadFileCount`、`GetUploadFileList` 轮询补偿断线期间的任务
- 只处理状态为 `Finish` 且命中监控目录的媒体文件
- 去重后批量调用 `P115StrmHelper/api_strm_sync_creata`

## 部署说明

当前 MoviePilot 容器只挂载宿主机 `/media`，因此本目录是 Git 源码仓库；MP 使用的部署副本仍在：

```text
/media/MP_movieDB/local-plugins
```

修改本仓库后，需要将对应文件同步到部署副本，再通过 MoviePilot 的本地插件安装/刷新流程部署。
