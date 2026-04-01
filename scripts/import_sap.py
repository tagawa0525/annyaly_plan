"""SAP CSV → budget_actual へのインポート

想定CSVフォーマット:
  プロジェクトコード,年月,人件費,外注費,経費
  P001,2026-04,800000,280000,150000
"""

import csv
import sys
from pathlib import Path

from utils.db import connect


def import_csv(year_month: str, csv_path: str) -> None:
    path = Path(csv_path)
    if not path.exists():
        print(f"ファイルが見つかりません: {csv_path}")
        sys.exit(1)

    conn = connect()
    count = 0

    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            conn.execute(
                """
                INSERT OR REPLACE INTO budget_actual
                (project_id, year_month, actual_labor_cost, actual_outsource_cost,
                 actual_expense, source, note)
                VALUES (?, ?, ?, ?, ?, 'sap', NULL)
            """,
                (
                    row["プロジェクトコード"],
                    year_month,
                    int(row["人件費"]),
                    int(row["外注費"]),
                    int(row["経費"]),
                ),
            )
            count += 1

    conn.commit()
    conn.close()
    print(f"SAP: {count}件インポート完了 ({year_month})")


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python import_sap.py YYYY-MM file.csv")
        sys.exit(1)
    import_csv(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
