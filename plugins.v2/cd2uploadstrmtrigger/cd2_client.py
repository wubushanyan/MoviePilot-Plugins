"""CloudDrive2 gRPC 客户端封装。"""

from __future__ import annotations

import posixpath
from threading import Event
from typing import Any, Iterator, List
from urllib.parse import urlparse

import grpc
from google.protobuf.empty_pb2 import Empty

from clouddrive2_client.proto import clouddrive_pb2 as cd2_pb2
from clouddrive2_client.proto import clouddrive_pb2_grpc as cd2_pb2_grpc


class CloudDrive2Client:
    """封装 CloudDrive2 上传任务和文件下载相关的 gRPC 调用。"""

    def __init__(self, endpoint: str, token: str, timeout: int = 15, page_size: int = 200):
        """创建 CloudDrive2 gRPC 客户端。"""
        self.endpoint = self._normalize_endpoint(endpoint)
        self.token = str(token or "").strip()
        self.timeout = max(3, int(timeout or 15))
        self.page_size = max(20, min(int(page_size or 200), 1000))
        self._channel = self._create_channel()
        self._stub = cd2_pb2_grpc.CloudDriveFileSrvStub(self._channel)

    @staticmethod
    def _normalize_endpoint(endpoint: str) -> str:
        """将 CD2 地址转换为带协议的 URL。"""
        value = str(endpoint or "").strip()
        if "://" not in value:
            value = f"http://{value}"
        return value.rstrip("/")

    def _create_channel(self):
        """根据 CD2 地址创建 HTTP/2 gRPC 通道。"""
        parsed = urlparse(self.endpoint)
        host = parsed.hostname
        if not host:
            raise ValueError("CD2 地址缺少主机名")
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 19798)
        target = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
        options = (
            ("grpc.enable_http_proxy", 0),
            ("grpc.keepalive_time_ms", 30000),
            ("grpc.keepalive_timeout_ms", 10000),
            ("grpc.keepalive_permit_without_calls", 1),
        )
        if parsed.scheme.lower() == "https":
            return grpc.secure_channel(target, grpc.ssl_channel_credentials(), options=options)
        return grpc.insecure_channel(target, options=options)

    def _metadata(self):
        """构造 CloudDrive2 Bearer Token 元数据。"""
        token = self.token
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        if not token:
            return ()
        return (("authorization", f"Bearer {token}"),)

    def get_system_info(self) -> Any:
        """读取 CD2 系统信息，用于连接和权限测试。"""
        return self._stub.GetSystemInfo(Empty(), timeout=self.timeout)

    def get_upload_file_count(self) -> int:
        """读取 CD2 当前上传任务数量。"""
        result = self._stub.GetUploadFileCount(
            Empty(), metadata=self._metadata(), timeout=self.timeout
        )
        return int(getattr(result, "fileCount", 0))

    def get_upload_file_list(self) -> List[Any]:
        """读取 CD2 上传任务列表，并在服务端分页时补齐后续页面。"""
        first = self._stub.GetUploadFileList(
            cd2_pb2.GetUploadFileListRequest(
                getAll=True,
                itemsPerPage=self.page_size,
                pageNumber=0,
            ),
            metadata=self._metadata(),
            timeout=self.timeout,
        )
        items = list(first.uploadFiles)
        total = max(
            int(getattr(first, "totalCountFiltered", 0)),
            int(getattr(first, "totalCount", 0)),
        )
        if len(items) >= total or not total:
            return items
        seen = {self._item_key(item) for item in items}
        max_pages = min((total + self.page_size - 1) // self.page_size + 1, 100)
        for page in range(0, max_pages):
            result = self._stub.GetUploadFileList(
                cd2_pb2.GetUploadFileListRequest(
                    getAll=False,
                    itemsPerPage=self.page_size,
                    pageNumber=page,
                ),
                metadata=self._metadata(),
                timeout=self.timeout,
            )
            for item in result.uploadFiles:
                item_key = self._item_key(item)
                if item_key not in seen:
                    seen.add(item_key)
                    items.append(item)
            if len(items) >= total:
                break
        return items

    def get_download_url_info(self, path: str) -> dict:
        """获取指定 CD2 文件的下载地址及下载所需请求头。"""
        result = self._stub.GetDownloadUrlPath(
            cd2_pb2.GetDownloadUrlPathRequest(
                path=str(path or ""),
                preview=False,
                lazy_read=False,
                get_direct_url=True,
            ),
            metadata=self._metadata(),
            timeout=self.timeout,
        )
        return {
            "download_url_path": str(getattr(result, "downloadUrlPath", "") or ""),
            "direct_url": str(getattr(result, "directUrl", "") or ""),
            "user_agent": str(getattr(result, "userAgent", "") or ""),
            "additional_headers": dict(getattr(result, "additionalHeaders", {}) or {}),
            "expires_in": int(getattr(result, "expiresIn", 0) or 0),
        }

    def get_file_info(self, path: str) -> Any:
        """读取单个文件的最新属性，用于确认远程上传已经稳定。"""
        value = str(path or "").replace("\\", "/").strip()
        if not value.startswith("/"):
            value = "/" + value
        value = posixpath.normpath(value)
        name = posixpath.basename(value)
        if not name or value == "/":
            raise ValueError("CD2 文件路径无效")
        parent = posixpath.dirname(value) or "/"
        return self._stub.FindFileByPath(
            cd2_pb2.FindFileByPathRequest(parentPath=parent, path=name),
            metadata=self._metadata(),
            timeout=self.timeout,
        )

    @staticmethod
    def _item_key(item: Any) -> str:
        """提取上传任务列表项的去重键。"""
        key = str(getattr(item, "key", "") or "").strip()
        if key:
            return key
        return f"{getattr(item, 'destPath', '')}|{getattr(item, 'size', 0)}"

    def push_messages(self, stop_event: Event) -> Iterator[Any]:
        """持续读取 CD2 PushMessage 中的上传和文件系统变化。"""
        call = self._stub.PushMessage(Empty(), metadata=self._metadata())
        for message in call:
            if stop_event.is_set():
                call.cancel()
                return
            yield message

    def close(self) -> None:
        """关闭 gRPC 通道。"""
        if self._channel:
            self._channel.close()
            self._channel = None
