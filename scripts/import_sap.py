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
        raise FileNotFoundError(f"ファイルが見つかりません: {csv_path}")

    conn = connect()
    count = 0

    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["年月"] != year_month:
                    raise ValueError(
                        f"CSV内の年月 '{row['年月']}' が引数 '{year_month}' と不一致"
                    )
                conn.execute(
                    """
                    INSERT INTO budget_actual
                    (project_id, year_month, actual_labor_cost, actual_outsource_cost,
                     actual_expense, source, note)
                    VALUES (?, ?, ?, ?, ?, 'sap', NULL)
                    ON CONFLICT(project_id, year_month) DO UPDATE SET
                        actual_labor_cost = excluded.actual_labor_cost,
                        actual_outsource_cost = excluded.actual_outsource_cost,
                        actual_expense = excluded.actual_expense,
                        source = excluded.source
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
        print(f"SAP: {count}件インポート完了 ({year_month})")
    finally:
        conn.close()


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python import_sap.py YYYY-MM file.csv")
        sys.exit(1)
    import_csv(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
