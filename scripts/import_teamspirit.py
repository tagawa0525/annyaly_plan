"""TeamSpirit CSV → assignments_actual へのインポート

想定CSVフォーマット:
  社員番号,社員名,プロジェクトコード,年月,実績時間,役割
  M001,田中太郎,P001,2026-04,88,PM
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
                INSERT OR REPLACE INTO assignments_actual
                (member_id, project_id, year_month, actual_hours, role_in_project, source, note)
                VALUES (?, ?, ?, ?, ?, 'teamspirit', NULL)
            """,
                (
                    row["社員番号"],
                    row["プロジェクトコード"],
                    year_month,
                    float(row["実績時間"]),
                    row["役割"],
                ),
            )
            count += 1

    conn.commit()
    conn.close()
    print(f"TeamSpirit: {count}件インポート完了 ({year_month})")


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python import_teamspirit.py YYYY-MM file.csv")
        sys.exit(1)
    import_csv(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
