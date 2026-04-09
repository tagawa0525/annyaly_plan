#!/usr/bin/env python3
"""アサイン整合性チェックのCLIエントリーポイント"""

import sys
import re
from datetime import date

from utils.db import connect
from utils.validation import run_all_validations


def _today() -> str:
    return date.today().isoformat()


def main() -> None:
    """Main entry point"""
    # Parse year_month argument (optional, defaults to today)
    year_month = sys.argv[1] if len(sys.argv) > 1 else _today()[:7]

    # Validate format
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", year_month):
        print(f"エラー: 無効な年月フォーマット: {year_month}", file=sys.stderr)
        print("使用法: python scripts/validate.py [YYYY-MM]", file=sys.stderr)
        sys.exit(1)

    conn = connect()
    try:
        issues = run_all_validations(conn, year_month)
    finally:
        conn.close()

    if not issues:
        print("検証完了: 問題なし")
        sys.exit(0)

    # Sort by severity
    level_order = {"警告": 0, "注意": 1, "情報": 2}
    issues.sort(key=lambda a: (level_order.get(a["level"], 9), a["type"]))

    # Print issues
    for issue in issues:
        print(f"[{issue['level']}] {issue['type']}: {issue['message']}")

    # Exit with error if warnings or higher
    has_warnings = any(i["level"] == "警告" for i in issues)
    sys.exit(1 if has_warnings else 0)


if __name__ == "__main__":
    main()
