import time
import httpx
from typing import Optional

from .manager import KeyPoolManager

MAX_FAILURES_PER_KEY = 10


class ResilientFireworksClient:
    def __init__(self):
        self.manager = KeyPoolManager()

    def _headers(self, key: str) -> dict:
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def _base_url(self) -> str:
        return "https://api.fireworks.ai"

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        seen_keys = set()
        while True:
            key = self.manager.get_active_key()
            if not key:
                raise RuntimeError("Kein API-Key verfügbar im Pool")
            if key in seen_keys and len(seen_keys) >= len(self.manager.keys):
                raise RuntimeError("Alle API-Keys erschöpft")
            seen_keys.add(key)
            headers = self._headers(key)

            failures = 0
            while failures < MAX_FAILURES_PER_KEY:
                try:
                    with httpx.Client(timeout=60) as client:
                        response = client.request(method, url, headers=headers, **kwargs)
                    if response.status_code == 429:
                        failures += 1
                        self.manager.report_failure(key)
                        wait = min(2 ** failures, 30)
                        print(f"Rate-Limit (Key {key[:12]}... fail {failures}/{MAX_FAILURES_PER_KEY}) – warte {wait}s")
                        time.sleep(wait)
                        key = self.manager.get_active_key()
                        if not key or key in seen_keys:
                            break
                        headers = self._headers(key)
                    else:
                        return response
                except httpx.HTTPError as e:
                    failures += 1
                    print(f"HTTP-Fehler: {e} – fail {failures}/{MAX_FAILURES_PER_KEY}")
                    time.sleep(min(2 ** failures, 15))
                    key = self.manager.get_active_key()
                    if not key or key in seen_keys:
                        break
                    headers = self._headers(key)
            self.manager.rotate()


client = ResilientFireworksClient()