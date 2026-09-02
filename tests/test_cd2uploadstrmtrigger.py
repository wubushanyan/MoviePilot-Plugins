"""CD2 上传触发 115 STRM 插件的纯逻辑测试。"""

import threading

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
    plugin._refresh_emby_batch(
        [{"pan_path": "/影视库/电影/a.mkv"}, {"pan_path": "/影视库/电影/b.mkv"}]
    )
    assert fake_emby.calls == 1
    assert plugin._stats["emby_refresh_batch_count"] == 1
    assert plugin._stats["emby_refresh_request_count"] == 1
