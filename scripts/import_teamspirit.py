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
                    INSERT INTO assignments_actual
                    (member_id, project_id, year_month, actual_hours, role_in_project, source, note)
                    VALUES (?, ?, ?, ?, ?, 'teamspirit', NULL)
                    ON CONFLICT(member_id, project_id, year_month) DO UPDATE SET
                        actual_hours = excluded.actual_hours,
                        role_in_project = excluded.role_in_project,
                        source = excluded.source
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
        print(f"TeamSpirit: {count}件インポート完了 ({year_month})")
    finally:
        conn.close()


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python import_teamspirit.py YYYY-MM file.csv", file=sys.stderr)
        sys.exit(1)
    try:
        import_csv(sys.argv[1], sys.argv[2])
    except (FileNotFoundError, ValueError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
