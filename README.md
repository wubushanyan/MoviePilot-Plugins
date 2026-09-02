# CD2 上传触发 115 STRM

MoviePilot V2 插件：监听 CloudDrive2 新完成任务，按配置的多个目录规则调用 115 网盘 STRM 助手生成增量 STRM，并将字幕文件限速下载到本地。

## 项目结构

- `package.v2.json`：MoviePilot V2 本地插件市场元数据
- `plugins.v2/cd2uploadstrmtrigger/`：插件后端、CloudDrive2 协议客户端和 Vue 联邦组件
- `tests/`：路径映射与任务转换测试

## 工作方式

- 通过 CloudDrive2 `PushMessage` 接收上传任务变化
- 通过 `GetUploadFileCount`、`GetUploadFileList` 轮询补偿断线期间的任务
- 启动后的第一次成功扫描只建立基线，不处理当前已经是 `Finish` 的任务
- 后续只处理新变为 `Finish` 且命中监控目录的文件
- 媒体文件去重后批量调用 `P115StrmHelper/api_strm_sync_creata`，并显式禁止 115 助手逐文件刷新；如果开启 Emby 刷新，媒体 STRM、外挂字幕下载和删除同步会进入同一个防抖窗口，由本插件向每个已配置的 Emby 服务发送一次刷新 API 请求
- `srt,ssa,ass,vtt,sub,idx,sup` 等字幕由独立线程从 CD2 下载，按配置的最小间隔串行限速，并在下载前确认文件大小稳定
- 可选同步 CD2 删除：删除监控目录中的媒体文件或字幕时，删除本地对应 STRM/字幕；只清理确实为空的目录，不递归删除其他内容

配置页内置“使用说明”，会解释 CD2 前缀、115 前缀、本地根目录、删除同步，以及 115 STRM 助手和本插件分别执行的附加动作。

## 发布到 GitHub 并由插件市场在线安装

本仓库已经按 MoviePilot V2 的在线市场结构整理好。创建一个公开 GitHub 仓库
`MoviePilot-Plugins`，将本目录的 `main` 分支推送到仓库根目录即可；后续插件继续放在同一个
仓库中。

MoviePilot V2 会读取仓库根目录的 `package.v2.json`，并从
`plugins.v2/cd2uploadstrmtrigger/` 下载插件；当前索引未声明 `release: true`，因此不需要创建
GitHub Release。

在 MP 中打开“插件 → 插件市场设置”，将仓库地址加入 `PLUGIN_MARKET`，例如：

```text
https://github.com/wubushanyan/MoviePilot-Plugins
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
