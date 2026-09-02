"""CloudDrive2 上传完成后触发 115 STRM 生成的 MoviePilot V2 插件。"""

from __future__ import annotations

import posixpath
import threading
import time
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import Body

from app import schemas
from app.core.config import settings
from app.core.event import Event, eventmanager
from app.helper.mediaserver import MediaServerHelper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType

from .cd2_client import CloudDrive2Client
from clouddrive2_client.proto import clouddrive_pb2 as cd2_pb2


class Cd2UploadStrmTrigger(_PluginBase):
    """监听 CD2 上传完成任务并调用 115 STRM 助手生成精确增量 STRM。"""

    plugin_name = "CD2 上传触发 115 STRM"
    plugin_desc = "监听 CloudDrive2 挂载/RemoteUpload 上传和文件变更，媒体调用 115 网盘 STRM 助手生成增量 STRM，字幕按限速下载到本地，并可按批次刷新 Emby。"
    plugin_icon = "https://raw.githubusercontent.com/cloud-fs/clouddrive-mediaserver-plugin/main/icon.png"
    plugin_version = "0.4.0"
    plugin_author = "wubushanyan"
    author_url = "https://github.com/wubushanyan"
    plugin_config_prefix = "cd2uploadstrmtrigger_"
    plugin_order = 98
    auth_level = 1

    DATA_KEY_PROCESSED = "processed_task_keys"
    FINISH_STATUS = int(cd2_pb2.UploadFileInfo.Finish)
    UPLOADER_MESSAGE = int(cd2_pb2.CloudDrivePushMessage.UPLOADER_COUNT)
    FILE_SYSTEM_MESSAGE = int(cd2_pb2.CloudDrivePushMessage.FILE_SYSTEM_CHANGE)
    FILE_CREATE = int(cd2_pb2.FileSystemChange.CREATE)
    FILE_RENAME = int(cd2_pb2.FileSystemChange.RENAME)
    RAPID_RESCAN_DELAYS = (0.2, 0.6, 1.2, 2.5)
    PAYLOAD_DEDUP_SECONDS = 60.0
    SUBTITLE_STABILITY_PROBE_INTERVAL = 1.0

    DEFAULT_EXTENSIONS = (
        "mkv,mp4,ts,avi,mov,m4v,wmv,flv,m2ts,iso,rmvb,webm,mpeg,mpg,3gp,asf,tp,f4v"
    )
    DEFAULT_SUBTITLE_EXTENSIONS = "srt,ssa,ass,vtt,sub,idx,sup"
    DEFAULT_SUBTITLE_INTERVAL = 3.0

    def __init__(self):
        """初始化插件运行时状态。"""
        super().__init__()
        self._config: Dict[str, Any] = self._default_config()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._ready_event = threading.Event()
        self._rapid_rescan_event = threading.Event()
        self._state_lock = threading.RLock()
        self._pending_lock = threading.RLock()
        self._scan_lock = threading.Lock()
        self._push_client: Optional[CloudDrive2Client] = None
        self._threads: List[threading.Thread] = []
        self._task_states: Dict[str, int] = {}
        self._pending: Dict[str, Dict[str, Any]] = {}
        self._subtitle_pending: Dict[str, Dict[str, Any]] = {}
        self._processed_keys: set[str] = set()
        self._recent_payloads: Dict[str, float] = {}
        self._subtitle_wake_event = threading.Event()
        self._last_subtitle_request_at = 0.0
        self._stats: Dict[str, Any] = self._new_stats()

    @staticmethod
    def _default_config() -> Dict[str, Any]:
        """返回插件默认配置。"""
        return {
            "enabled": False,
            "cd2_endpoint": "http://172.17.0.1:19798",
            "cd2_token": "",
            "moviepilot_url": "http://127.0.0.1:3001",
            "moviepilot_api_key": "",
            "rules": [],
            "poll_interval": 5,
            "batch_window": 5,
            "page_size": 200,
            "include_extensions": Cd2UploadStrmTrigger.DEFAULT_EXTENSIONS,
            "subtitle_extensions": Cd2UploadStrmTrigger.DEFAULT_SUBTITLE_EXTENSIONS,
            "subtitle_interval": Cd2UploadStrmTrigger.DEFAULT_SUBTITLE_INTERVAL,
            "scrape_metadata": False,
            "media_server_refresh": False,
            "auto_download_mediainfo": False,
            "notify": False,
            "cd2_api_root": "/115",
            "subtitle_stability_delay": 3.0,
        }

    @staticmethod
    def _new_stats() -> Dict[str, Any]:
        """创建运行状态统计对象。"""
        return {
            "running": False,
            "connected": False,
            "last_error": "",
            "last_poll_at": "",
            "last_push_at": "",
            "last_message_at": "",
            "last_message_type": "",
            "last_event_source": "",
            "last_operator_type": "",
            "last_task_status": "",
            "last_dest_path": "",
            "last_event": "",
            "last_trigger_at": "",
            "last_trigger": {},
            "upload_count": 0,
            "task_count": 0,
            "matched_count": 0,
            "pending_count": 0,
            "strm_pending_count": 0,
            "subtitle_pending_count": 0,
            "processed_count": 0,
            "subtitle_success_count": 0,
            "subtitle_fail_count": 0,
            "filesystem_event_count": 0,
            "rapid_rescan_count": 0,
            "ignored_count": 0,
            "emby_refresh_batch_count": 0,
            "emby_refresh_request_count": 0,
            "last_emby_refresh_at": "",
            "last_emby_refresh_servers": [],
            "last_emby_refresh_error": "",
            "last_subtitle_at": "",
            "last_subtitle_file": "",
            "last_subtitle_error": "",
            "poll_count": 0,
        }

    @staticmethod
    def _text(value: Any) -> str:
        """将任意配置值转换为去除首尾空白的字符串。"""
        return str(value or "").strip()

    @staticmethod
    def _int(value: Any, default: int, minimum: int, maximum: int) -> int:
        """将配置值转换为指定范围内的整数。"""
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        return max(minimum, min(number, maximum))

    @staticmethod
    def _float(value: Any, default: float, minimum: float, maximum: float) -> float:
        """将配置值转换为指定范围内的浮点数。"""
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = default
        return max(minimum, min(number, maximum))

    @classmethod
    def _normalize_path(cls, value: Any) -> str:
        """规范化 CD2、115 和本地路径，统一使用正斜杠。"""
        path = cls._text(value).replace("\\", "/")
        if not path:
            return ""
        if not path.startswith("/"):
            path = "/" + path
        path = posixpath.normpath(path)
        return "/" if path == "." else path.rstrip("/") or "/"

    def _canonical_cd2_path(self, value: Any) -> str:
        """将挂载路径、源目录路径和 Token 根目录下的 API 路径统一。"""
        path = self._normalize_path(value)
        if not path:
            return ""
        # /CloudNAS/115/... 是 CD2 挂载点路径；去掉挂载根后变成 /115/...
        mount_root = "/CloudNAS"
        if path == mount_root or path.startswith(mount_root + "/"):
            path = path[len(mount_root) :] or "/"
        # Token RootDirectory=/115 时，API 返回的根目录内容从 / 开始，
        # 因此 /115/影视库 和 /影视库 是同一个 API 文件。
        api_root = self._normalize_path(self._config.get("cd2_api_root") or "/115")
        if api_root != "/" and (
            path == api_root or path.startswith(api_root.rstrip("/") + "/")
        ):
            path = path[len(api_root) :] or "/"
        return self._normalize_path(path)

    @classmethod
    def _normalize_rule(cls, rule: Any) -> Optional[Dict[str, Any]]:
        """规范化一条目录映射规则。"""
        if not isinstance(rule, dict):
            return None
        cd2_prefix = cls._normalize_path(
            rule.get("cd2_prefix") or rule.get("monitor_path") or rule.get("src")
        )
        pan_prefix = cls._normalize_path(
            rule.get("pan_prefix") or rule.get("pan_path") or rule.get("dest")
        )
        local_path = cls._text(rule.get("local_path") or rule.get("local"))
        if not cd2_prefix or not pan_prefix or not local_path:
            return None
        return {
            "name": cls._text(rule.get("name")),
            "enabled": bool(rule.get("enabled", True)),
            "cd2_prefix": cd2_prefix,
            "pan_prefix": pan_prefix,
            "local_path": local_path.rstrip("/") or "/",
        }

    @classmethod
    def _normalize_config(cls, config: Optional[dict]) -> Dict[str, Any]:
        """规范化插件配置并过滤无效目录规则。"""
        raw = config if isinstance(config, dict) else {}
        rules_value = raw.get("rules")
        if rules_value is None:
            rules_value = raw.get("monitor_rules") or []
        if isinstance(rules_value, dict):
            rules_value = list(rules_value.values())
        rules = [cls._normalize_rule(item) for item in (rules_value or [])]
        rules = [item for item in rules if item]
        defaults = cls._default_config()
        normalized = {
            "enabled": bool(raw.get("enabled", raw.get("enable", defaults["enabled"]))),
            "cd2_endpoint": cls._text(raw.get("cd2_endpoint")) or defaults["cd2_endpoint"],
            "cd2_token": cls._text(raw.get("cd2_token")),
            "moviepilot_url": cls._text(raw.get("moviepilot_url")) or defaults["moviepilot_url"],
            "moviepilot_api_key": cls._text(raw.get("moviepilot_api_key")),
            "rules": rules,
            "poll_interval": cls._int(raw.get("poll_interval"), 5, 2, 60),
            "batch_window": cls._int(raw.get("batch_window"), 5, 0, 120),
            "page_size": cls._int(raw.get("page_size"), 200, 20, 1000),
            "include_extensions": cls._text(raw.get("include_extensions"))
            or defaults["include_extensions"],
            "subtitle_extensions": cls._text(raw.get("subtitle_extensions"))
            or defaults["subtitle_extensions"],
            "subtitle_interval": cls._float(
                raw.get("subtitle_interval", raw.get("subtitle_download_interval")),
                defaults["subtitle_interval"],
                0.0,
                60.0,
            ),
            "scrape_metadata": bool(raw.get("scrape_metadata", False)),
            "media_server_refresh": bool(raw.get("media_server_refresh", False)),
            "auto_download_mediainfo": bool(raw.get("auto_download_mediainfo", False)),
            "notify": bool(raw.get("notify", False)),
            "cd2_api_root": cls._normalize_path(
                raw.get("cd2_api_root") or defaults["cd2_api_root"]
            ),
            "subtitle_stability_delay": cls._float(
                raw.get("subtitle_stability_delay"),
                defaults["subtitle_stability_delay"],
                0.0,
                60.0,
            ),
        }
        return normalized

    def _public_config(self) -> Dict[str, Any]:
        """返回前端编辑所需的配置快照。"""
        return {
            key: value
            for key, value in self._config.items()
            if key != "monitor_rules"
        }

    def init_plugin(self, config: dict = None):
        """根据配置启动或停止 CD2 监听服务。"""
        self.stop_service()
        self._config = self._normalize_config(config or {})
        self._task_states = {}
        self._pending = {}
        self._subtitle_pending = {}
        self._recent_payloads = {}
        self._rapid_rescan_event.clear()
        self._last_subtitle_request_at = 0.0
        self._subtitle_wake_event.clear()
        stored_processed = self.get_data(self.DATA_KEY_PROCESSED) or []
        if isinstance(stored_processed, list):
            self._processed_keys = {self._text(item) for item in stored_processed if self._text(item)}
        else:
            self._processed_keys = set()
        self._stats = self._new_stats()
        self._stats["processed_count"] = len(self._processed_keys)
        if not self._config["enabled"]:
            return
        if not self._config["cd2_token"]:
            self._set_error("未配置 CD2 API Token")
            return
        if not self._config["rules"]:
            self._set_error("未配置有效的目录映射规则")
            return
        self._start_workers()

    def get_state(self) -> bool:
        """返回插件是否已启用。"""
        return bool(self._config.get("enabled"))

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """注册手动唤醒 CD2 上传检查的远程命令。"""
        return [
            {
                "cmd": "/cd2_strm_sync",
                "event": EventType.PluginAction,
                "desc": "立即检查 CD2 上传并生成 115 STRM",
                "category": "插件",
                "data": {"action": "cd2_upload_strm_trigger"},
            }
        ]

    @staticmethod
    def get_render_mode() -> Tuple[str, str]:
        """声明插件使用 Vue 联邦组件渲染。"""
        return "vue", "dist/assets"

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """返回 Vue 模式下的默认配置模型。"""
        return [], self._public_config()

    def get_page(self) -> List[dict]:
        """返回空的 Vuetify 页面，由 Vue 联邦组件负责渲染。"""
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        """注册 Vue 页面所需的状态、测试和手动触发 API。"""
        return [
            {
                "path": "/status",
                "endpoint": self.api_status,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取 CD2 STRM 触发器状态",
            },
            {
                "path": "/test",
                "endpoint": self.api_test,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "测试 CD2 连接和上传任务权限",
            },
            {
                "path": "/trigger",
                "endpoint": self.api_trigger,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "手动触发一次 CD2 上传检查",
            },
        ]

    def api_status(self) -> schemas.Response:
        """返回脱敏后的插件运行状态。"""
        return schemas.Response(success=True, data=self._status_snapshot())

    def api_test(self, config: Optional[dict] = Body(default=None)) -> schemas.Response:
        """测试 CD2 API Token、上传任务读取权限和 MoviePilot API 配置。"""
        test_config = self._normalize_config(config or self._config)
        try:
            client = CloudDrive2Client(
                endpoint=test_config["cd2_endpoint"],
                token=test_config["cd2_token"],
                timeout=10,
                page_size=test_config["page_size"],
            )
            system_info = client.get_system_info()
            upload_count = client.get_upload_file_count()
            client.close()
            mp_result = self._test_moviepilot_api(test_config)
            if not mp_result[0]:
                return schemas.Response(success=False, message=mp_result[1])
            return schemas.Response(
                success=True,
                message="CD2 和 115 STRM API 连接测试成功",
                data={
                    "cd2_version": self._text(getattr(system_info, "version", "")),
                    "upload_count": upload_count,
                    "moviepilot": mp_result[1],
                },
            )
        except Exception as exc:
            logger.warning("【CD2 STRM触发器】连接测试失败：%s", exc)
            return schemas.Response(success=False, message=f"连接测试失败：{exc}")

    def api_trigger(self) -> schemas.Response:
        """请求后台立即执行一次上传任务检查。"""
        if not self.get_state():
            return schemas.Response(success=False, message="插件未启用")
        self._wake_event.set()
        return schemas.Response(success=True, message="已请求立即检查 CD2 上传任务")

    @eventmanager.register(EventType.PluginAction)
    def handle_plugin_action(self, event: Event):
        """处理远程命令发出的手动检查事件。"""
        if not event or event.event_data.get("action") != "cd2_upload_strm_trigger":
            return
        self._wake_event.set()

    def _start_workers(self) -> None:
        """启动轮询、推送、STRM 批处理和字幕下载线程。"""
        self._stop_event.clear()
        self._wake_event.clear()
        self._subtitle_wake_event.clear()
        self._ready_event.clear()
        self._stats["running"] = True
        poll_thread = threading.Thread(
            target=self._poll_loop,
            name="Cd2UploadStrmTrigger-Poll",
            daemon=True,
        )
        push_thread = threading.Thread(
            target=self._push_loop,
            name="Cd2UploadStrmTrigger-Push",
            daemon=True,
        )
        dispatch_thread = threading.Thread(
            target=self._dispatch_loop,
            name="Cd2UploadStrmTrigger-Dispatch",
            daemon=True,
        )
        subtitle_thread = threading.Thread(
            target=self._subtitle_loop,
            name="Cd2UploadStrmTrigger-Subtitle",
            daemon=True,
        )
        self._threads = [poll_thread, push_thread, dispatch_thread, subtitle_thread]
        for thread in self._threads:
            thread.start()

    def _poll_loop(self) -> None:
        """定时读取 CD2 上传计数和任务列表，作为推送监听的可靠兜底。"""
        # 启动后的第一次成功读取永远只建立状态基线，不处理列表中已经完成的任务。
        first_scan = True
        while not self._stop_event.is_set():
            try:
                self._scan_and_observe(
                    allow_trigger=not first_scan,
                    source="poll_baseline" if first_scan else "poll",
                )
                if first_scan:
                    first_scan = False
                    self._ready_event.set()
                    # 启动期间收到的推送只属于基线阶段，不处理其中的旧任务。
                    self._rapid_rescan_event.clear()
                elif self._rapid_rescan_event.is_set():
                    self._run_rapid_rescans()
                self._update_pending_count()
            except Exception as exc:
                self._set_error(f"轮询 CD2 上传任务失败：{exc}")
            self._wake_event.wait(timeout=self._config.get("poll_interval", 5))
            self._wake_event.clear()

    def _scan_and_observe(self, allow_trigger: bool, source: str) -> Tuple[int, List[Any]]:
        """读取一次上传列表并记录/处理其中的任务。"""
        with self._scan_lock:
            count, tasks = self._poll_once()
        with self._state_lock:
            self._stats["connected"] = True
            self._stats["last_error"] = ""
            self._stats["last_poll_at"] = self._now()
            self._stats["upload_count"] = count
            self._stats["task_count"] = len(tasks)
            self._stats["poll_count"] += 1
        if tasks or source == "rapid":
            logger.info(
                "【CD2 STRM触发器】%s扫描：当前上传数=%s，任务详情=%s",
                source,
                count,
                len(tasks),
            )
        for task in tasks:
            self._observe_task(task, allow_trigger=allow_trigger, source=source)
        self._update_pending_count()
        return count, tasks

    def _request_rapid_rescan(self) -> None:
        """请求轮询线程在当前周期后执行一组快速补扫。"""
        self._rapid_rescan_event.set()
        self._wake_event.set()

    def _run_rapid_rescans(self) -> None:
        """对瞬时完成的远程上传执行多次短间隔补扫。"""
        if not self._ready_event.is_set():
            return
        self._rapid_rescan_event.clear()
        logger.info(
            "【CD2 STRM触发器】开始快速补扫，间隔=%s 秒",
            ",".join(str(delay) for delay in self.RAPID_RESCAN_DELAYS),
        )
        for delay in self.RAPID_RESCAN_DELAYS:
            if self._stop_event.wait(timeout=delay):
                return
            try:
                self._scan_and_observe(allow_trigger=True, source="rapid")
                with self._state_lock:
                    self._stats["rapid_rescan_count"] += 1
            except Exception as exc:
                self._set_error(f"快速补扫 CD2 上传任务失败：{exc}")
        logger.info("【CD2 STRM触发器】快速补扫结束")

    def _poll_once(self) -> Tuple[int, List[Any]]:
        """执行一次 CD2 上传任务计数和列表读取。"""
        client = CloudDrive2Client(
            endpoint=self._config["cd2_endpoint"],
            token=self._config["cd2_token"],
            timeout=max(5, self._config["poll_interval"] + 5),
            page_size=self._config["page_size"],
        )
        try:
            count = client.get_upload_file_count()
            tasks = client.get_upload_file_list()
            return count, tasks
        finally:
            client.close()

    def _push_loop(self) -> None:
        """订阅 CD2 PushMessage，直接接收上传任务状态变化。"""
        self._ready_event.wait(timeout=20)
        while not self._stop_event.is_set():
            client: Optional[CloudDrive2Client] = None
            try:
                client = CloudDrive2Client(
                    endpoint=self._config["cd2_endpoint"],
                    token=self._config["cd2_token"],
                    timeout=15,
                    page_size=self._config["page_size"],
                )
                with self._state_lock:
                    self._push_client = client
                logger.info("【CD2 STRM触发器】CD2 PushMessage 已连接，监听上传和文件变更事件")
                for message in client.push_messages(self._stop_event):
                    if self._stop_event.is_set():
                        return
                    message_type = int(message.messageType)
                    if message_type not in (self.UPLOADER_MESSAGE, self.FILE_SYSTEM_MESSAGE):
                        continue
                    message_name = self._message_type_name(message_type)
                    with self._state_lock:
                        self._stats["last_push_at"] = self._now()
                        self._stats["last_message_at"] = self._now()
                        self._stats["last_message_type"] = message_name
                        self._stats["last_event"] = message_name
                    if message_type == self.FILE_SYSTEM_MESSAGE:
                        if not message.HasField("fileSystemChange"):
                            logger.warning(
                                "【CD2 STRM触发器】收到 FILE_SYSTEM_CHANGE，但消息没有变更详情"
                            )
                        else:
                            self._observe_file_system_change(message.fileSystemChange)
                        self._request_rapid_rescan()
                        continue
                    has_details = message.HasField("transferTaskStatus")
                    task_count = (
                        len(message.transferTaskStatus.uploadFileStatusChanges)
                        if has_details
                        else 0
                    )
                    logger.info(
                        "【CD2 STRM触发器】收到 CD2 上传推送：messageType=%s(%s)，任务详情=%s",
                        message_name,
                        message_type,
                        task_count,
                    )
                    if not has_details:
                        logger.info(
                            "【CD2 STRM触发器】上传推送只有数量变化，交给快速补扫捕获瞬时任务"
                        )
                    elif not self._ready_event.is_set():
                        # 首次成功轮询完成前不消费推送任务，避免把启动阶段的旧任务
                        # 写入状态表后又在基线扫描时误判为“新完成”。
                        logger.info(
                            "【CD2 STRM触发器】监听器尚未完成基线，本次上传推送仅唤醒轮询"
                        )
                    else:
                        for task in message.transferTaskStatus.uploadFileStatusChanges:
                            self._observe_task(task, allow_trigger=True, source="push")
                    self._request_rapid_rescan()
            except Exception as exc:
                if not self._stop_event.is_set():
                    self._set_error(f"CD2 推送连接断开：{exc}")
                    self._stop_event.wait(timeout=5)
            finally:
                with self._state_lock:
                    if self._push_client is client:
                        self._push_client = None
                if client:
                    client.close()

    def _dispatch_loop(self) -> None:
        """按批次调用 115 STRM API，并对暂时失败的任务进行有限重试。"""
        while not self._stop_event.is_set():
            try:
                self._flush_pending_if_due()
            except Exception as exc:
                self._set_error(f"提交 115 STRM API 失败：{exc}")
            self._stop_event.wait(timeout=1)

    def _subtitle_loop(self) -> None:
        """串行下载字幕，并按配置的最小间隔限制 CD2 请求频率。"""
        while not self._stop_event.is_set():
            with self._pending_lock:
                if not self._subtitle_pending:
                    item = None
                else:
                    key, item = next(iter(self._subtitle_pending.items()))
                    self._subtitle_pending.pop(key, None)
            if item is None:
                self._subtitle_wake_event.wait(timeout=1)
                self._subtitle_wake_event.clear()
                continue

            not_before = float(item.get("not_before", 0) or 0)
            remaining = not_before - time.monotonic()
            if remaining > 0 and self._stop_event.wait(timeout=remaining):
                return
            if not self._wait_for_subtitle_slot():
                return
            self._update_pending_count()
            self._last_subtitle_request_at = time.monotonic()
            key = str(item.get("key") or "")
            payload = item.get("payload") or {}
            try:
                detail = self._download_subtitle(payload)
                if item.get("persist_key", True):
                    self._processed_keys.add(key)
                    self._save_processed_keys()
                with self._state_lock:
                    self._stats["subtitle_success_count"] += 1
                    self._stats["last_subtitle_at"] = self._now()
                    self._stats["last_subtitle_file"] = str(payload.get("local_file") or "")
                    self._stats["last_subtitle_error"] = ""
                    self._stats["last_error"] = ""
                logger.info(
                    "【CD2 STRM触发器】字幕下载成功：%s%s",
                    payload.get("cd2_path") or key,
                    f"（{detail}）" if detail else "",
                )
            except Exception as exc:
                attempts = int(item.get("attempts", 0)) + 1
                with self._state_lock:
                    self._stats["last_subtitle_at"] = self._now()
                    self._stats["last_subtitle_file"] = str(payload.get("local_file") or "")
                    self._stats["last_subtitle_error"] = str(exc)
                    self._stats["last_error"] = f"字幕下载失败：{exc}"
                if attempts < 4:
                    item["attempts"] = attempts
                    item["first_seen"] = time.monotonic()
                    item["not_before"] = time.monotonic() + float(
                        self._config.get("subtitle_stability_delay", 3.0)
                    )
                    with self._pending_lock:
                        self._subtitle_pending[key] = item
                    logger.warning(
                        "【CD2 STRM触发器】字幕下载失败，%s 秒后重试（第 %s 次）：%s；原因：%s",
                        self._config.get("subtitle_interval", self.DEFAULT_SUBTITLE_INTERVAL),
                        attempts,
                        payload.get("cd2_path") or key,
                        exc,
                    )
                else:
                    with self._state_lock:
                        self._stats["subtitle_fail_count"] += 1
                    logger.error(
                        "【CD2 STRM触发器】字幕连续失败，停止自动重试：%s；原因：%s",
                        payload.get("cd2_path") or key,
                        exc,
                    )
            self._update_pending_count()

    def _wait_for_subtitle_slot(self) -> bool:
        """等待到达下一次字幕下载时间点，返回是否可以开始下载。"""
        interval = float(self._config.get("subtitle_interval", self.DEFAULT_SUBTITLE_INTERVAL))
        remaining = interval - (time.monotonic() - self._last_subtitle_request_at)
        if remaining <= 0:
            return True
        self._subtitle_wake_event.wait(timeout=remaining)
        self._subtitle_wake_event.clear()
        return not self._stop_event.is_set() and (
            time.monotonic() - self._last_subtitle_request_at >= interval
        )

    def _observe_task(self, task: Any, allow_trigger: bool, source: str = "poll") -> None:
        """记录任务状态，并在新完成任务命中规则时加入对应处理队列。"""
        raw_destination = self._text(getattr(task, "destPath", ""))
        destination = self._normalize_path(raw_destination)
        operator_value = int(getattr(task, "operatorType", -1))
        status_value = int(getattr(task, "statusEnum", -1))
        operator_name = self._operator_type_name(operator_value)
        status_name = self._status_name(status_value)
        with self._state_lock:
            self._stats["last_event_source"] = source
            self._stats["last_operator_type"] = operator_name
            self._stats["last_task_status"] = status_name
            self._stats["last_dest_path"] = raw_destination
            self._stats["last_event"] = f"{source}:UPLOAD_TASK"
        logger.info(
            "【CD2 STRM触发器】收到 CD2 上传任务：source=%s operatorType=%s(%s) "
            "statusEnum=%s(%s) status=%s destPath=%s size=%s key=%s",
            source,
            operator_name,
            operator_value,
            status_name,
            status_value,
            self._text(getattr(task, "status", "")),
            raw_destination,
            int(getattr(task, "size", 0) or 0),
            self._text(getattr(task, "key", "")),
        )
        key = self._task_key(task)
        if not key:
            self._log_ignored(destination, "任务没有 key 或 destPath")
            return
        previous = self._task_states.get(key)
        self._task_states[key] = status_value
        if not allow_trigger:
            logger.info("【CD2 STRM触发器】基线任务跳过：destPath=%s", destination)
            return
        if status_value != self.FINISH_STATUS:
            return
        if previous == self.FINISH_STATUS:
            logger.info("【CD2 STRM触发器】重复完成状态跳过：destPath=%s", destination)
            return
        built = self._build_file_payload_from_destination(
            destination,
            int(getattr(task, "size", 0) or 0),
        )
        if not built:
            self._log_ignored(destination, self._payload_ignore_reason(destination))
            return
        kind, payload = built
        with self._state_lock:
            self._stats["matched_count"] += 1
        self._enqueue_payload(kind, key, payload, persist_key=True, source=source)

    def _observe_file_system_change(self, change: Any) -> None:
        """处理 CD2 文件系统 CREATE/RENAME 事件，捕获已从上传列表消失的文件。"""
        change_type = int(getattr(change, "changeType", -1))
        change_name = self._file_change_type_name(change_type)
        raw_path = self._text(getattr(change, "path", ""))
        new_path = self._text(getattr(change, "newPath", ""))
        file_info = change.theFile if change.HasField("theFile") else None
        full_path = self._text(getattr(file_info, "fullPathName", "")) if file_info else ""
        destination = self._normalize_path(full_path or new_path or raw_path)
        size = int(getattr(file_info, "size", 0) or 0) if file_info else 0
        is_directory = bool(getattr(change, "isDirectory", False)) or bool(
            getattr(file_info, "isDirectory", False) if file_info else False
        )
        with self._state_lock:
            self._stats["filesystem_event_count"] += 1
            self._stats["last_event_source"] = "filesystem"
            self._stats["last_operator_type"] = "FILE_SYSTEM_CHANGE"
            self._stats["last_task_status"] = change_name
            self._stats["last_dest_path"] = raw_path or destination
            self._stats["last_event"] = "filesystem:" + change_name
        logger.info(
            "【CD2 STRM触发器】收到 CD2 文件系统变更：changeType=%s(%s) "
            "isDirectory=%s path=%s newPath=%s fullPathName=%s size=%s",
            change_name,
            change_type,
            is_directory,
            raw_path,
            new_path,
            full_path,
            size,
        )
        if not self._ready_event.is_set():
            logger.info("【CD2 STRM触发器】监听器尚未完成基线，文件系统变更仅记录不处理")
            return
        if change_type not in (self.FILE_CREATE, self.FILE_RENAME) or is_directory:
            return
        if not destination:
            self._log_ignored(destination, "文件系统事件没有有效文件路径")
            return
        built = self._build_file_payload_from_destination(destination, size)
        if not built:
            self._log_ignored(destination, self._payload_ignore_reason(destination))
            return
        kind, payload = built
        with self._state_lock:
            self._stats["matched_count"] += 1
        file_id = self._text(getattr(file_info, "id", "")) if file_info else ""
        event_key = f"fs:{file_id or destination}|{size}"
        self._enqueue_payload(
            kind,
            event_key,
            payload,
            persist_key=False,
            source="filesystem",
        )

    def _enqueue_payload(
        self,
        kind: str,
        key: str,
        payload: Dict[str, Any],
        persist_key: bool,
        source: str,
    ) -> bool:
        """将媒体或字幕任务入队，并抑制推送/文件变更双通道造成的重复。"""
        now = time.monotonic()
        signature = self._payload_signature(kind, payload)
        with self._pending_lock:
            self._recent_payloads = {
                item_key: item_time
                for item_key, item_time in self._recent_payloads.items()
                if now - item_time < self.PAYLOAD_DEDUP_SECONDS
            }
            if persist_key and key in self._processed_keys:
                logger.info("【CD2 STRM触发器】任务已处理，跳过：source=%s key=%s", source, key)
                return False
            if signature in self._recent_payloads:
                logger.info(
                    "【CD2 STRM触发器】推送/文件变更重复事件跳过：source=%s path=%s",
                    source,
                    payload.get("cd2_path") or payload.get("raw_dest_path") or signature,
                )
                return False
            target_queue = self._pending if kind == "media" else self._subtitle_pending
            if key in target_queue:
                return False
            if any(
                self._payload_signature(kind, item.get("payload") or {}) == signature
                for item in list(self._pending.values()) + list(self._subtitle_pending.values())
            ):
                return False
            item = {
                "key": key,
                "payload": payload,
                "attempts": 0,
                "first_seen": now,
                "persist_key": persist_key,
                "source": source,
            }
            if kind == "subtitle":
                item["not_before"] = now + float(
                    self._config.get("subtitle_stability_delay", 3.0)
                )
            target_queue[key] = item
            self._recent_payloads[signature] = now
        self._update_pending_count()
        logger.info(
            "【CD2 STRM触发器】任务入队：kind=%s source=%s path=%s raw_destPath=%s",
            kind,
            source,
            payload.get("cd2_path") or payload.get("pan_path"),
            payload.get("raw_dest_path", ""),
        )
        if kind == "subtitle":
            self._subtitle_wake_event.set()
        return True

    @staticmethod
    def _payload_signature(kind: str, payload: Dict[str, Any]) -> str:
        """构造跨推送来源的文件级去重签名。"""
        path = str(payload.get("pan_path") or payload.get("cd2_path") or "")
        size = int(payload.get("size", 0) or 0)
        return f"{kind}|{path}|{size}"

    def _log_ignored(self, destination: str, reason: str) -> None:
        """记录未命中规则或扩展名的任务，避免“没有日志”难以排查。"""
        with self._state_lock:
            self._stats["ignored_count"] += 1
        logger.info(
            "【CD2 STRM触发器】任务忽略：raw destPath=%s；原因=%s",
            destination,
            reason,
        )

    @staticmethod
    def _enum_name(enum_type: Any, value: int, fallback: str = "UNKNOWN") -> str:
        """将 protobuf 枚举值转换为可读名称。"""
        try:
            return str(enum_type.Name(int(value)))
        except (AttributeError, TypeError, ValueError):
            return fallback

    @classmethod
    def _operator_type_name(cls, value: int) -> str:
        """返回 CD2 上传任务来源名称。"""
        return cls._enum_name(cd2_pb2.UploadFileInfo.OperatorType, value)

    @classmethod
    def _status_name(cls, value: int) -> str:
        """返回 CD2 上传任务状态名称。"""
        return cls._enum_name(cd2_pb2.UploadFileInfo.Status, value)

    @classmethod
    def _message_type_name(cls, value: int) -> str:
        """返回 CD2 推送消息类型名称。"""
        return cls._enum_name(cd2_pb2.CloudDrivePushMessage.MessageType, value)

    @classmethod
    def _file_change_type_name(cls, value: int) -> str:
        """返回 CD2 文件系统变更类型名称。"""
        return cls._enum_name(cd2_pb2.FileSystemChange.ChangeType, value)

    def _task_key(self, task: Any) -> str:
        """获取 CD2 上传任务的稳定去重键。"""
        key = self._text(getattr(task, "key", ""))
        if key:
            return key
        destination = self._normalize_path(getattr(task, "destPath", ""))
        size = int(getattr(task, "size", 0) or 0)
        return f"{destination}|{size}" if destination else ""

    @classmethod
    def _path_matches(cls, path: str, prefix: str) -> bool:
        """判断文件路径是否位于目录前缀下，并避免相似目录误匹配。"""
        normalized_path = cls._normalize_path(path)
        normalized_prefix = cls._normalize_path(prefix)
        if normalized_prefix == "/":
            return bool(normalized_path)
        return bool(
            normalized_path
            and normalized_prefix
            and (
                normalized_path == normalized_prefix
                or normalized_path.startswith(normalized_prefix.rstrip("/") + "/")
            )
        )

    @classmethod
    def _relative_path(cls, path: str, prefix: str) -> str:
        """计算文件相对于 CD2 监控目录的相对路径。"""
        normalized_path = cls._normalize_path(path)
        normalized_prefix = cls._normalize_path(prefix).rstrip("/")
        if normalized_path == normalized_prefix:
            return ""
        return normalized_path[len(normalized_prefix) :].lstrip("/")

    def _find_rule(self, destination: str) -> Optional[Dict[str, Any]]:
        """根据 CD2 文件目标路径选择最长匹配的启用规则。"""
        canonical_destination = self._canonical_cd2_path(destination)
        candidates = [
            rule
            for rule in self._config.get("rules", [])
            if rule.get("enabled", True)
            and self._path_matches(
                canonical_destination,
                self._canonical_cd2_path(rule["cd2_prefix"]),
            )
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda item: len(self._canonical_cd2_path(item["cd2_prefix"])),
        )

    def _allowed_extension(
        self, name: str, config_key: str = "include_extensions", empty_matches: bool = True
    ) -> bool:
        """判断任务文件扩展名是否属于指定配置项。"""
        configured = self._config.get(config_key, "")
        if isinstance(configured, (list, tuple, set)):
            items = configured
        else:
            items = str(configured or "").split(",")
        extensions = {
            str(item).strip().lower().lstrip(".")
            for item in items
            if str(item).strip()
        }
        if not extensions:
            return empty_matches
        suffix = PurePosixPath(name).suffix.lower().lstrip(".")
        return bool(suffix and suffix in extensions)

    def _build_payload(self, task: Any) -> Optional[Dict[str, Any]]:
        """将 CD2 完成任务转换为 115 STRM 文件生成请求。"""
        built = self._build_file_payload(task)
        if not built or built[0] != "media":
            return None
        return built[1]

    def _build_file_payload(self, task: Any) -> Optional[Tuple[str, Dict[str, Any]]]:
        """将 CD2 完成任务转换为 STRM 或字幕下载任务。"""
        destination = self._normalize_path(getattr(task, "destPath", ""))
        return self._build_file_payload_from_destination(
            destination,
            int(getattr(task, "size", 0) or 0),
        )

    def _build_file_payload_from_destination(
        self, destination: str, size: int
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """按统一后的 CD2 路径构造 STRM 或字幕任务。"""
        destination = self._normalize_path(destination)
        canonical_destination = self._canonical_cd2_path(destination)
        rule = self._find_rule(canonical_destination)
        if not rule:
            return None
        name = posixpath.basename(canonical_destination)
        if not name:
            return None
        relative = self._relative_path(
            canonical_destination,
            self._canonical_cd2_path(rule["cd2_prefix"]),
        )
        pan_path = self._join_path(rule["pan_prefix"], relative)
        common_payload = {
            "name": name,
            "pan_path": pan_path,
            "size": int(size or 0),
            "local_path": rule["local_path"],
            "pan_media_path": rule["pan_prefix"],
            "raw_dest_path": destination,
            "cd2_path": canonical_destination,
        }
        if self._allowed_extension(name, "include_extensions"):
            common_payload.update(
                {
                    "scrape_metadata": bool(self._config["scrape_metadata"]),
                    # Emby 刷新由本插件在整批 STRM 生成完成后统一执行。
                    # 显式传 False，避免 115 助手的全局 API 刷新开关再次逐文件刷新。
                    "media_server_refresh": False,
                    "auto_download_mediainfo": bool(self._config["auto_download_mediainfo"]),
                }
            )
            return "media", common_payload
        if self._allowed_extension(
            name, "subtitle_extensions", empty_matches=False
        ):
            common_payload.update(
                {
                    "local_file": self._local_file_path(rule["local_path"], relative),
                }
            )
            return "subtitle", common_payload
        return None

    def _payload_ignore_reason(self, destination: str) -> str:
        """返回路径/扩展名未命中时的可读原因。"""
        canonical_destination = self._canonical_cd2_path(destination)
        rule = self._find_rule(canonical_destination)
        if not rule:
            return f"未命中目录规则（规范化路径：{canonical_destination or '/'}）"
        name = posixpath.basename(canonical_destination)
        if self._allowed_extension(name, "include_extensions"):
            return "媒体扩展名已命中，但文件任务构造失败"
        if self._allowed_extension(name, "subtitle_extensions", empty_matches=False):
            return "字幕扩展名已命中，但文件任务构造失败"
        return f"扩展名未启用：{PurePosixPath(name).suffix or '(无扩展名)'}"

    @classmethod
    def _join_path(cls, prefix: str, relative: str) -> str:
        """将网盘目录前缀和相对文件路径安全拼接。"""
        normalized_prefix = cls._normalize_path(prefix)
        if not relative:
            return normalized_prefix
        if normalized_prefix == "/":
            return "/" + relative.lstrip("/")
        return normalized_prefix.rstrip("/") + "/" + relative.lstrip("/")

    @classmethod
    def _local_file_path(cls, root: str, relative: str) -> str:
        """将相对网盘路径映射为本地字幕文件路径。"""
        relative_path = PurePosixPath(str(relative or ""))
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("字幕相对路径包含非法目录跳转")
        local_root = Path(cls._text(root)).expanduser()
        if not relative_path.parts:
            return str(local_root)
        return str(local_root.joinpath(*relative_path.parts))

    def _download_subtitle(self, payload: Dict[str, Any]) -> str:
        """通过 CD2 下载单个字幕文件并原子写入本地媒体目录。"""
        target = Path(str(payload.get("local_file") or "")).expanduser()
        if not target.name or str(target) in (".", "/"):
            raise ValueError("字幕本地目标路径无效")

        expected_size = int(payload.get("size", 0) or 0)
        if target.is_file() and (expected_size <= 0 or target.stat().st_size == expected_size):
            return "本地文件已存在"

        self._confirm_subtitle_stable(payload)

        cd2_client = CloudDrive2Client(
            endpoint=self._config["cd2_endpoint"],
            token=self._config["cd2_token"],
            timeout=120,
            page_size=self._config["page_size"],
        )
        try:
            url_info = cd2_client.get_download_url_info(str(payload.get("cd2_path") or ""))
        finally:
            cd2_client.close()

        download_url = self._resolve_download_url(url_info)
        headers = {
            str(key): str(value)
            for key, value in (url_info.get("additional_headers") or {}).items()
            if key and value
        }
        if url_info.get("user_agent") and not any(
            key.lower() == "user-agent" for key in headers
        ):
            headers["User-Agent"] = str(url_info["user_agent"])

        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.parent / f".{target.name}.cd2-part"
        try:
            with httpx.Client(
                timeout=120,
                trust_env=False,
                follow_redirects=True,
            ) as client:
                with client.stream("GET", download_url, headers=headers) as response:
                    response.raise_for_status()
                    with temporary.open("wb") as output:
                        for chunk in response.iter_bytes():
                            if chunk:
                                output.write(chunk)
            if expected_size > 0 and temporary.stat().st_size != expected_size:
                raise RuntimeError(
                    f"字幕下载大小不一致：期望 {expected_size} 字节，实际 {temporary.stat().st_size} 字节"
                )
            temporary.replace(target)
        except Exception:
            if temporary.exists():
                temporary.unlink()
            raise
        return "已下载"

    def _confirm_subtitle_stable(self, payload: Dict[str, Any]) -> None:
        """延迟并连续读取两次远端属性，确认字幕不是仍在写入的临时文件。"""
        path = self._text(payload.get("cd2_path"))
        if not path:
            raise RuntimeError("字幕缺少 CD2 API 文件路径")
        client = CloudDrive2Client(
            endpoint=self._config["cd2_endpoint"],
            token=self._config["cd2_token"],
            timeout=30,
            page_size=self._config["page_size"],
        )
        try:
            samples: List[int] = []
            for index in range(2):
                file_info = client.get_file_info(path)
                if bool(getattr(file_info, "isDirectory", False)):
                    raise RuntimeError("CD2 返回的是目录，不是字幕文件")
                samples.append(int(getattr(file_info, "size", 0) or 0))
                if index == 0 and self._stop_event.wait(
                    timeout=self.SUBTITLE_STABILITY_PROBE_INTERVAL
                ):
                    raise RuntimeError("插件正在停止")
        finally:
            client.close()
        if samples[0] != samples[1]:
            raise RuntimeError(
                f"字幕仍在上传：连续两次大小为 {samples[0]}、{samples[1]} 字节"
            )
        if samples[1] > 0 and int(payload.get("size", 0) or 0) != samples[1]:
            logger.info(
                "【CD2 STRM触发器】字幕任务大小已更新：task=%s，CD2=%s，使用 CD2 最新大小",
                payload.get("size", 0),
                samples[1],
            )
            payload["size"] = samples[1]

    def _resolve_download_url(self, url_info: Dict[str, Any]) -> str:
        """将 CD2 返回的直链或带占位符地址转换为可请求的 URL。"""
        direct_url = self._text(url_info.get("direct_url"))
        if direct_url:
            return direct_url
        template = self._text(url_info.get("download_url_path"))
        if not template:
            raise RuntimeError("CD2 未返回字幕下载地址")

        endpoint = self._text(self._config.get("cd2_endpoint"))
        if "://" not in endpoint:
            endpoint = f"http://{endpoint}"
        parsed = urlparse(endpoint.rstrip("/"))
        if not parsed.netloc:
            raise RuntimeError("CD2 地址无效，无法拼接字幕下载地址")
        scheme = parsed.scheme or "http"
        template = template.replace("{SCHEME}", scheme)
        template = template.replace("{HOST}", parsed.netloc)
        template = template.replace("{PREVIEW}", "false")
        if template.startswith("//"):
            template = f"{scheme}:{template}"
        elif template.startswith("/"):
            template = f"{scheme}://{parsed.netloc}{template}"
        elif "://" not in template:
            template = urljoin(f"{scheme}://{parsed.netloc}/", template)
        if "{" in template or "}" in template:
            raise RuntimeError(f"CD2 下载地址包含未识别占位符：{template}")
        return template

    def _flush_pending_if_due(self) -> None:
        """在批处理窗口到期后提交最多 100 个待生成文件。"""
        with self._pending_lock:
            if not self._pending:
                self._update_pending_count()
                return
            now = time.monotonic()
            first_item = next(iter(self._pending.values()))
            first_seen = float(first_item.get("first_seen", now))
            if now - first_seen < self._config.get("batch_window", 5):
                return
            selected = list(self._pending.items())[:100]
            for key, _ in selected:
                self._pending.pop(key, None)
        self._update_pending_count()
        payloads = [item["payload"] for _, item in selected]
        try:
            result = self._call_p115_api(payloads)
        except Exception:
            with self._pending_lock:
                for key, item in selected:
                    attempts = int(item.get("attempts", 0)) + 1
                    if attempts < 4:
                        item["attempts"] = attempts
                        item["first_seen"] = time.monotonic()
                        self._pending[key] = item
                    else:
                        logger.error(
                            "【CD2 STRM触发器】115 STRM API 连续失败，停止自动重试：%s",
                            item["payload"].get("pan_path", key),
                        )
            self._update_pending_count()
            raise
        succeeded, failed = self._split_result(selected, result)
        selected_by_key = dict(selected)
        persisted = [
            key
            for key in succeeded
            if selected_by_key.get(key, {}).get("persist_key", True)
        ]
        if persisted:
            self._processed_keys.update(persisted)
            self._save_processed_keys()
        if failed:
            with self._pending_lock:
                for key, item in failed:
                    attempts = int(item.get("attempts", 0)) + 1
                    if attempts < 4:
                        item["attempts"] = attempts
                        item["first_seen"] = time.monotonic()
                        self._pending[key] = item
                    else:
                        logger.error(
                            "【CD2 STRM触发器】任务连续失败，停止自动重试：%s",
                            item["payload"].get("pan_path", key),
                        )
            self._update_pending_count()
        succeeded_payloads = [
            selected_by_key[key]["payload"]
            for key in succeeded
            if key in selected_by_key
        ]
        if succeeded_payloads:
            self._refresh_emby_batch(succeeded_payloads)
        self._record_trigger_result(result, len(succeeded), len(failed))

    def _refresh_emby_batch(self, payloads: List[Dict[str, Any]]) -> None:
        """在一批 STRM 生成成功后向每个已配置的 Emby 发送一次刷新请求。"""
        if not self._config.get("media_server_refresh") or not payloads:
            return

        try:
            services = MediaServerHelper().get_services(type_filter="emby")
        except Exception as exc:
            message = f"获取 MoviePilot Emby 服务失败：{exc}"
            with self._state_lock:
                self._stats["last_emby_refresh_error"] = message
            logger.warning("【CD2 STRM触发器】%s", message)
            return

        if not services:
            message = "MoviePilot 未找到已配置的 Emby 服务，跳过批次刷新"
            with self._state_lock:
                self._stats["last_emby_refresh_error"] = message
            logger.warning("【CD2 STRM触发器】%s", message)
            return

        server_names = list(services.keys())
        logger.info(
            "【CD2 STRM触发器】开始 Emby 批次刷新：STRM成功=%s，目标服务器=%s；每个服务器本批仅请求一次",
            len(payloads),
            ",".join(server_names),
        )
        refreshed_servers: List[str] = []
        errors: List[str] = []
        request_count = 0
        for name, service in services.items():
            instance = getattr(service, "instance", None)
            if not instance:
                errors.append(f"{name}:实例不存在")
                continue
            try:
                if instance.is_inactive():
                    errors.append(f"{name}:服务未连接")
                    continue
                refresh = getattr(instance, "refresh_root_library", None)
                if not callable(refresh):
                    errors.append(f"{name}:不支持 Emby 刷新接口")
                    continue
                request_count += 1
                if refresh():
                    refreshed_servers.append(name)
                    logger.info(
                        "【CD2 STRM触发器】Emby 批次刷新请求已发送：server=%s，文件数=%s",
                        name,
                        len(payloads),
                    )
                else:
                    errors.append(f"{name}:Emby API 返回失败")
                    logger.warning(
                        "【CD2 STRM触发器】Emby 批次刷新失败：server=%s，文件数=%s",
                        name,
                        len(payloads),
                    )
            except Exception as exc:
                errors.append(f"{name}:{exc}")
                logger.warning("【CD2 STRM触发器】Emby 批次刷新异常：server=%s，原因=%s", name, exc)

        with self._state_lock:
            self._stats["emby_refresh_batch_count"] += 1
            self._stats["emby_refresh_request_count"] += request_count
            self._stats["last_emby_refresh_at"] = self._now()
            self._stats["last_emby_refresh_servers"] = refreshed_servers
            self._stats["last_emby_refresh_error"] = "; ".join(errors)
        if errors:
            logger.warning(
                "【CD2 STRM触发器】Emby 批次刷新部分失败：成功=%s，失败=%s",
                ",".join(refreshed_servers) or "无",
                "; ".join(errors),
            )
        else:
            logger.info(
                "【CD2 STRM触发器】Emby 批次刷新完成：本批文件=%s，API请求=%s",
                len(payloads),
                request_count,
            )

    def _call_p115_api(self, payloads: List[Dict[str, Any]]) -> Dict[str, Any]:
        """调用 115 STRM 助手的文件级增量生成 API。"""
        api_key = self._text(self._config.get("moviepilot_api_key")) or self._text(
            getattr(settings, "API_TOKEN", "")
        )
        if not api_key:
            raise RuntimeError("未配置 MoviePilot API Key，且系统 API_TOKEN 为空")
        base_url = self._config["moviepilot_url"].rstrip("/")
        endpoint = f"{base_url}/api/v1/plugin/P115StrmHelper/api_strm_sync_creata"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=60, trust_env=False) as client:
            response = client.post(
                endpoint,
                params={"apikey": api_key},
                headers=headers,
                json={"data": payloads},
            )
            response.raise_for_status()
            result = response.json()
        if not isinstance(result, dict):
            raise RuntimeError("115 STRM API 返回格式不是 JSON 对象")
        code = result.get("code")
        if code is not None and int(code) != 10200:
            raise RuntimeError(f"115 STRM API 返回错误：{result.get('msg') or code}")
        return result

    @staticmethod
    def _split_result(
        selected: List[Tuple[str, Dict[str, Any]]], result: Dict[str, Any]
    ) -> Tuple[List[str], List[Tuple[str, Dict[str, Any]]]]:
        """根据 115 API 的成功和失败列表拆分批处理结果。"""
        data = result.get("data") if isinstance(result.get("data"), dict) else result
        success_items = data.get("success") or []
        fail_items = data.get("fail") or []
        success_paths = {
            str(item.get("pan_path"))
            for item in success_items
            if isinstance(item, dict) and item.get("pan_path")
        }
        fail_paths = {
            str(item.get("pan_path"))
            for item in fail_items
            if isinstance(item, dict) and item.get("pan_path")
        }
        if not success_paths and not fail_paths:
            return [key for key, _ in selected], []
        succeeded: List[str] = []
        failed: List[Tuple[str, Dict[str, Any]]] = []
        for key, item in selected:
            path = str(item["payload"].get("pan_path") or "")
            if path in success_paths:
                succeeded.append(key)
            elif path in fail_paths or path not in success_paths:
                failed.append((key, item))
        return succeeded, failed

    def _record_trigger_result(
        self, result: Dict[str, Any], success_count: int, failed_count: int
    ) -> None:
        """记录本次 115 STRM API 调用结果并按需发送通知。"""
        data = result.get("data") if isinstance(result.get("data"), dict) else result
        summary = {
            "success_count": int(data.get("success_count", success_count) or 0),
            "fail_count": int(data.get("fail_count", failed_count) or 0),
            "download_success_count": int(data.get("download_success_count", 0) or 0),
            "download_fail_count": int(data.get("download_fail_count", 0) or 0),
        }
        with self._state_lock:
            self._stats["last_trigger_at"] = self._now()
            self._stats["last_trigger"] = summary
            self._stats["last_error"] = "" if not failed_count else "部分文件生成 STRM 失败，已进入重试"
        if self._config.get("notify"):
            self.post_message(
                mtype=NotificationType.Plugin,
                title="【CD2】上传完成，115 STRM 增量生成",
                text=(
                    f"生成成功 {summary['success_count']} 个，失败 {summary['fail_count']} 个"
                    f"\n媒体元数据成功 {summary['download_success_count']} 个"
                ),
            )

    def _test_moviepilot_api(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        """测试 MoviePilot 115 STRM API 是否可访问。"""
        api_key = self._text(config.get("moviepilot_api_key")) or self._text(
            getattr(settings, "API_TOKEN", "")
        )
        if not api_key:
            return False, "MoviePilot API Key 未配置"
        endpoint = (
            f"{config['moviepilot_url'].rstrip('/')}/api/v1/plugin/"
            "P115StrmHelper/api_strm_sync_creata"
        )
        try:
            with httpx.Client(timeout=10, trust_env=False) as client:
                response = client.post(
                    endpoint,
                    params={"apikey": api_key},
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"data": []},
                )
            if response.status_code in (400, 422):
                return True, "MoviePilot API 可访问（空请求被正常校验）"
            if response.status_code >= 400:
                return False, f"MoviePilot API HTTP {response.status_code}"
            return True, "MoviePilot API 可访问"
        except Exception as exc:
            return False, f"MoviePilot API 访问失败：{exc}"

    def _save_processed_keys(self) -> None:
        """持久化最近处理过的 CD2 任务键，避免重启后重复生成。"""
        keys = list(self._processed_keys)[-2000:]
        self.save_data(self.DATA_KEY_PROCESSED, keys)
        with self._state_lock:
            self._stats["processed_count"] = len(self._processed_keys)

    def _update_pending_count(self) -> None:
        """刷新待处理任务数量统计。"""
        with self._pending_lock:
            strm_pending_count = len(self._pending)
            subtitle_pending_count = len(self._subtitle_pending)
        with self._state_lock:
            self._stats["strm_pending_count"] = strm_pending_count
            self._stats["subtitle_pending_count"] = subtitle_pending_count
            self._stats["pending_count"] = strm_pending_count + subtitle_pending_count

    def _status_snapshot(self) -> Dict[str, Any]:
        """生成供前端显示的线程安全状态快照。"""
        with self._state_lock:
            snapshot = dict(self._stats)
        snapshot["rule_count"] = len(self._config.get("rules", []))
        snapshot["has_cd2_token"] = bool(self._config.get("cd2_token"))
        snapshot["has_moviepilot_api_key"] = bool(
            self._config.get("moviepilot_api_key") or getattr(settings, "API_TOKEN", "")
        )
        return snapshot

    @staticmethod
    def _now() -> str:
        """返回当前本地时间文本。"""
        return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")

    def _set_error(self, message: str) -> None:
        """记录错误状态并写入 MoviePilot 日志。"""
        with self._state_lock:
            self._stats["connected"] = False
            self._stats["last_error"] = message
        logger.warning("【CD2 STRM触发器】%s", message)

    def stop_service(self):
        """停止后台线程、关闭 CD2 推送连接并释放资源。"""
        self._stop_event.set()
        self._wake_event.set()
        if hasattr(self, "_subtitle_wake_event"):
            self._subtitle_wake_event.set()
        with self._state_lock:
            push_client = self._push_client
            self._push_client = None
        if push_client:
            push_client.close()
        for thread in getattr(self, "_threads", []):
            if thread.is_alive() and thread is not threading.current_thread():
                thread.join(timeout=3)
        self._threads = []
        with self._state_lock:
            self._stats["running"] = False
