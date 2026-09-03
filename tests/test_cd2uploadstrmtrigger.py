"""CD2 上传触发 115 STRM 插件的纯逻辑测试。"""

import threading
from pathlib import Path

import pytest

import cd2uploadstrmtrigger as plugin_module
from cd2uploadstrmtrigger import Cd2UploadStrmTrigger
from clouddrive2_client.proto import clouddrive_pb2


def _make_plugin():
    """创建不启动后台线程的插件测试对象。"""
    plugin = object.__new__(Cd2UploadStrmTrigger)
    plugin._config = plugin._normalize_config(
        {
            "rules": [
                {
                    "cd2_prefix": "/CloudNAS/115/影视库",
                    "pan_prefix": "/影视库",
                    "local_path": "/media/MP_movieDB/影视库",
                }
            ],
            "include_extensions": "mkv,mp4",
        }
    )
    return plugin


def _prepare_runtime(plugin, ready=True):
    """补齐事件/队列运行态，便于纯逻辑测试直接调用处理方法。"""
    plugin._ensure_runtime_events()
    plugin._stats = plugin._new_stats()
    plugin._state_lock = threading.RLock()
    plugin._ready_event = threading.Event()
    if ready:
        plugin._ready_event.set()
    return plugin


def _valid_config(**overrides):
    """返回不触发外部请求的有效配置样本。"""
    config = {
        "enabled": True,
        "cd2_endpoint": "http://cd2.test:19798",
        "cd2_token": "cd2-test-token",
        "moviepilot_url": "http://moviepilot.test:3001",
        "moviepilot_api_key": "",
        "rules": [
            {
                "enabled": True,
                "cd2_prefix": "/影视库",
                "pan_prefix": "/影视库",
                "local_path": "/media/MP_movieDB/影视库",
            }
        ],
    }
    config.update(overrides)
    return config


def _init_test_plugin():
    """创建可运行 init_plugin 但不会启动线程的测试对象。"""
    plugin = _make_plugin()
    plugin._ensure_runtime_events()
    plugin._threads = []
    plugin._push_client = None
    plugin._emby_refresh_lock = threading.RLock()
    plugin._emby_refresh_wake_event = threading.Event()
    plugin._emby_refresh_pending = False
    plugin._emby_refresh_deadline = 0.0
    plugin._emby_refresh_pending_count = 0
    plugin._emby_refresh_reasons = set()
    plugin.get_data = lambda key: []
    plugin._start_workers = lambda: pytest.fail("无效配置不应启动后台线程")
    return plugin


def test_completed_task_is_mapped_to_115_payload():
    """验证完成任务会转换为正确的 115 文件级请求。"""
    plugin = _make_plugin()
    task = clouddrive_pb2.UploadFileInfo(
        key="task-1",
        destPath="/CloudNAS/115/影视库/电影/a.mkv",
        size=123,
        statusEnum=clouddrive_pb2.UploadFileInfo.Finish,
    )
    payload = plugin._build_payload(task)
    assert payload["pan_path"] == "/影视库/电影/a.mkv"
    assert payload["local_path"] == "/media/MP_movieDB/影视库"


def test_similar_directory_and_non_media_are_ignored():
    """验证相似目录和非媒体文件不会命中规则。"""
    plugin = _make_plugin()
    wrong_dir = clouddrive_pb2.UploadFileInfo(
        destPath="/CloudNAS/115/影视库2/a.mkv", size=1, statusEnum=5
    )
    wrong_ext = clouddrive_pb2.UploadFileInfo(
        destPath="/CloudNAS/115/影视库/a.txt", size=1, statusEnum=5
    )
    assert plugin._build_payload(wrong_dir) is None
    assert plugin._build_payload(wrong_ext) is None


def test_subtitle_is_mapped_to_local_path_without_strm_flags():
    """验证字幕命中后进入下载任务，并按相对目录映射到本地。"""
    plugin = _make_plugin()
    subtitle = clouddrive_pb2.UploadFileInfo(
        destPath="/CloudNAS/115/影视库/电影/a.srt", size=12, statusEnum=5
    )
    kind, payload = plugin._build_file_payload(subtitle)
    assert kind == "subtitle"
    assert payload["cd2_path"] == "/影视库/电影/a.srt"
    assert payload["raw_dest_path"] == "/CloudNAS/115/影视库/电影/a.srt"
    assert payload["local_file"] == "/media/MP_movieDB/影视库/电影/a.srt"
    assert "scrape_metadata" not in payload


def test_mount_source_and_api_paths_are_equivalent():
    """验证挂载路径、源目录路径和令牌 API 路径可以命中同一条规则。"""
    plugin = _make_plugin()
    paths = (
        "/CloudNAS/115/影视库/电影/a.sup",
        "/115/影视库/电影/a.sup",
        "/影视库/电影/a.sup",
    )
    for path in paths:
        kind, payload = plugin._build_file_payload(
            clouddrive_pb2.UploadFileInfo(destPath=path, size=12, statusEnum=5)
        )
        assert kind == "subtitle"
        assert payload["pan_path"] == "/影视库/电影/a.sup"
        assert payload["cd2_path"] == "/影视库/电影/a.sup"


def test_remote_upload_operator_is_not_filtered():
    """验证 RemoteUpload 完成任务不会被当作挂载上传以外的任务过滤。"""
    plugin = _make_plugin()
    task = clouddrive_pb2.UploadFileInfo(
        key="remote-upload-1",
        destPath="/影视库/电影/a.mkv",
        size=123,
        operatorType=clouddrive_pb2.UploadFileInfo.RemoteUpload,
        statusEnum=clouddrive_pb2.UploadFileInfo.Finish,
    )
    payload = plugin._build_payload(task)
    assert payload["pan_path"] == "/影视库/电影/a.mkv"


def test_startup_baseline_option_is_removed():
    """验证旧的基线开关不再出现在规范化配置中。"""
    plugin = _make_plugin()
    assert "baseline_on_start" not in plugin._config
    assert plugin._config["subtitle_interval"] == 3.0


def test_115_payload_never_enables_assistant_media_refresh():
    """验证刷新开关不会再传给 115 助手，避免其逐文件刷新。"""
    plugin = _make_plugin()
    plugin._config["media_server_refresh"] = True
    task = clouddrive_pb2.UploadFileInfo(
        destPath="/影视库/电影/a.mkv",
        size=123,
        statusEnum=clouddrive_pb2.UploadFileInfo.Finish,
    )
    payload = plugin._build_payload(task)
    assert payload["media_server_refresh"] is False


def test_emby_is_refreshed_once_for_one_strm_batch(monkeypatch):
    """验证一批 STRM 只向一个已配置 Emby 发送一次刷新请求。"""
    plugin = _make_plugin()
    plugin._config["media_server_refresh"] = True
    plugin._stats = plugin._new_stats()
    plugin._state_lock = threading.RLock()

    class FakeEmby:
        def __init__(self):
            self.calls = 0

        def is_inactive(self):
            return False

        def refresh_root_library(self):
            self.calls += 1
            return True

    fake_emby = FakeEmby()

    class FakeHelper:
        def get_services(self, type_filter=None):
            assert type_filter == "emby"
            return {"家庭 Emby": type("Service", (), {"instance": fake_emby})()}

    monkeypatch.setattr(plugin_module, "MediaServerHelper", FakeHelper)
    plugin._perform_emby_refresh(2, "strm,subtitle")
    assert fake_emby.calls == 1
    assert plugin._stats["emby_refresh_batch_count"] == 1
    assert plugin._stats["emby_refresh_request_count"] == 1


def test_media_and_subtitle_refresh_requests_share_debounce_window():
    """验证媒体和字幕事件会合并到同一个刷新窗口。"""
    plugin = _make_plugin()
    plugin._config["media_server_refresh"] = True
    plugin._config["emby_refresh_debounce"] = 5
    plugin._state_lock = threading.RLock()
    plugin._emby_refresh_lock = threading.RLock()
    plugin._emby_refresh_wake_event = threading.Event()
    plugin._emby_refresh_pending = False
    plugin._emby_refresh_deadline = 0.0
    plugin._emby_refresh_pending_count = 0
    plugin._emby_refresh_reasons = set()
    plugin._request_emby_refresh("strm", 2)
    plugin._request_emby_refresh("subtitle", 1)
    assert plugin._emby_refresh_pending is True
    assert plugin._emby_refresh_pending_count == 3
    assert plugin._emby_refresh_reasons == {"strm", "subtitle"}
    assert plugin._stats["emby_refresh_pending_count"] == 3


def test_delete_sync_removes_subtitle_and_empty_directories(tmp_path):
    """验证删除 CD2 字幕会删除本地字幕并清理空目录。"""
    plugin = _make_plugin()
    plugin._config["delete_sync"] = True
    plugin._config["media_server_refresh"] = False
    plugin._ready_event = threading.Event()
    plugin._ready_event.set()
    plugin._state_lock = threading.RLock()
    plugin._emby_refresh_lock = threading.RLock()
    plugin._emby_refresh_wake_event = threading.Event()
    plugin._stop_event = threading.Event()
    local_root = tmp_path / "影视库"
    local_file = local_root / "电影" / "新目录" / "a.sup"
    local_file.parent.mkdir(parents=True)
    local_file.write_bytes(b"subtitle")
    plugin._config["rules"] = plugin._normalize_config(
        {
            "rules": [
                {
                    "cd2_prefix": "/影视库",
                    "pan_prefix": "/影视库",
                    "local_path": str(local_root),
                }
            ],
            "delete_sync": True,
        }
    )["rules"]
    change = clouddrive_pb2.FileSystemChange(
        changeType=clouddrive_pb2.FileSystemChange.DELETE,
        isDirectory=False,
        path="/115/影视库/电影/新目录/a.sup",
    )
    plugin._observe_file_system_change(change)
    assert not local_file.exists()
    assert not local_file.parent.exists()
    assert (local_root / "电影").exists() is False
    assert plugin._stats["delete_sync_count"] == 1


def test_delete_sync_removes_default_strm_name(tmp_path):
    """验证删除 CD2 媒体文件会删除默认命名的 STRM。"""
    plugin = _make_plugin()
    plugin._config["delete_sync"] = True
    plugin._ready_event = threading.Event()
    plugin._ready_event.set()
    plugin._state_lock = threading.RLock()
    plugin._emby_refresh_lock = threading.RLock()
    plugin._emby_refresh_wake_event = threading.Event()
    plugin._stop_event = threading.Event()
    local_root = tmp_path / "影视库"
    strm_file = local_root / "电影" / "a.strm"
    strm_file.parent.mkdir(parents=True)
    strm_file.write_text("url", encoding="utf-8")
    plugin._config["rules"] = plugin._normalize_config(
        {
            "rules": [
                {
                    "cd2_prefix": "/影视库",
                    "pan_prefix": "/影视库",
                    "local_path": str(local_root),
                }
            ],
            "delete_sync": True,
        }
    )["rules"]
    change = clouddrive_pb2.FileSystemChange(
        changeType=clouddrive_pb2.FileSystemChange.DELETE,
        isDirectory=False,
        path="/115/影视库/电影/a.mkv",
    )
    plugin._observe_file_system_change(change)
    assert not strm_file.exists()
    assert not (local_root / "电影").exists()


def test_sort_delete_is_recorded_as_non_monitor_event_without_local_delete(tmp_path):
    """验证 /Sort 源文件删除只记 CD2 事件，不进入删除同步或报错。"""
    plugin = _prepare_runtime(_make_plugin())
    plugin._config["delete_sync"] = True
    local_root = tmp_path / "影视库"
    local_file = local_root / "电影" / "a.strm"
    local_file.parent.mkdir(parents=True)
    local_file.write_text("url", encoding="utf-8")

    change = clouddrive_pb2.FileSystemChange(
        changeType=clouddrive_pb2.FileSystemChange.DELETE,
        isDirectory=False,
        path="/Sort/电影/a.mkv",
    )
    plugin._observe_file_system_change(change)

    status = plugin._status_snapshot()
    assert local_file.exists()
    assert plugin._pending == {}
    assert plugin._subtitle_pending == {}
    assert status["delete_sync_count"] == 0
    assert status["non_monitor_count"] == 1
    assert status["ignored_count"] == 1
    assert status["last_error"] == ""
    assert status["cd2_received_count"] == 1
    assert any(
        item["title"] == "非监控目录事件已忽略"
        and item["raw_dest_path"] == "/Sort/电影/a.mkv"
        for item in status["event_history"]
    )


def test_push_task_details_are_processed_without_periodic_scan(monkeypatch):
    """验证 Push 任务详情可直接处理，详情事件不触发周期/快速扫描。"""
    plugin = _prepare_runtime(_make_plugin())
    plugin._last_push_upload_count = 0
    scan_calls = []
    rapid_calls = []
    monkeypatch.setattr(
        plugin,
        "_scan_and_observe",
        lambda *args, **kwargs: scan_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(plugin, "_request_rapid_rescan", lambda: rapid_calls.append(True))

    task = clouddrive_pb2.UploadFileInfo(
        key="push-task-1",
        destPath="/115/影视库/电影/push.mkv",
        size=123,
        statusEnum=clouddrive_pb2.UploadFileInfo.Finish,
    )
    message = clouddrive_pb2.CloudDrivePushMessage(
        messageType=clouddrive_pb2.CloudDrivePushMessage.UPLOADER_COUNT,
    )
    message.transferTaskStatus.uploadCount = 1
    message.transferTaskStatus.uploadFileStatusChanges.append(task)

    plugin._handle_push_message(message)

    assert len(plugin._pending) == 1
    assert scan_calls == []
    assert rapid_calls == []
    assert any(item["source"] == "push" for item in plugin._status_snapshot()["event_history"])


def test_poll_fallback_defaults_off_but_manual_scan_remains_available():
    """验证兜底轮询默认关闭，开启后手动立即检查仍可唤醒扫描。"""
    default_config = Cd2UploadStrmTrigger._normalize_config({})
    enabled_config = Cd2UploadStrmTrigger._normalize_config(
        {"poll_fallback_enabled": True}
    )
    assert default_config["poll_fallback_enabled"] is False
    assert enabled_config["poll_fallback_enabled"] is True

    plugin = _prepare_runtime(_make_plugin())
    plugin._config["enabled"] = True
    plugin._config["poll_fallback_enabled"] = True
    plugin._wake_event = threading.Event()
    plugin._manual_scan_event = threading.Event()
    plugin._stop_event = threading.Event()
    scan_calls = []

    def fake_scan(*args, **kwargs):
        scan_calls.append(kwargs.get("source"))
        plugin._stop_event.set()
        return 0, []

    plugin._scan_and_observe = fake_scan
    response = plugin.api_trigger()
    assert response.success is True
    worker = threading.Thread(target=plugin._poll_loop)
    worker.start()
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert scan_calls == ["manual"]


def test_event_history_is_categorized_bounded_and_redacted():
    """验证事件分类字段完整、历史有上限且不会保存 Token。"""
    plugin = _prepare_runtime(_make_plugin())
    plugin._config["cd2_token"] = "cd2-secret-token"
    for index in range(120):
        plugin._record_event(
            "generate_event",
            "INFO",
            f"生成 {index}",
            "任务完成",
            source="test",
            status="success",
            raw_dest_path=f"/影视库/{index}.mkv",
            path=f"/影视库/{index}.mkv",
            details={"index": index, "token": "cd2-secret-token"},
        )

    assert len(plugin._event_history) == plugin.EVENT_HISTORY_LIMIT
    history = plugin._status_snapshot()["event_history"]
    assert len(history) == plugin.EVENT_HISTORY_LIMIT
    required = {
        "id",
        "at",
        "category",
        "level",
        "title",
        "message",
        "source",
        "status",
        "raw_dest_path",
        "path",
        "details",
    }
    assert required <= set(history[-1])
    assert history[-1]["category"] == "generate_event"
    assert "cd2-secret-token" not in str(history)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cd2_endpoint", ""),
        ("cd2_token", ""),
        ("rules", [{"enabled": True, "cd2_prefix": "/影视库"}]),
    ],
)
def test_validate_core_configuration_requires_cd2_and_enabled_rule(
    monkeypatch, field, value
):
    """核心启用配置必须有 CD2 地址、Token 和有效启用规则。"""
    monkeypatch.setattr(plugin_module.settings, "API_TOKEN", "system-test-token", raising=False)
    plugin = _make_plugin()
    config = _valid_config(**{field: value})

    result = plugin._validate_config(config)

    assert result["valid"] is False
    assert any(error["field"] == field for error in result["errors"])
    assert "cd2-test-token" not in str(result)
    assert "system-test-token" not in str(result)


def test_validate_accepts_empty_config_api_key_with_system_token(monkeypatch):
    """配置 API Key 留空时可使用系统 API_TOKEN。"""
    monkeypatch.setattr(plugin_module.settings, "API_TOKEN", "system-test-token", raising=False)
    plugin = _make_plugin()

    result = plugin._validate_config(_valid_config(moviepilot_api_key=""))

    assert result["valid"] is True
    assert result["errors"] == []
    assert "system-test-token" not in str(result)


def test_validate_accepts_configured_moviepilot_api_key_without_system_token(monkeypatch):
    """配置 API Key 时即使系统 API_TOKEN 为空也可以通过校验。"""
    monkeypatch.setattr(plugin_module.settings, "API_TOKEN", "", raising=False)
    plugin = _make_plugin()
    configured_key = "configured-moviepilot-key"

    result = plugin._validate_config(_valid_config(moviepilot_api_key=configured_key))

    assert result["valid"] is True
    assert configured_key not in str(result)


def test_validate_rejects_missing_moviepilot_credentials_without_leaking_token(monkeypatch):
    """配置 API Key 和系统 API_TOKEN 均为空时必须明确报错。"""
    monkeypatch.setattr(plugin_module.settings, "API_TOKEN", "", raising=False)
    plugin = _make_plugin()

    result = plugin._validate_config(_valid_config(moviepilot_api_key=""))

    assert result["valid"] is False
    assert any(error["field"] == "moviepilot_api_key" for error in result["errors"])
    assert "cd2-test-token" not in str(result)


def test_validate_moviepilot_actions_require_credentials_when_plugin_is_disabled(
    monkeypatch,
):
    """关闭插件时开启 115 助手动作仍需有效的 MoviePilot 凭据。"""
    monkeypatch.setattr(plugin_module.settings, "API_TOKEN", "", raising=False)
    plugin = _make_plugin()

    result = plugin._validate_config(
        _valid_config(
            enabled=False,
            scrape_metadata=True,
            auto_download_mediainfo=True,
            moviepilot_api_key="",
        )
    )

    assert result["valid"] is False
    assert result["feature_errors"]["moviepilot_actions"]
    assert all(error.get("scope") == "feature" for error in result["errors"])
    assert "cd2-test-token" not in str(result)


def test_validate_emby_refresh_requires_a_usable_service(monkeypatch):
    """Emby 刷新必须有可用服务，且只检查服务能力不发送刷新请求。"""
    monkeypatch.setattr(plugin_module.settings, "API_TOKEN", "system-test-token", raising=False)
    plugin = _make_plugin()

    class EmptyHelper:
        def get_services(self, type_filter=None):
            assert type_filter == "emby"
            return {}

    monkeypatch.setattr(plugin_module, "MediaServerHelper", EmptyHelper)
    rejected = plugin._validate_config(_valid_config(media_server_refresh=True))
    assert rejected["valid"] is False
    assert rejected["feature_errors"]["media_server_refresh"]

    class FakeEmby:
        def is_inactive(self):
            return False

        def refresh_root_library(self):
            raise AssertionError("前置校验不应发送刷新请求")

    class AvailableHelper:
        def get_services(self, type_filter=None):
            assert type_filter == "emby"
            return {"家庭 Emby": type("Service", (), {"instance": FakeEmby()})()}

    monkeypatch.setattr(plugin_module, "MediaServerHelper", AvailableHelper)
    accepted = plugin._validate_config(_valid_config(media_server_refresh=True))
    assert accepted["valid"] is True
    assert accepted["features"]["media_server_refresh"]["valid"] is True


def test_validate_delete_sync_requires_valid_local_mapping(monkeypatch):
    """删除同步没有有效本地映射时不能开启。"""
    monkeypatch.setattr(plugin_module.settings, "API_TOKEN", "", raising=False)
    plugin = _make_plugin()

    result = plugin._validate_config(
        _valid_config(
            enabled=False,
            delete_sync=True,
            rules=[
                {
                    "enabled": True,
                    "cd2_prefix": "/影视库",
                    "pan_prefix": "/影视库",
                    "local_path": "relative/path",
                }
            ],
        )
    )

    assert result["valid"] is False
    assert result["feature_errors"]["delete_sync"]
    assert any(error["field"] == "delete_sync" for error in result["errors"])


def test_init_plugin_rejects_invalid_core_without_starting(monkeypatch):
    """初始化遇到无效核心配置时关闭插件并留下脱敏错误。"""
    monkeypatch.setattr(plugin_module.settings, "API_TOKEN", "system-test-token", raising=False)
    plugin = _init_test_plugin()
    secret = "cd2-init-secret-token"

    plugin.init_plugin(
        _valid_config(
            enabled=True,
            cd2_endpoint="",
            cd2_token=secret,
            rules=[],
        )
    )

    assert plugin._config["enabled"] is False
    assert plugin._stats["running"] is False
    assert "CD2 gRPC 地址无效" in plugin._stats["last_error"]
    assert secret not in plugin._stats["last_error"]
    assert secret not in str(plugin._status_snapshot())


def test_init_plugin_closes_invalid_optional_features_and_syncs_poll_status(
    monkeypatch,
):
    """初始化会关闭缺少前置的可选功能，并同步轮询状态统计。"""
    monkeypatch.setattr(plugin_module.settings, "API_TOKEN", "", raising=False)

    class EmptyHelper:
        def get_services(self, type_filter=None):
            assert type_filter == "emby"
            return {}

    monkeypatch.setattr(plugin_module, "MediaServerHelper", EmptyHelper)
    plugin = _init_test_plugin()
    plugin.init_plugin(
        {
            "enabled": False,
            "poll_fallback_enabled": True,
            "delete_sync": True,
            "media_server_refresh": True,
            "scrape_metadata": True,
            "auto_download_mediainfo": True,
        }
    )

    assert plugin._config["poll_fallback_enabled"] is False
    assert plugin._config["delete_sync"] is False
    assert plugin._config["media_server_refresh"] is False
    assert plugin._config["scrape_metadata"] is False
    assert plugin._config["auto_download_mediainfo"] is False
    assert plugin._stats["poll_fallback_enabled"] is False
    assert plugin._stats["last_error"]


def test_status_usage_tab_has_only_local_back_action():
    """状态页说明子页只保留返回总览，不重复显示全局 footer 动作。"""
    remote = (
        Path(__file__).parents[1]
        / "plugins.v2/cd2uploadstrmtrigger/dist/assets/remoteEntry.js"
    ).read_text(encoding="utf-8")
    page = remote.split("async function createPageModule()", 1)[1]

    assert 'createUsageView(h, () => { activeTab.value = "overview"; })' in page
    assert 'activeTab.value !== "usage"\n          ? h("div", { class: "cd2-trigger-actions cd2-trigger-footer" }' in page
    assert 'button("使用说明"' not in page
    assert page.count('button("设置"') == 1
    assert page.count('button("关闭"') == 1
