"""CloudDrive2 上传完成后触发 115 STRM 生成的 MoviePilot V2 插件。"""

from __future__ import annotations

import posixpath
import threading
import time
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import Body

from app import schemas
from app.core.config import settings
from app.core.event import Event, eventmanager
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType

from .cd2_client import CloudDrive2Client
from clouddrive2_client.proto import clouddrive_pb2 as cd2_pb2


class Cd2UploadStrmTrigger(_PluginBase):
    """监听 CD2 上传完成任务并调用 115 STRM 助手生成精确增量 STRM。"""

    plugin_name = "CD2 上传触发 115 STRM"
    plugin_desc = "监听 CloudDrive2 上传完成任务，按目录映射调用 115 网盘 STRM 助手生成增量 STRM。"
    plugin_icon = "https://raw.githubusercontent.com/cloud-fs/clouddrive-mediaserver-plugin/main/icon.png"
    plugin_version = "0.1.0"
    plugin_author = "wubushanyan"
    author_url = "https://github.com/wubushanyan"
    plugin_config_prefix = "cd2uploadstrmtrigger_"
    plugin_order = 98
    auth_level = 1

    DATA_KEY_PROCESSED = "processed_task_keys"
    FINISH_STATUS = int(cd2_pb2.UploadFileInfo.Finish)
    UPLOADER_MESSAGE = int(cd2_pb2.CloudDrivePushMessage.UPLOADER_COUNT)

    DEFAULT_EXTENSIONS = (
        "mkv,mp4,ts,avi,mov,m4v,wmv,flv,m2ts,iso,rmvb,webm,mpeg,mpg,3gp,asf,tp,f4v"
    )

    def __init__(self):
        """初始化插件运行时状态。"""
        super().__init__()
        self._config: Dict[str, Any] = self._default_config()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._ready_event = threading.Event()
        self._state_lock = threading.RLock()
        self._pending_lock = threading.RLock()
        self._push_client: Optional[CloudDrive2Client] = None
        self._threads: List[threading.Thread] = []
        self._task_states: Dict[str, int] = {}
        self._pending: Dict[str, Dict[str, Any]] = {}
        self._processed_keys: set[str] = set()
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
            "baseline_on_start": True,
            "include_extensions": Cd2UploadStrmTrigger.DEFAULT_EXTENSIONS,
            "scrape_metadata": False,
            "media_server_refresh": False,
            "auto_download_mediainfo": False,
            "notify": False,
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
            "last_trigger_at": "",
            "last_trigger": {},
            "upload_count": 0,
            "task_count": 0,
            "matched_count": 0,
            "pending_count": 0,
            "processed_count": 0,
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
            "baseline_on_start": bool(raw.get("baseline_on_start", True)),
            "include_extensions": cls._text(raw.get("include_extensions"))
            or defaults["include_extensions"],
            "scrape_metadata": bool(raw.get("scrape_metadata", False)),
            "media_server_refresh": bool(raw.get("media_server_refresh", False)),
            "auto_download_mediainfo": bool(raw.get("auto_download_mediainfo", False)),
            "notify": bool(raw.get("notify", False)),
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
        """启动轮询、推送和 STRM 请求批处理线程。"""
        self._stop_event.clear()
        self._wake_event.clear()
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
        self._threads = [poll_thread, push_thread, dispatch_thread]
        for thread in self._threads:
            thread.start()

    def _poll_loop(self) -> None:
        """定时读取 CD2 上传计数和任务列表，作为推送监听的可靠兜底。"""
        first_scan = bool(self._config.get("baseline_on_start", True))
        while not self._stop_event.is_set():
            try:
                count, tasks = self._poll_once()
                with self._state_lock:
                    self._stats["connected"] = True
                    self._stats["last_error"] = ""
                    self._stats["last_poll_at"] = self._now()
                    self._stats["upload_count"] = count
                    self._stats["task_count"] = len(tasks)
                    self._stats["poll_count"] += 1
                for task in tasks:
                    self._observe_task(task, allow_trigger=not first_scan)
                if first_scan:
                    first_scan = False
                    self._ready_event.set()
                self._update_pending_count()
            except Exception as exc:
                self._set_error(f"轮询 CD2 上传任务失败：{exc}")
                self._ready_event.set()
            self._wake_event.wait(timeout=self._config.get("poll_interval", 5))
            self._wake_event.clear()

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
                for message in client.push_messages(self._stop_event):
                    if self._stop_event.is_set():
                        return
                    if int(message.messageType) != self.UPLOADER_MESSAGE:
                        continue
                    with self._state_lock:
                        self._stats["last_push_at"] = self._now()
                    if not message.HasField("transferTaskStatus"):
                        self._wake_event.set()
                        continue
                    for task in message.transferTaskStatus.uploadFileStatusChanges:
                        self._observe_task(task, allow_trigger=self._ready_event.is_set())
                    self._wake_event.set()
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

    def _observe_task(self, task: Any, allow_trigger: bool) -> None:
        """记录任务状态，并在任务从未完成变为 Finish 时加入待处理队列。"""
        key = self._task_key(task)
        if not key:
            return
        status = int(getattr(task, "statusEnum", -1))
        previous = self._task_states.get(key)
        self._task_states[key] = status
        if not allow_trigger or status != self.FINISH_STATUS or previous == self.FINISH_STATUS:
            return
        payload = self._build_payload(task)
        if not payload:
            return
        with self._state_lock:
            self._stats["matched_count"] += 1
        with self._pending_lock:
            if key in self._processed_keys or key in self._pending:
                return
            self._pending[key] = {"payload": payload, "attempts": 0, "first_seen": time.monotonic()}
        self._update_pending_count()

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
        candidates = [
            rule
            for rule in self._config.get("rules", [])
            if rule.get("enabled", True) and self._path_matches(destination, rule["cd2_prefix"])
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: len(item["cd2_prefix"]))

    def _allowed_extension(self, name: str) -> bool:
        """判断任务文件扩展名是否属于配置的媒体扩展名。"""
        configured = self._config.get("include_extensions", "")
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
            return True
        suffix = PurePosixPath(name).suffix.lower().lstrip(".")
        return bool(suffix and suffix in extensions)

    def _build_payload(self, task: Any) -> Optional[Dict[str, Any]]:
        """将 CD2 完成任务转换为 115 STRM 文件生成请求。"""
        destination = self._normalize_path(getattr(task, "destPath", ""))
        rule = self._find_rule(destination)
        if not rule:
            return None
        name = posixpath.basename(destination)
        if not name or not self._allowed_extension(name):
            return None
        relative = self._relative_path(destination, rule["cd2_prefix"])
        pan_path = self._join_path(rule["pan_prefix"], relative)
        return {
            "name": name,
            "pan_path": pan_path,
            "size": int(getattr(task, "size", 0) or 0),
            "local_path": rule["local_path"],
            "pan_media_path": rule["pan_prefix"],
            "scrape_metadata": bool(self._config["scrape_metadata"]),
            "media_server_refresh": bool(self._config["media_server_refresh"]),
            "auto_download_mediainfo": bool(self._config["auto_download_mediainfo"]),
        }

    @classmethod
    def _join_path(cls, prefix: str, relative: str) -> str:
        """将网盘目录前缀和相对文件路径安全拼接。"""
        normalized_prefix = cls._normalize_path(prefix)
        if not relative:
            return normalized_prefix
        if normalized_prefix == "/":
            return "/" + relative.lstrip("/")
        return normalized_prefix.rstrip("/") + "/" + relative.lstrip("/")

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
        result = self._call_p115_api(payloads)
        succeeded, failed = self._split_result(selected, result)
        if succeeded:
            self._processed_keys.update(succeeded)
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
        self._record_trigger_result(result, len(succeeded), len(failed))

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
            pending_count = len(self._pending)
        with self._state_lock:
            self._stats["pending_count"] = pending_count

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
