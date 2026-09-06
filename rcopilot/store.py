"""SQLite persistence for fetched posts and comment drafts."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DRAFT_STATUSES = frozenset({"pending", "approved", "rejected", "posted", "error", "scheduled"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class Store:
    """SQLite-backed store for posts and drafts."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _column_exists(self, conn: sqlite3.Connection, table: str, column: str) -> bool:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any(row["name"] == column for row in rows)

    def _add_column_if_missing(
        self,
        conn: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        if not self._column_exists(conn, table, column):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def ensure_schema(self) -> None:
        conn = self.connect()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS posts (
                id TEXT PRIMARY KEY,
                subreddit TEXT NOT NULL,
                title TEXT NOT NULL,
                selftext TEXT NOT NULL,
                url TEXT NOT NULL,
                permalink TEXT NOT NULL,
                created_utc REAL NOT NULL,
                top_comments TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT NOT NULL UNIQUE,
                account_name TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT,
                permalink TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (post_id) REFERENCES posts(id)
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                action TEXT NOT NULL,
                draft_id INTEGER,
                post_id TEXT,
                detail TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status);
            CREATE INDEX IF NOT EXISTS idx_drafts_account_status ON drafts(account_name, status);
            CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_events(created_at DESC);
            """
        )

        self._add_column_if_missing(conn, "posts", "relevance_score", "REAL DEFAULT 0")
        self._add_column_if_missing(conn, "posts", "score_reasons", "TEXT DEFAULT '[]'")
        self._add_column_if_missing(conn, "posts", "skipped", "INTEGER DEFAULT 0")
        self._add_column_if_missing(conn, "posts", "keywords_matched", "TEXT DEFAULT '[]'")
        self._add_column_if_missing(conn, "posts", "intent_labels", "TEXT DEFAULT '[]'")
        self._add_column_if_missing(conn, "drafts", "run_at", "TEXT")
        self._add_column_if_missing(conn, "drafts", "comment_id", "TEXT")
        self._add_column_if_missing(conn, "drafts", "outcome_score", "INTEGER")
        self._add_column_if_missing(conn, "drafts", "outcome_replies", "INTEGER")
        self._add_column_if_missing(conn, "drafts", "outcome_removed", "INTEGER DEFAULT 0")
        self._add_column_if_missing(conn, "drafts", "outcomes_polled_at", "TEXT")

        conn.commit()
        logger.debug("Ensured schema at %s", self.db_path)

    def upsert_post(
        self,
        *,
        id: str,
        subreddit: str,
        title: str,
        selftext: str,
        url: str,
        permalink: str,
        created_utc: float,
        top_comments: list[dict[str, Any]] | str,
    ) -> None:
        conn = self.connect()
        comments_json = top_comments if isinstance(top_comments, str) else json.dumps(top_comments)
        fetched_at = _utc_now_iso()
        conn.execute(
            """
            INSERT INTO posts (
                id, subreddit, title, selftext, url, permalink,
                created_utc, top_comments, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                subreddit = excluded.subreddit,
                title = excluded.title,
                selftext = excluded.selftext,
                url = excluded.url,
                permalink = excluded.permalink,
                created_utc = excluded.created_utc,
                top_comments = excluded.top_comments,
                fetched_at = excluded.fetched_at
            """,
            (id, subreddit, title, selftext, url, permalink, created_utc, comments_json, fetched_at),
        )
        conn.commit()

    def update_post(self, post_id: str, **fields: Any) -> None:
        if not fields:
            return

        allowed = {
            "relevance_score",
            "score_reasons",
            "skipped",
            "keywords_matched",
            "intent_labels",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unknown post fields: {', '.join(sorted(unknown))}")

        columns = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [post_id]

        conn = self.connect()
        conn.execute(f"UPDATE posts SET {columns} WHERE id = ?", values)
        conn.commit()

    def list_posts(
        self,
        *,
        undrafted: bool | None = None,
        skipped: bool | None = None,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        conn = self.connect()
        clauses: list[str] = []
        params: list[Any] = []

        if undrafted is True:
            clauses.append("d.id IS NULL")
        elif undrafted is False:
            clauses.append("d.id IS NOT NULL")

        if skipped is not None:
            clauses.append("p.skipped = ?")
            params.append(1 if skipped else 0)

        if min_score is not None:
            clauses.append("p.relevance_score >= ?")
            params.append(min_score)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        join = "LEFT JOIN drafts d ON d.post_id = p.id" if undrafted is not None else ""

        rows = conn.execute(
            f"""
            SELECT p.*
            FROM posts p
            {join}
            {where}
            ORDER BY p.relevance_score DESC, p.created_utc DESC
            """,
            params,
        ).fetchall()
        return [self._row_post(row) for row in rows]

    def list_posts_without_draft(self) -> list[dict[str, Any]]:
        return self.list_posts(undrafted=True)

    def get_post(self, post_id: str) -> dict[str, Any] | None:
        conn = self.connect()
        row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
        return self._row_post(row) if row else None

    def create_draft(
        self,
        post_id: str,
        account_name: str,
        body: str,
        status: str = "pending",
    ) -> int:
        if status not in DRAFT_STATUSES:
            raise ValueError(f"Invalid draft status: {status}")

        now = _utc_now_iso()
        conn = self.connect()
        cursor = conn.execute(
            """
            INSERT INTO drafts (post_id, account_name, body, status, error, permalink, created_at, updated_at)
            VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)
            """,
            (post_id, account_name, body, status, now, now),
        )
        conn.commit()
        return int(cursor.lastrowid)

    def update_draft(self, draft_id: int, **fields: Any) -> None:
        if not fields:
            return

        allowed = {
            "post_id",
            "account_name",
            "body",
            "status",
            "error",
            "permalink",
            "run_at",
            "comment_id",
            "outcome_score",
            "outcome_replies",
            "outcome_removed",
            "outcomes_polled_at",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unknown draft fields: {', '.join(sorted(unknown))}")

        if "status" in fields and fields["status"] not in DRAFT_STATUSES:
            raise ValueError(f"Invalid draft status: {fields['status']}")

        fields = dict(fields)
        fields["updated_at"] = _utc_now_iso()

        columns = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [draft_id]

        conn = self.connect()
        conn.execute(f"UPDATE drafts SET {columns} WHERE id = ?", values)
        conn.commit()

    def get_draft(self, draft_id: int) -> dict[str, Any] | None:
        conn = self.connect()
        row = conn.execute(
            """
            SELECT d.*,
                   p.subreddit, p.title, p.selftext, p.url,
                   p.permalink AS post_permalink, p.created_utc, p.top_comments,
                   p.relevance_score, p.score_reasons
            FROM drafts d
            JOIN posts p ON p.id = d.post_id
            WHERE d.id = ?
            """,
            (draft_id,),
        ).fetchone()
        return self._row_draft(row) if row else None

    def list_drafts(self, status: str | None = None) -> list[dict[str, Any]]:
        conn = self.connect()
        if status is not None and status not in DRAFT_STATUSES and status != "all":
            raise ValueError(f"Invalid draft status: {status}")

        base_query = """
            SELECT d.*,
                   p.subreddit, p.title, p.selftext, p.url,
                   p.permalink AS post_permalink, p.created_utc, p.top_comments,
                   p.relevance_score, p.score_reasons
            FROM drafts d
            JOIN posts p ON p.id = d.post_id
        """

        if status is None or status == "all":
            rows = conn.execute(
                base_query + " ORDER BY d.created_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                base_query + " WHERE d.status = ? ORDER BY d.created_at DESC",
                (status,),
            ).fetchall()
        return [self._row_draft(row) for row in rows]

    def list_posted_for_outcomes(self, limit: int = 20) -> list[dict[str, Any]]:
        """Posted drafts needing outcome poll, oldest poll first (never-polled first)."""
        conn = self.connect()
        rows = conn.execute(
            """
            SELECT d.*,
                   p.subreddit, p.title, p.selftext, p.url,
                   p.permalink AS post_permalink, p.created_utc, p.top_comments,
                   p.relevance_score, p.score_reasons
            FROM drafts d
            JOIN posts p ON p.id = d.post_id
            WHERE d.status = 'posted'
            ORDER BY (d.outcomes_polled_at IS NULL) DESC, d.outcomes_polled_at ASC, d.id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._row_draft(row) for row in rows]

    def list_scheduled_due(self, now_iso: str) -> list[dict[str, Any]]:
        conn = self.connect()
        rows = conn.execute(
            """
            SELECT d.*,
                   p.subreddit, p.title, p.selftext, p.url,
                   p.permalink AS post_permalink, p.created_utc, p.top_comments,
                   p.relevance_score, p.score_reasons
            FROM drafts d
            JOIN posts p ON p.id = d.post_id
            WHERE d.status = 'scheduled'
              AND d.run_at IS NOT NULL
              AND d.run_at <= ?
            ORDER BY d.run_at ASC
            """,
            (now_iso,),
        ).fetchall()
        return [self._row_draft(row) for row in rows]

    def list_scheduled(self) -> list[dict[str, Any]]:
        conn = self.connect()
        rows = conn.execute(
            """
            SELECT d.*,
                   p.subreddit, p.title, p.selftext, p.url,
                   p.permalink AS post_permalink, p.created_utc, p.top_comments,
                   p.relevance_score, p.score_reasons
            FROM drafts d
            JOIN posts p ON p.id = d.post_id
            WHERE d.status = 'scheduled'
            ORDER BY d.run_at ASC
            """
        ).fetchall()
        return [self._row_draft(row) for row in rows]

    def cancel_schedule(self, draft_id: int) -> None:
        draft = self.get_draft(draft_id)
        if draft is None:
            raise ValueError(f"Draft not found: {draft_id}")
        if draft["status"] != "scheduled":
            raise ValueError(f"Draft {draft_id} is not scheduled (status={draft['status']})")
        self.update_draft(draft_id, status="pending", run_at=None)

    def add_audit(
        self,
        action: str,
        *,
        draft_id: int | None = None,
        post_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> int:
        conn = self.connect()
        cursor = conn.execute(
            """
            INSERT INTO audit_events (created_at, action, draft_id, post_id, detail)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                _utc_now_iso(),
                action,
                draft_id,
                post_id,
                json.dumps(detail) if detail else None,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)

    def list_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        conn = self.connect()
        rows = conn.execute(
            """
            SELECT id, created_at, action, draft_id, post_id, detail
            FROM audit_events
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            raw_detail = data.get("detail")
            if isinstance(raw_detail, str):
                data["detail"] = json.loads(raw_detail)
            results.append(data)
        return results

    def count_drafts_by_status(self) -> dict[str, int]:
        conn = self.connect()
        rows = conn.execute(
            "SELECT status, COUNT(*) AS cnt FROM drafts GROUP BY status"
        ).fetchall()
        counts = {status: 0 for status in DRAFT_STATUSES}
        for row in rows:
            counts[row["status"]] = int(row["cnt"])
        return counts

    def count_posted_today(self, account_name: str) -> int:
        conn = self.connect()
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        start_iso = start.isoformat()
        row = conn.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM drafts
            WHERE account_name = ?
              AND status = 'posted'
              AND updated_at >= ?
            """,
            (account_name, start_iso),
        ).fetchone()
        return int(row["cnt"]) if row else 0

    def get_last_posted_at(self, account_name: str) -> datetime | None:
        conn = self.connect()
        row = conn.execute(
            """
            SELECT MAX(updated_at) AS last_posted
            FROM drafts
            WHERE account_name = ?
              AND status = 'posted'
            """,
            (account_name,),
        ).fetchone()
        return _parse_iso(row["last_posted"]) if row and row["last_posted"] else None

    @staticmethod
    def _parse_json_list(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return []
        return []

    @staticmethod
    def _row_post(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        raw_comments = data.get("top_comments")
        if isinstance(raw_comments, str):
            data["top_comments"] = json.loads(raw_comments)
        data["score_reasons"] = Store._parse_json_list(data.get("score_reasons"))
        data["keywords_matched"] = Store._parse_json_list(data.get("keywords_matched"))
        data["intent_labels"] = Store._parse_json_list(data.get("intent_labels"))
        data["skipped"] = bool(data.get("skipped", 0))
        return data

    @staticmethod
    def _row_draft(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        raw_comments = data.get("top_comments")
        if isinstance(raw_comments, str):
            data["top_comments"] = json.loads(raw_comments)
        data["score_reasons"] = Store._parse_json_list(data.get("score_reasons"))
        data["outcome_removed"] = bool(data.get("outcome_removed", 0))
        return data
