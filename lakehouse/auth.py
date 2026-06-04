# lakehouse/auth.py
"""
Token 管理。

按 tgt_svc 分别缓存 access_token，过期前 60 秒主动刷新。
"""
import sys
import time
import httpx
import config

_EXPIRE_BUFFER_MS = 60 * 1000


class TokenManager:
    """
    Envision 平台 Token 管理器。

    每个 tgt_svc 独立缓存 token，互不影响。
    即将过期（60 秒内）时自动刷新。
    """

    def __init__(self):
        self._cache: dict[str, tuple[str, int]] = {}

    def get_token(self, tgt_svc: str) -> str:
        """返回指定服务的有效 access_token。"""
        token, expired_ms = self._cache.get(tgt_svc, (None, 0))
        if token is None or int(time.time() * 1000) >= expired_ms - _EXPIRE_BUFFER_MS:
            token, expired_ms = self._refresh(tgt_svc)
        return token

    def _refresh(self, tgt_svc: str) -> tuple[str, int]:
        """向 Envision 平台申请新 token。"""
        url = f"{config.ENVISION_BASE_URL}/apis/token"
        payload = {
            "grant_type": "CREDENTIAL",
            "app_id": config.ENVISION_APP_ID,
            "app_secret": config.ENVISION_APP_SECRET,
            "tgt_svc": tgt_svc,
            "user_id": config.ENVISION_USER_ID,
        }
        resp = httpx.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        token = data["access_token"]
        expired_ms = data["expired_date"]
        self._cache[tgt_svc] = (token, expired_ms)
        remaining_sec = (expired_ms - int(time.time() * 1000)) // 1000
        print(f"[lakehouse/auth] token refreshed (tgt_svc={tgt_svc}), expires in {remaining_sec}s", file=sys.stderr)
        return token, expired_ms


token_manager = TokenManager()
