from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional


class CacheDB:
    def __init__(self, path: str = ".cache/nail_verifier_v3.sqlite3"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS http_cache (
                cache_key TEXT PRIMARY KEY,
                body TEXT NOT NULL,
                fetched_at REAL NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS verification_cache (
                record_key TEXT NOT NULL,
                engine_version TEXT NOT NULL,
                payload TEXT NOT NULL,
                checked_at REAL NOT NULL,
                PRIMARY KEY(record_key, engine_version)
            )
            """
        )
        self.conn.commit()

    def get_http(self, cache_key: str, ttl_seconds: int) -> Optional[str]:
        row = self.conn.execute(
            "SELECT body, fetched_at FROM http_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        if not row:
            return None
        body, fetched_at = row
        if ttl_seconds >= 0 and time.time() - float(fetched_at) > ttl_seconds:
            return None
        return str(body)

    def set_http(self, cache_key: str, body: str) -> None:
        self.conn.execute(
            """
            INSERT INTO http_cache(cache_key, body, fetched_at)
            VALUES (?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET body=excluded.body, fetched_at=excluded.fetched_at
            """,
            (cache_key, body, time.time()),
        )
        self.conn.commit()

    def get_verification(self, record_key: str, engine_version: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT payload FROM verification_cache WHERE record_key = ? AND engine_version = ?",
            (record_key, engine_version),
        ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            return None

    def set_verification(self, record_key: str, engine_version: str, payload: Dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO verification_cache(record_key, engine_version, payload, checked_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(record_key, engine_version)
            DO UPDATE SET payload=excluded.payload, checked_at=excluded.checked_at
            """,
            (record_key, engine_version, json.dumps(payload, ensure_ascii=False), time.time()),
        )
        self.conn.commit()

    def clear_verification(self) -> None:
        self.conn.execute("DELETE FROM verification_cache")
        self.conn.commit()

    def stats(self) -> Dict[str, int]:
        http_count = self.conn.execute("SELECT COUNT(*) FROM http_cache").fetchone()[0]
        verification_count = self.conn.execute("SELECT COUNT(*) FROM verification_cache").fetchone()[0]
        return {"http_cache": int(http_count), "verification_cache": int(verification_count)}
