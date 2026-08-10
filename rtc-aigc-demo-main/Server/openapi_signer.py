"""火山引擎 V4 OpenAPI 签名实现，等价于 Node SDK 的常规签名流程。"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from urllib.parse import quote


def _hash(data: bytes | str) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def _hmac(key: bytes, value: str) -> bytes:
    return hmac.new(key, value.encode(), hashlib.sha256).digest()


def sign_request(
    method: str,
    host: str,
    path: str,
    query: dict,
    body: bytes,
    access_key: str,
    secret_key: str,
    region: str = "cn-north-1",
    service: str = "rtc",
    now: datetime | None = None,
) -> dict[str, str]:
    """生成 Authorization、X-Date 等请求头；参数排序规则遵循 RFC3986。"""
    now = now or datetime.now(timezone.utc)
    date = now.strftime("%Y%m%d")
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    canonical_query = "&".join(
        f"{quote(str(k), safe='~-_.')}={quote(str(v), safe='~-_.')}"
        for k, v in sorted(query.items())
    )
    headers = {"content-type": "application/json", "host": host, "x-date": timestamp}
    signed = ";".join(sorted(headers))
    canonical_headers = "".join(
        f"{key}:{' '.join(headers[key].strip().split())}\n" for key in sorted(headers)
    )
    canonical_request = "\n".join(
        [
            method.upper(),
            path or "/",
            canonical_query,
            canonical_headers,
            signed,
            _hash(body),
        ]
    )
    scope = f"{date}/{region}/{service}/request"
    string_to_sign = "\n".join(
        ["HMAC-SHA256", timestamp, scope, _hash(canonical_request)]
    )
    k_date = _hmac(secret_key.encode(), date)
    k_region = _hmac(k_date, region)
    k_service = _hmac(k_region, service)
    signing_key = _hmac(k_service, "request")
    signature = hmac.new(
        signing_key, string_to_sign.encode(), hashlib.sha256
    ).hexdigest()
    authorization = f"HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={signed}, Signature={signature}"
    return {
        "Host": host,
        "Content-type": "application/json",
        "X-Date": timestamp,
        "Authorization": authorization,
    }
