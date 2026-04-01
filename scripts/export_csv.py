"""DB → CSVエクスポート（Git差分追跡用）"""

import csv
import sqlite3
from pathlib import Path

from utils.db import connect

EXPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "export"

TABLES = [
    "members",
    "member_skills",
    "member_capacity",
    "projects",
    "project_budgets",
    "project_required_skills",
    "milestones",
    "assignments_plan",
    "assignments_actual",
    "budget_plan",
    "budget_actual",
    "progress",
    "monthly_calendar",
    "fiscal_year",
]


def export_table(conn: sqlite3.Connection, table: str) -> None:
    cursor = conn.execute(f"SELECT * FROM {table}")  # noqa: S608
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()

    path = EXPORT_DIR / f"{table}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)


def main() -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    for table in TABLES:
        export_table(conn, table)
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
        print(f"  {table}: {count} rows")
    conn.close()
    print(f"\nExported to {EXPORT_DIR}")


if __name__ == "__main__":
    main()
