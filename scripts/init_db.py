"""SQLiteデータベースの初期化（テーブル・VIEW作成）"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "project_mgmt.db"

DDL = """
-- 年度設定
CREATE TABLE IF NOT EXISTS fiscal_year (
    fiscal_year    INTEGER PRIMARY KEY,
    period_start   TEXT NOT NULL,
    period_end     TEXT NOT NULL,
    revenue_target INTEGER NOT NULL,
    headcount      INTEGER NOT NULL
);

-- 月別営業日数
CREATE TABLE IF NOT EXISTS monthly_calendar (
    year_month   TEXT PRIMARY KEY,
    working_days INTEGER NOT NULL,
    base_hours   REAL GENERATED ALWAYS AS (working_days * 8.0) STORED
);

-- 人員マスタ
CREATE TABLE IF NOT EXISTS members (
    id                 TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    type               TEXT NOT NULL CHECK (type IN ('internal', 'outsource', 'dispatch')),
    role               TEXT NOT NULL,
    grade              TEXT NOT NULL CHECK (grade IN ('junior', 'mid', 'senior', 'lead')),
    unit_cost          INTEGER NOT NULL,
    hourly_rate        INTEGER,
    max_capacity       REAL NOT NULL DEFAULT 1.0,
    avg_overtime_hours REAL DEFAULT 0,
    join_date          TEXT,
    contract_start     TEXT,
    contract_end       TEXT,
    note               TEXT
);

-- メンバーの保有スキル
CREATE TABLE IF NOT EXISTS member_skills (
    member_id TEXT NOT NULL REFERENCES members(id),
    skill     TEXT NOT NULL,
    level     TEXT NOT NULL CHECK (level IN ('junior', 'mid', 'senior')),
    PRIMARY KEY (member_id, skill)
);

-- 月別の個人キャパシティ（有給予定・残業時間）
CREATE TABLE IF NOT EXISTS member_capacity (
    member_id        TEXT NOT NULL REFERENCES members(id),
    year_month       TEXT NOT NULL REFERENCES monthly_calendar(year_month),
    planned_pto_days INTEGER NOT NULL DEFAULT 0,
    overtime_hours   REAL,
    PRIMARY KEY (member_id, year_month)
);

-- 案件マスタ
CREATE TABLE IF NOT EXISTS projects (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    client              TEXT NOT NULL,
    status              TEXT NOT NULL CHECK (status IN
                          ('planned', 'in_progress', 'on_hold', 'completed', 'cancelled')),
    priority            TEXT NOT NULL CHECK (priority IN ('high', 'medium', 'low')),
    start_date          TEXT NOT NULL,
    end_date            TEXT NOT NULL,
    pm                  TEXT REFERENCES members(id),
    contract_status     TEXT NOT NULL DEFAULT 'planned'
                          CHECK (contract_status IN ('planned', 'delayed', 'signed')),
    original_work_start TEXT NOT NULL,
    actual_work_start   TEXT NOT NULL,
    delay_note          TEXT,
    budget_this_fy      INTEGER,
    budget_next_fy      INTEGER,
    note                TEXT
);

-- 案件の予算内訳
CREATE TABLE IF NOT EXISTS project_budgets (
    project_id     TEXT PRIMARY KEY REFERENCES projects(id),
    labor_cost     INTEGER NOT NULL DEFAULT 0,
    outsource_cost INTEGER NOT NULL DEFAULT 0,
    expense        INTEGER NOT NULL DEFAULT 0,
    total          INTEGER GENERATED ALWAYS AS (labor_cost + outsource_cost + expense) STORED
);

-- 案件の必要スキル
CREATE TABLE IF NOT EXISTS project_required_skills (
    project_id TEXT NOT NULL REFERENCES projects(id),
    skill      TEXT NOT NULL,
    level      TEXT NOT NULL CHECK (level IN ('junior', 'mid', 'senior')),
    need_count INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (project_id, skill)
);

-- マイルストーン
CREATE TABLE IF NOT EXISTS milestones (
    id             TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL REFERENCES projects(id),
    name           TEXT NOT NULL,
    due_date       TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'not_started'
                     CHECK (status IN ('not_started', 'in_progress', 'completed', 'delayed')),
    completion_pct INTEGER NOT NULL DEFAULT 0 CHECK (completion_pct BETWEEN 0 AND 100)
);

-- 年間アサイン計画
CREATE TABLE IF NOT EXISTS assignments_plan (
    member_id       TEXT NOT NULL REFERENCES members(id),
    project_id      TEXT NOT NULL REFERENCES projects(id),
    year_month      TEXT NOT NULL,
    allocation      REAL NOT NULL CHECK (allocation BETWEEN 0.0 AND 1.5),
    role_in_project TEXT NOT NULL,
    PRIMARY KEY (member_id, project_id, year_month)
);

-- アサイン実績
CREATE TABLE IF NOT EXISTS assignments_actual (
    member_id       TEXT NOT NULL REFERENCES members(id),
    project_id      TEXT NOT NULL REFERENCES projects(id),
    year_month      TEXT NOT NULL,
    actual_hours    REAL NOT NULL,
    role_in_project TEXT NOT NULL,
    source          TEXT NOT NULL CHECK (source IN ('teamspirit', 'manual')),
    note            TEXT,
    PRIMARY KEY (member_id, project_id, year_month)
);

-- 年間予算計画（月別・内訳3区分 + 売上予測）
CREATE TABLE IF NOT EXISTS budget_plan (
    project_id             TEXT NOT NULL REFERENCES projects(id),
    year_month             TEXT NOT NULL,
    planned_labor_cost     INTEGER NOT NULL DEFAULT 0,
    planned_outsource_cost INTEGER NOT NULL DEFAULT 0,
    planned_expense        INTEGER NOT NULL DEFAULT 0,
    planned_revenue        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (project_id, year_month)
);

-- コスト実績（月別・内訳3区分）
CREATE TABLE IF NOT EXISTS budget_actual (
    project_id             TEXT NOT NULL REFERENCES projects(id),
    year_month             TEXT NOT NULL,
    actual_labor_cost      INTEGER NOT NULL DEFAULT 0,
    actual_outsource_cost  INTEGER NOT NULL DEFAULT 0,
    actual_expense         INTEGER NOT NULL DEFAULT 0,
    source                 TEXT NOT NULL CHECK (source IN ('sap', 'manual')),
    note                   TEXT,
    PRIMARY KEY (project_id, year_month)
);

-- 進捗記録
CREATE TABLE IF NOT EXISTS progress (
    project_id             TEXT NOT NULL REFERENCES projects(id),
    year_month             TEXT NOT NULL,
    overall_completion_pct INTEGER NOT NULL CHECK (overall_completion_pct BETWEEN 0 AND 100),
    note                   TEXT,
    PRIMARY KEY (project_id, year_month)
);
"""

VIEWS = """
-- 実効キャパシティVIEW
-- 営業日数・有給予定・残業時間から個人×月の実効キャパシティを算出
DROP VIEW IF EXISTS v_effective_capacity;
CREATE VIEW v_effective_capacity AS
SELECT
    mc.member_id,
    mc.year_month,
    m.name AS member_name,
    cal.working_days,
    mc.planned_pto_days,
    (cal.working_days - mc.planned_pto_days) AS effective_working_days,
    (cal.working_days - mc.planned_pto_days) * 8.0 AS base_effective_hours,
    COALESCE(mc.overtime_hours, m.avg_overtime_hours, 0) AS overtime_hours,
    (cal.working_days - mc.planned_pto_days) * 8.0
      + COALESCE(mc.overtime_hours, m.avg_overtime_hours, 0) AS effective_hours,
    cal.working_days * 8.0 AS base_hours,
    ROUND(
      ((cal.working_days - mc.planned_pto_days) * 8.0
        + COALESCE(mc.overtime_hours, m.avg_overtime_hours, 0))
      / (cal.working_days * 8.0), 3
    ) AS effective_capacity
FROM member_capacity mc
JOIN monthly_calendar cal ON mc.year_month = cal.year_month
JOIN members m ON mc.member_id = m.id;

-- アサイン実績VIEW（allocation自動算出）
DROP VIEW IF EXISTS v_assignments_actual;
CREATE VIEW v_assignments_actual AS
SELECT
    aa.*,
    cal.base_hours,
    ROUND(aa.actual_hours / cal.base_hours, 3) AS allocation
FROM assignments_actual aa
JOIN monthly_calendar cal ON aa.year_month = cal.year_month;
"""


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(DDL)
    conn.executescript(VIEWS)
    conn.commit()
    conn.close()
    print(f"Database initialized: {DB_PATH}")


if __name__ == "__main__":
    init_db()
