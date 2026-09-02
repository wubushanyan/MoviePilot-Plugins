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

## 发布到 GitHub 并由插件市场在线安装

本仓库已经按 MoviePilot V2 的在线市场结构整理好。创建一个公开 GitHub 仓库（建议名称
`cd2-upload-strm-trigger`），将本目录的 `main` 分支推送到仓库根目录即可。

MoviePilot V2 会读取仓库根目录的 `package.v2.json`，并从
`plugins.v2/cd2uploadstrmtrigger/` 下载插件；当前索引未声明 `release: true`，因此不需要创建
GitHub Release。

在 MP 中打开“插件 → 插件市场设置”，将仓库地址加入 `PLUGIN_MARKET`，例如：

```text
https://github.com/daimon3332/cd2-upload-strm-trigger
```

多个仓库用英文逗号分隔。首次切换到在线版本前，先移除本地插件仓库配置
`/media/MP_movieDB/local-plugins`，再从市场安装或强制更新本插件；移除配置不会删除这个 Git
仓库。

后续更新时，同时修改下面两处版本号并提交推送到 `main`：

- `package.v2.json` 中的 `version`
- `plugins.v2/cd2uploadstrmtrigger/__init__.py` 中的 `plugin_version`

然后在 MP 刷新插件市场，点击更新即可。

## 本地部署说明

当前 MoviePilot 容器只挂载宿主机 `/media`，因此本目录是 Git 源码仓库；MP 使用的本地部署副本仍在：

```text
/media/MP_movieDB/local-plugins
```

修改本仓库后，需要将对应文件同步到部署副本，再通过 MoviePilot 的本地插件安装/刷新流程部署。
