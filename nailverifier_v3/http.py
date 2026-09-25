from __future__ import annotations

import time
from typing import Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .cache import CacheDB

USER_AGENT = "NailVerifier/3.0 (+https://github.com/hungdeniubeo/nail-verifier)"


class CachedHttpClient:
    def __init__(self, cache: CacheDB, timeout: int = 30):
        self.cache = cache
        self.timeout = timeout
        self.session = requests.Session()
        retry = Retry(
            total=3,
            read=3,
            connect=3,
            backoff_factor=0.8,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            }
        )
        self.last_request_by_host: Dict[str, float] = {}

    def get_text(
        self,
        url: str,
        cache_key: Optional[str] = None,
        ttl_seconds: int = 86400,
        min_interval_seconds: float = 0.0,
        params: Optional[Dict[str, str]] = None,
    ) -> str:
        key = cache_key or url
        cached = self.cache.get_http(key, ttl_seconds)
        if cached is not None:
            return cached

        host = requests.utils.urlparse(url).netloc
        if min_interval_seconds > 0:
            last = self.last_request_by_host.get(host, 0.0)
            wait = min_interval_seconds - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)

        response = self.session.get(url, params=params, timeout=self.timeout, allow_redirects=True)
        self.last_request_by_host[host] = time.monotonic()
        response.raise_for_status()
        text = response.text
        self.cache.set_http(key, text)
        return text
