"""SQLite persistence for fetched posts and comment drafts."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DRAFT_STATUSES = frozenset({"pending", "approved", "rejected", "posted", "error", "scheduled"})
DRAFT_KINDS = frozenset({"comment", "submission"})
PROJECT_PURPOSES = frozenset({"product", "personal", "custom"})
DEFAULT_PROJECT_ID = "default"

_DRAFT_SELECT = """
            SELECT d.id, d.post_id, d.account_name, d.body, d.status, d.error, d.permalink,
                   d.created_at, d.updated_at, d.run_at, d.comment_id,
                   d.outcome_score, d.outcome_replies, d.outcome_removed, d.outcomes_polled_at,
                   d.kind, d.submission_id, d.target_subreddit, d.project_id, d.variants,
                   COALESCE(p.subreddit, d.target_subreddit) AS subreddit,
                   COALESCE(p.title, d.title) AS title,
                   COALESCE(p.selftext, '') AS selftext,
                   COALESCE(p.url, '') AS url,
                   p.permalink AS post_permalink,
                   p.created_utc,
                   p.top_comments,
                   p.relevance_score,
                   p.score_reasons
            FROM drafts d
            LEFT JOIN posts p ON p.id = d.post_id AND p.project_id = d.project_id
"""


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
        self._local = threading.local()

    def connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            # SSE/stream handlers run on a different thread than the request.
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            self._local.conn = conn
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

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
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                purpose TEXT NOT NULL DEFAULT 'product',
                briefing TEXT NOT NULL DEFAULT '',
                goals TEXT NOT NULL DEFAULT '[]',
                links TEXT NOT NULL DEFAULT '[]',
                interview_messages TEXT NOT NULL DEFAULT '[]',
                tone TEXT NOT NULL DEFAULT '',
                persona TEXT NOT NULL DEFAULT '',
                avoid TEXT NOT NULL DEFAULT '',
                subreddits TEXT NOT NULL DEFAULT '[]',
                keywords TEXT NOT NULL DEFAULT '[]',
                search_queries TEXT NOT NULL DEFAULT '[]',
                queries_fingerprint TEXT NOT NULL DEFAULT '',
                complete INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS posts (
                id TEXT NOT NULL,
                project_id TEXT NOT NULL DEFAULT 'default',
                subreddit TEXT NOT NULL,
                title TEXT NOT NULL,
                selftext TEXT NOT NULL,
                url TEXT NOT NULL,
                permalink TEXT NOT NULL,
                created_utc REAL NOT NULL,
                top_comments TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (project_id, id)
            );

            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT,
                project_id TEXT NOT NULL DEFAULT 'default',
                account_name TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT,
                permalink TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'comment',
                title TEXT,
                target_subreddit TEXT,
                submission_id TEXT,
                variants TEXT NOT NULL DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                action TEXT NOT NULL,
                draft_id INTEGER,
                post_id TEXT,
                project_id TEXT,
                detail TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status);
            CREATE INDEX IF NOT EXISTS idx_drafts_account_status ON drafts(account_name, status);
            CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_events(created_at DESC);
            """
        )

        self._ensure_default_project(conn)
        self._migrate_posts_project_scope(conn)
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
        self._add_column_if_missing(conn, "drafts", "kind", "TEXT NOT NULL DEFAULT 'comment'")
        self._add_column_if_missing(conn, "drafts", "title", "TEXT")
        self._add_column_if_missing(conn, "drafts", "target_subreddit", "TEXT")
        self._add_column_if_missing(conn, "drafts", "submission_id", "TEXT")
        self._add_column_if_missing(conn, "drafts", "project_id", "TEXT NOT NULL DEFAULT 'default'")
        self._add_column_if_missing(conn, "drafts", "variants", "TEXT NOT NULL DEFAULT '[]'")
        self._add_column_if_missing(conn, "audit_events", "project_id", "TEXT")
        self._add_column_if_missing(conn, "projects", "setup_step", "INTEGER NOT NULL DEFAULT 0")
        self._migrate_drafts_nullable_post_id(conn)
        self._migrate_drafts_invalid_post_fk(conn)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_drafts_project ON drafts(project_id, status)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_project ON posts(project_id)")

        conn.commit()
        logger.debug("Ensured schema at %s", self.db_path)

    def _ensure_default_project(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT id FROM projects WHERE id = ?", (DEFAULT_PROJECT_ID,)).fetchone()
        if row:
            return
        now = _utc_now_iso()
        conn.execute(
            """
            INSERT INTO projects (
                id, name, purpose, briefing, goals, links, interview_messages,
                tone, persona, avoid, subreddits, keywords, search_queries,
                queries_fingerprint, complete, created_at, updated_at
            ) VALUES (?, '', 'product', '', '[]', '[]', '[]', '', '', '', '[]', '[]', '[]', '', 0, ?, ?)
            """,
            (DEFAULT_PROJECT_ID, now, now),
        )

    def _migrate_posts_project_scope(self, conn: sqlite3.Connection) -> None:
        """Rebuild posts with composite PK (project_id, id) when upgrading older DBs."""
        info = {row["name"]: row for row in conn.execute("PRAGMA table_info(posts)").fetchall()}
        if not info:
            return
        pk_cols = [row["name"] for row in conn.execute("PRAGMA table_info(posts)").fetchall() if row["pk"]]
        has_project = "project_id" in info
        if has_project and "project_id" in pk_cols:
            return

        extra_cols = [
            name
            for name in (
                "relevance_score",
                "score_reasons",
                "skipped",
                "keywords_matched",
                "intent_labels",
            )
            if name in info
        ]
        extra_select = "".join(f", {name}" for name in extra_cols)
        extra_insert = "".join(f", {name}" for name in extra_cols)
        project_select = "project_id" if has_project else f"'{DEFAULT_PROJECT_ID}'"

        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DROP TABLE IF EXISTS posts_migrated")
        conn.executescript(
            f"""
            CREATE TABLE posts_migrated (
                id TEXT NOT NULL,
                project_id TEXT NOT NULL DEFAULT 'default',
                subreddit TEXT NOT NULL,
                title TEXT NOT NULL,
                selftext TEXT NOT NULL,
                url TEXT NOT NULL,
                permalink TEXT NOT NULL,
                created_utc REAL NOT NULL,
                top_comments TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                relevance_score REAL DEFAULT 0,
                score_reasons TEXT DEFAULT '[]',
                skipped INTEGER DEFAULT 0,
                keywords_matched TEXT DEFAULT '[]',
                intent_labels TEXT DEFAULT '[]',
                PRIMARY KEY (project_id, id)
            );

            INSERT INTO posts_migrated (
                id, project_id, subreddit, title, selftext, url, permalink,
                created_utc, top_comments, fetched_at
                {extra_insert}
            )
            SELECT
                id, {project_select}, subreddit, title, selftext, url, permalink,
                created_utc, top_comments, fetched_at
                {extra_select}
            FROM posts;

            DROP TABLE posts;
            ALTER TABLE posts_migrated RENAME TO posts;
            CREATE INDEX IF NOT EXISTS idx_posts_project ON posts(project_id);
            """
        )
        conn.execute("PRAGMA foreign_keys = ON")

    def _migrate_drafts_nullable_post_id(self, conn: sqlite3.Connection) -> None:
        """Allow NULL post_id for submission drafts; unique per project when post_id is set."""
        info = {row["name"]: row for row in conn.execute("PRAGMA table_info(drafts)").fetchall()}
        post_col = info.get("post_id")
        if post_col is None:
            return
        has_project = "project_id" in info
        unique_ok = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_drafts_post_id_unique'"
        ).fetchone()
        if int(post_col["notnull"] or 0) == 0 and unique_ok and has_project:
            conn.execute("DROP INDEX IF EXISTS idx_drafts_post_id_unique")
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_drafts_project_post_unique
                ON drafts(project_id, post_id) WHERE post_id IS NOT NULL
                """
            )
            return
        if int(post_col["notnull"] or 0) == 0 and has_project:
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_drafts_project_post_unique
                ON drafts(project_id, post_id) WHERE post_id IS NOT NULL
                """
            )
            return

        project_select = "project_id" if has_project else f"'{DEFAULT_PROJECT_ID}'"
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.executescript(
            f"""
            CREATE TABLE drafts_migrated (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT,
                project_id TEXT NOT NULL DEFAULT 'default',
                account_name TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT,
                permalink TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                run_at TEXT,
                comment_id TEXT,
                outcome_score INTEGER,
                outcome_replies INTEGER,
                outcome_removed INTEGER DEFAULT 0,
                outcomes_polled_at TEXT,
                kind TEXT NOT NULL DEFAULT 'comment',
                title TEXT,
                target_subreddit TEXT,
                submission_id TEXT
            );

            INSERT INTO drafts_migrated (
                id, post_id, project_id, account_name, body, status, error, permalink,
                created_at, updated_at, run_at, comment_id,
                outcome_score, outcome_replies, outcome_removed, outcomes_polled_at,
                kind, title, target_subreddit, submission_id
            )
            SELECT
                id, post_id, {project_select}, account_name, body, status, error, permalink,
                created_at, updated_at, run_at, comment_id,
                outcome_score, outcome_replies, outcome_removed, outcomes_polled_at,
                COALESCE(kind, 'comment'), title, target_subreddit, submission_id
            FROM drafts;

            DROP TABLE drafts;
            ALTER TABLE drafts_migrated RENAME TO drafts;

            CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status);
            CREATE INDEX IF NOT EXISTS idx_drafts_account_status ON drafts(account_name, status);
            CREATE INDEX IF NOT EXISTS idx_drafts_project ON drafts(project_id, status);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_drafts_project_post_unique
                ON drafts(project_id, post_id) WHERE post_id IS NOT NULL;
            """
        )
        conn.execute("PRAGMA foreign_keys = ON")

    def _migrate_drafts_invalid_post_fk(self, conn: sqlite3.Connection) -> None:
        """Drop drafts.post_id → posts(id) after posts moved to a composite PK."""
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='drafts'"
        ).fetchone()
        if exists is None:
            return
        fks = conn.execute("PRAGMA foreign_key_list(drafts)").fetchall()
        if not fks:
            return
        grouped: dict[int, list[Any]] = {}
        for row in fks:
            grouped.setdefault(int(row["id"]), []).append(row)
        invalid = False
        for parts in grouped.values():
            mapping = {(str(row["from"]), str(row["to"])) for row in parts}
            if mapping == {("post_id", "id")}:
                invalid = True
        if not invalid:
            return

        info = {row["name"]: row for row in conn.execute("PRAGMA table_info(drafts)").fetchall()}

        def col(name: str, fallback: str) -> str:
            return name if name in info else fallback

        conn.execute("PRAGMA foreign_keys = OFF")
        conn.executescript(
            f"""
            DROP TABLE IF EXISTS drafts_migrated;
            CREATE TABLE drafts_migrated (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT,
                project_id TEXT NOT NULL DEFAULT 'default',
                account_name TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT,
                permalink TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                run_at TEXT,
                comment_id TEXT,
                outcome_score INTEGER,
                outcome_replies INTEGER,
                outcome_removed INTEGER DEFAULT 0,
                outcomes_polled_at TEXT,
                kind TEXT NOT NULL DEFAULT 'comment',
                title TEXT,
                target_subreddit TEXT,
                submission_id TEXT,
                variants TEXT NOT NULL DEFAULT '[]'
            );

            INSERT INTO drafts_migrated (
                id, post_id, project_id, account_name, body, status, error, permalink,
                created_at, updated_at, run_at, comment_id,
                outcome_score, outcome_replies, outcome_removed, outcomes_polled_at,
                kind, title, target_subreddit, submission_id, variants
            )
            SELECT
                id,
                post_id,
                {col("project_id", "'default'")},
                account_name,
                body,
                status,
                error,
                permalink,
                created_at,
                updated_at,
                {col("run_at", "NULL")},
                {col("comment_id", "NULL")},
                {col("outcome_score", "NULL")},
                {col("outcome_replies", "NULL")},
                {col("outcome_removed", "0")},
                {col("outcomes_polled_at", "NULL")},
                {col("kind", "'comment'")},
                {col("title", "NULL")},
                {col("target_subreddit", "NULL")},
                {col("submission_id", "NULL")},
                {col("variants", "'[]'")}
            FROM drafts;

            DROP TABLE drafts;
            ALTER TABLE drafts_migrated RENAME TO drafts;

            CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status);
            CREATE INDEX IF NOT EXISTS idx_drafts_account_status ON drafts(account_name, status);
            CREATE INDEX IF NOT EXISTS idx_drafts_project ON drafts(project_id, status);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_drafts_project_post_unique
                ON drafts(project_id, post_id) WHERE post_id IS NOT NULL;
            """
        )
        conn.execute("PRAGMA foreign_keys = ON")

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
        project_id: str = DEFAULT_PROJECT_ID,
    ) -> None:
        conn = self.connect()
        comments_json = top_comments if isinstance(top_comments, str) else json.dumps(top_comments)
        fetched_at = _utc_now_iso()
        conn.execute(
            """
            INSERT INTO posts (
                id, project_id, subreddit, title, selftext, url, permalink,
                created_utc, top_comments, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, id) DO UPDATE SET
                subreddit = excluded.subreddit,
                title = excluded.title,
                selftext = excluded.selftext,
                url = excluded.url,
                permalink = excluded.permalink,
                created_utc = excluded.created_utc,
                top_comments = excluded.top_comments,
                fetched_at = excluded.fetched_at
            """,
            (
                id,
                project_id,
                subreddit,
                title,
                selftext,
                url,
                permalink,
                created_utc,
                comments_json,
                fetched_at,
            ),
        )
        conn.commit()

    def update_post(
        self,
        post_id: str,
        *,
        project_id: str = DEFAULT_PROJECT_ID,
        **fields: Any,
    ) -> None:
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
        values = list(fields.values()) + [project_id, post_id]

        conn = self.connect()
        conn.execute(
            f"UPDATE posts SET {columns} WHERE project_id = ? AND id = ?",
            values,
        )
        conn.commit()

    def list_posts(
        self,
        *,
        project_id: str = DEFAULT_PROJECT_ID,
        undrafted: bool | None = None,
        skipped: bool | None = None,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        conn = self.connect()
        clauses: list[str] = ["p.project_id = ?"]
        params: list[Any] = [project_id]

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

        where = f"WHERE {' AND '.join(clauses)}"
        join = (
            "LEFT JOIN drafts d ON d.post_id = p.id AND d.project_id = p.project_id"
            if undrafted is not None
            else ""
        )

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

    def list_posts_without_draft(
        self, *, project_id: str = DEFAULT_PROJECT_ID
    ) -> list[dict[str, Any]]:
        return self.list_posts(project_id=project_id, undrafted=True)

    def get_post(
        self, post_id: str, *, project_id: str = DEFAULT_PROJECT_ID
    ) -> dict[str, Any] | None:
        conn = self.connect()
        row = conn.execute(
            "SELECT * FROM posts WHERE project_id = ? AND id = ?",
            (project_id, post_id),
        ).fetchone()
        return self._row_post(row) if row else None

    def create_draft(
        self,
        post_id: str,
        account_name: str,
        body: str,
        status: str = "pending",
        *,
        kind: str = "comment",
        title: str | None = None,
        target_subreddit: str | None = None,
        project_id: str = DEFAULT_PROJECT_ID,
    ) -> int:
        if status not in DRAFT_STATUSES:
            raise ValueError(f"Invalid draft status: {status}")
        if kind not in DRAFT_KINDS:
            raise ValueError(f"Invalid draft kind: {kind}")
        if kind == "comment" and not post_id:
            raise ValueError("Comment drafts require post_id")
        if kind == "submission" and (not title or not target_subreddit):
            raise ValueError("Submission drafts require title and target_subreddit")

        now = _utc_now_iso()
        conn = self.connect()
        cursor = conn.execute(
            """
            INSERT INTO drafts (
                post_id, project_id, account_name, body, status, error, permalink,
                created_at, updated_at, kind, title, target_subreddit
            )
            VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?)
            """,
            (
                post_id if kind == "comment" else None,
                project_id,
                account_name,
                body,
                status,
                now,
                now,
                kind,
                title,
                target_subreddit,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)

    def create_submission_draft(
        self,
        *,
        account_name: str,
        subreddit: str,
        title: str,
        body: str,
        status: str = "pending",
        project_id: str = DEFAULT_PROJECT_ID,
    ) -> int:
        return self.create_draft(
            "",
            account_name,
            body,
            status,
            kind="submission",
            title=title.strip(),
            target_subreddit=subreddit.strip().lstrip("r/"),
            project_id=project_id,
        )

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
            "kind",
            "title",
            "target_subreddit",
            "submission_id",
            "variants",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unknown draft fields: {', '.join(sorted(unknown))}")

        if "status" in fields and fields["status"] not in DRAFT_STATUSES:
            raise ValueError(f"Invalid draft status: {fields['status']}")
        if "kind" in fields and fields["kind"] not in DRAFT_KINDS:
            raise ValueError(f"Invalid draft kind: {fields['kind']}")

        fields = dict(fields)
        if "variants" in fields and not isinstance(fields["variants"], str):
            fields["variants"] = json.dumps(fields["variants"])
        fields["updated_at"] = _utc_now_iso()

        columns = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [draft_id]

        conn = self.connect()
        conn.execute(f"UPDATE drafts SET {columns} WHERE id = ?", values)
        conn.commit()

    def get_draft(self, draft_id: int) -> dict[str, Any] | None:
        conn = self.connect()
        row = conn.execute(
            _DRAFT_SELECT + " WHERE d.id = ?",
            (draft_id,),
        ).fetchone()
        return self._row_draft(row) if row else None

    def list_drafts(
        self,
        status: str | None = None,
        *,
        project_id: str | None = DEFAULT_PROJECT_ID,
    ) -> list[dict[str, Any]]:
        conn = self.connect()
        if status is not None and status not in DRAFT_STATUSES and status != "all":
            raise ValueError(f"Invalid draft status: {status}")

        clauses: list[str] = []
        params: list[Any] = []
        if project_id:
            clauses.append("d.project_id = ?")
            params.append(project_id)
        if status is not None and status != "all":
            clauses.append("d.status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            _DRAFT_SELECT + f" {where} ORDER BY d.created_at DESC",
            params,
        ).fetchall()
        return [self._row_draft(row) for row in rows]

    def list_posted_for_outcomes(self, limit: int = 20) -> list[dict[str, Any]]:
        """Posted comment drafts needing outcome poll, oldest poll first."""
        conn = self.connect()
        rows = conn.execute(
            _DRAFT_SELECT
            + """
            WHERE d.status = 'posted'
              AND COALESCE(d.kind, 'comment') = 'comment'
            ORDER BY (d.outcomes_polled_at IS NULL) DESC, d.outcomes_polled_at ASC, d.id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._row_draft(row) for row in rows]

    def list_scheduled_due(self, now_iso: str) -> list[dict[str, Any]]:
        conn = self.connect()
        rows = conn.execute(
            _DRAFT_SELECT
            + """
            WHERE d.status = 'scheduled'
              AND d.run_at IS NOT NULL
              AND d.run_at <= ?
            ORDER BY d.run_at ASC
            """,
            (now_iso,),
        ).fetchall()
        return [self._row_draft(row) for row in rows]

    def list_scheduled(self, *, project_id: str | None = DEFAULT_PROJECT_ID) -> list[dict[str, Any]]:
        conn = self.connect()
        if project_id:
            rows = conn.execute(
                _DRAFT_SELECT
                + """
                WHERE d.status = 'scheduled' AND d.project_id = ?
                ORDER BY d.run_at ASC
                """,
                (project_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                _DRAFT_SELECT
                + """
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
        project_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> int:
        conn = self.connect()
        cursor = conn.execute(
            """
            INSERT INTO audit_events (created_at, action, draft_id, post_id, project_id, detail)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                _utc_now_iso(),
                action,
                draft_id,
                post_id,
                project_id,
                json.dumps(detail) if detail else None,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)

    def list_audit(
        self,
        limit: int = 100,
        *,
        project_id: str | None = DEFAULT_PROJECT_ID,
    ) -> list[dict[str, Any]]:
        conn = self.connect()
        if project_id:
            rows = conn.execute(
                """
                SELECT id, created_at, action, draft_id, post_id, project_id, detail
                FROM audit_events
                WHERE project_id IS NULL OR project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, created_at, action, draft_id, post_id, project_id, detail
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

    def count_drafts_by_status(
        self, *, project_id: str | None = DEFAULT_PROJECT_ID
    ) -> dict[str, int]:
        conn = self.connect()
        if project_id:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS cnt FROM drafts WHERE project_id = ? GROUP BY status",
                (project_id,),
            ).fetchall()
        else:
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

    def create_project(
        self,
        *,
        purpose: str,
        name: str = "",
        project_id: str | None = None,
        briefing: str = "",
        goals: list[str] | None = None,
        links: list[dict[str, Any]] | None = None,
        interview_messages: list[dict[str, Any]] | None = None,
        tone: str = "",
        persona: str = "",
        avoid: str = "",
        subreddits: list[str] | None = None,
        keywords: list[str] | None = None,
        complete: bool = False,
    ) -> dict[str, Any]:
        if purpose not in PROJECT_PURPOSES:
            raise ValueError(f"Invalid project purpose: {purpose}")
        now = _utc_now_iso()
        if project_id is None:
            unused = self.get_project(DEFAULT_PROJECT_ID)
            if unused and self._project_is_unused(unused):
                updated = self.update_project(
                    DEFAULT_PROJECT_ID,
                    name=name,
                    purpose=purpose,
                    briefing=briefing,
                    goals=goals or [],
                    links=links or [],
                    interview_messages=interview_messages or [],
                    tone=tone,
                    persona=persona,
                    avoid=avoid,
                    subreddits=subreddits or [],
                    keywords=keywords or [],
                    complete=complete,
                )
                if updated is None:
                    raise RuntimeError("Failed to initialize default project")
                return updated
            pid = uuid.uuid4().hex
        else:
            pid = project_id
        existing = self.get_project(pid)
        if existing:
            updated = self.update_project(
                pid,
                name=name or existing["name"],
                purpose=purpose,
                briefing=briefing,
                goals=goals if goals is not None else existing["goals"],
                links=links if links is not None else existing["links"],
                interview_messages=(
                    interview_messages
                    if interview_messages is not None
                    else existing["interview_messages"]
                ),
                tone=tone,
                persona=persona,
                avoid=avoid,
                subreddits=subreddits if subreddits is not None else existing["subreddits"],
                keywords=keywords if keywords is not None else existing["keywords"],
                complete=complete,
            )
            if updated is None:
                raise RuntimeError(f"Failed to update project {pid}")
            return updated
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO projects (
                id, name, purpose, briefing, goals, links, interview_messages,
                tone, persona, avoid, subreddits, keywords, search_queries,
                queries_fingerprint, complete, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', '', ?, ?, ?)
            """,
            (
                pid,
                name,
                purpose,
                briefing,
                json.dumps(goals or []),
                json.dumps(links or []),
                json.dumps(interview_messages or []),
                tone,
                persona,
                avoid,
                json.dumps(subreddits or []),
                json.dumps(keywords or []),
                1 if complete else 0,
                now,
                now,
            ),
        )
        conn.commit()
        project = self.get_project(pid)
        if project is None:
            raise RuntimeError("Failed to create project")
        return project

    def find_setup_project(self) -> dict[str, Any] | None:
        """Most recently updated project still in the interview/review setup flow."""
        in_setup: list[dict[str, Any]] = []
        for project in self.list_projects(include_empty=True):
            step = int(project.get("setup_step") or 0)
            if step in {3, 4, 5}:
                in_setup.append(project)
        if not in_setup:
            return None
        return max(in_setup, key=lambda item: str(item.get("updated_at") or ""))

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        conn = self.connect()
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return self._row_project(row) if row else None

    def list_projects(self, *, include_empty: bool = False) -> list[dict[str, Any]]:
        conn = self.connect()
        rows = conn.execute("SELECT * FROM projects ORDER BY created_at ASC").fetchall()
        projects = [self._row_project(row) for row in rows]
        if include_empty:
            return projects
        visible: list[dict[str, Any]] = []
        for project in projects:
            if (
                project["complete"]
                or (project.get("briefing") or "").strip()
                or project.get("subreddits")
            ):
                visible.append(project)
        return visible

    def update_project(self, project_id: str, **fields: Any) -> dict[str, Any] | None:
        allowed = {
            "name",
            "purpose",
            "briefing",
            "goals",
            "links",
            "interview_messages",
            "tone",
            "persona",
            "avoid",
            "subreddits",
            "keywords",
            "search_queries",
            "queries_fingerprint",
            "complete",
            "setup_step",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unknown project fields: {', '.join(sorted(unknown))}")
        if "purpose" in fields and fields["purpose"] not in PROJECT_PURPOSES:
            raise ValueError(f"Invalid project purpose: {fields['purpose']}")

        payload = dict(fields)
        json_fields = {
            "goals",
            "links",
            "interview_messages",
            "subreddits",
            "keywords",
            "search_queries",
        }
        for key in json_fields:
            if key in payload and not isinstance(payload[key], str):
                payload[key] = json.dumps(payload[key])
        if "complete" in payload:
            payload["complete"] = 1 if payload["complete"] else 0
        if "setup_step" in payload:
            payload["setup_step"] = int(payload["setup_step"] or 0)
        payload["updated_at"] = _utc_now_iso()

        columns = ", ".join(f"{key} = ?" for key in payload)
        values = list(payload.values()) + [project_id]
        conn = self.connect()
        conn.execute(f"UPDATE projects SET {columns} WHERE id = ?", values)
        conn.commit()
        return self.get_project(project_id)

    def list_post_ids(self, *, project_id: str = DEFAULT_PROJECT_ID) -> set[str]:
        conn = self.connect()
        rows = conn.execute(
            "SELECT id FROM posts WHERE project_id = ?", (project_id,)
        ).fetchall()
        return {row["id"] for row in rows}

    def draft_exists_for_post(
        self, post_id: str, *, project_id: str = DEFAULT_PROJECT_ID
    ) -> bool:
        conn = self.connect()
        row = conn.execute(
            "SELECT id FROM drafts WHERE project_id = ? AND post_id = ?",
            (project_id, post_id),
        ).fetchone()
        return row is not None

    @staticmethod
    def _row_project(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        for key in (
            "goals",
            "links",
            "interview_messages",
            "subreddits",
            "keywords",
            "search_queries",
        ):
            data[key] = Store._parse_json_list(data.get(key))
        data["complete"] = bool(data.get("complete", 0))
        data["setup_step"] = int(data.get("setup_step") or 0)
        return data

    @staticmethod
    def _project_is_unused(project: dict[str, Any]) -> bool:
        return not (
            project.get("complete")
            or (project.get("briefing") or "").strip()
            or project.get("interview_messages")
            or project.get("subreddits")
        )

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
        elif raw_comments is None:
            data["top_comments"] = []
        data["score_reasons"] = Store._parse_json_list(data.get("score_reasons"))
        data["outcome_removed"] = bool(data.get("outcome_removed", 0))
        data["kind"] = data.get("kind") or "comment"
        data["relevance_score"] = data.get("relevance_score") or 0
        data["variants"] = Store._parse_variants(data.get("variants"))
        return data

    @staticmethod
    def _parse_variants(value: Any) -> list[dict[str, str]]:
        variants: list[dict[str, str]] = []
        for item in Store._parse_json_list(value):
            if not isinstance(item, dict):
                continue
            variant_id = str(item.get("id") or "").strip()
            body = str(item.get("body") or "").strip()
            label = str(item.get("label") or "").strip() or "Reply"
            if not variant_id or not body:
                continue
            variants.append({"id": variant_id, "label": label, "body": body})
        return variants
