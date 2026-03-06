"""
数据模型 & SQLite 数据库管理
"""

import sqlite3
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, List

from config import DATABASE_PATH


@dataclass
class LegislationItem:
    """一条立法/监管动态条目"""
    region: str             # 区域 (欧洲/北美/东南亚/...)
    category_l1: str        # 一级分类
    category_l2: str        # 二级分类
    title: str              # 原文标题
    date: str               # 时间 (YYYY-MM-DD)
    status: str             # 状态
    summary: str            # 原文摘要
    source_name: str        # 数据源名称
    source_url: str         # 原文链接
    lang: str = "en"        # 语言
    title_zh: str = ""      # 标题中文翻译
    summary_zh: str = ""    # 摘要中文翻译
    impact_score: int = 1   # 影响评分 1=低/2=中/3=高 (信源层级 × 状态)
    id: Optional[int] = None

    def to_dict(self):
        return asdict(self)


class Database:
    """SQLite 数据库操作"""

    def __init__(self, db_path: str = DATABASE_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS legislation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                region TEXT NOT NULL,
                category_l1 TEXT NOT NULL,
                category_l2 TEXT DEFAULT '',
                title TEXT NOT NULL,
                date TEXT NOT NULL,
                status TEXT DEFAULT '政策信号',
                summary TEXT DEFAULT '',
                source_name TEXT DEFAULT '',
                source_url TEXT DEFAULT '',
                lang TEXT DEFAULT 'en',
                title_zh TEXT DEFAULT '',
                summary_zh TEXT DEFAULT '',
                impact_score INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(title, source_url)
            );

            CREATE INDEX IF NOT EXISTS idx_region ON legislation(region);
            CREATE INDEX IF NOT EXISTS idx_category ON legislation(category_l1);
            CREATE INDEX IF NOT EXISTS idx_date ON legislation(date);

            CREATE TABLE IF NOT EXISTS fetch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_name TEXT NOT NULL,
                fetched_at TEXT DEFAULT (datetime('now')),
                item_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'ok',
                error_msg TEXT DEFAULT ''
            );
        """)
        # ── 迁移: 旧表补列 ────────────────────────────────────────────
        for col, definition in [
            ("title_zh",     "TEXT DEFAULT ''"),
            ("summary_zh",   "TEXT DEFAULT ''"),
            ("impact_score", "INTEGER DEFAULT 1"),
        ]:
            try:
                self.conn.execute(f"SELECT {col} FROM legislation LIMIT 1")
            except sqlite3.OperationalError:
                self.conn.execute(
                    f"ALTER TABLE legislation ADD COLUMN {col} {definition}"
                )
        # idx_impact 依赖 impact_score 列，必须在迁移之后再建
        self.conn.executescript(
            "CREATE INDEX IF NOT EXISTS idx_impact ON legislation(impact_score);"
        )
        self.conn.commit()

    def upsert_item(self, item: LegislationItem) -> bool:
        try:
            self.conn.execute("""
                INSERT INTO legislation
                    (region, category_l1, category_l2, title, date, status, summary,
                     source_name, source_url, lang, title_zh, summary_zh, impact_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(title, source_url) DO UPDATE SET
                    title_zh   = CASE WHEN excluded.title_zh   != '' THEN excluded.title_zh   ELSE legislation.title_zh   END,
                    summary_zh = CASE WHEN excluded.summary_zh != '' THEN excluded.summary_zh ELSE legislation.summary_zh END
            """, (
                item.region, item.category_l1, item.category_l2,
                item.title, item.date, item.status, item.summary,
                item.source_name, item.source_url, item.lang,
                item.title_zh, item.summary_zh, item.impact_score,
            ))
            self.conn.commit()
            return self.conn.total_changes > 0
        except sqlite3.Error:
            return False

    def bulk_upsert(self, items: List[LegislationItem]) -> int:
        count = 0
        for item in items:
            if self.upsert_item(item):
                count += 1
        return count

    def log_fetch(self, source_name: str, item_count: int, status: str = "ok", error_msg: str = ""):
        self.conn.execute("""
            INSERT INTO fetch_log (source_name, item_count, status, error_msg)
            VALUES (?, ?, ?, ?)
        """, (source_name, item_count, status, error_msg))
        self.conn.commit()

    def query_items(
        self,
        region: Optional[str] = None,
        category_l1: Optional[str] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
        days: int = 90,
        limit: int = 500,
    ) -> List[dict]:
        conditions = []
        params = []

        if region:
            conditions.append("region = ?")
            params.append(region)
        if category_l1:
            conditions.append("category_l1 = ?")
            params.append(category_l1)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if keyword:
            conditions.append("(title LIKE ? OR summary LIKE ? OR title_zh LIKE ? OR summary_zh LIKE ?)")
            params.extend([f"%{keyword}%"] * 4)
        if days:
            conditions.append("date >= date('now', ?)")
            params.append(f"-{days} days")

        where = " AND ".join(conditions) if conditions else "1=1"
        query = f"""
            SELECT * FROM legislation
            WHERE {where}
            ORDER BY impact_score DESC, date DESC
            LIMIT ?
        """
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_stats(self) -> dict:
        total = self.conn.execute("SELECT COUNT(*) FROM legislation").fetchone()[0]
        by_region = self.conn.execute(
            "SELECT region, COUNT(*) as cnt FROM legislation GROUP BY region ORDER BY cnt DESC"
        ).fetchall()
        by_category = self.conn.execute(
            "SELECT category_l1, COUNT(*) as cnt FROM legislation GROUP BY category_l1 ORDER BY cnt DESC"
        ).fetchall()
        latest = self.conn.execute(
            "SELECT MAX(date) FROM legislation"
        ).fetchone()[0]
        by_impact = self.conn.execute(
            "SELECT impact_score, COUNT(*) as cnt FROM legislation GROUP BY impact_score ORDER BY impact_score DESC"
        ).fetchall()
        return {
            "total": total,
            "by_region": {r["region"]: r["cnt"] for r in by_region},
            "by_category": {r["category_l1"]: r["cnt"] for r in by_category},
            "by_impact": {r["impact_score"]: r["cnt"] for r in by_impact},
            "latest_date": latest,
        }

    def clear_stale_translations(self, dirty_terms: list) -> int:
        """
        将 title_zh 或 summary_zh 中包含脏词（音译错误、栏目前缀等）的条目
        翻译字段清空，以便下次 run 时重新翻译。返回清空的条目数。
        """
        if not dirty_terms:
            return 0
        conditions = []
        params = []
        for term in dirty_terms:
            conditions.append("title_zh LIKE ? OR summary_zh LIKE ?")
            params.extend([f"%{term}%", f"%{term}%"])
        where = " OR ".join(f"({c})" for c in conditions)
        cur = self.conn.execute(
            f"UPDATE legislation SET title_zh = '', summary_zh = '' WHERE {where}",
            params,
        )
        self.conn.commit()
        return cur.rowcount

    def query_items_untranslated(self, limit: int = 200) -> List[dict]:
        """查询尚未翻译（title_zh 为空）的条目，优先处理高 impact 的。"""
        rows = self.conn.execute("""
            SELECT * FROM legislation
            WHERE title_zh = '' OR title_zh IS NULL
            ORDER BY impact_score DESC, date DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(row) for row in rows]

    def update_translation(self, item_id: int, title_zh: str, summary_zh: str):
        """直接按 id 更新翻译字段。"""
        self.conn.execute(
            "UPDATE legislation SET title_zh = ?, summary_zh = ? WHERE id = ?",
            (title_zh, summary_zh, item_id),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()
