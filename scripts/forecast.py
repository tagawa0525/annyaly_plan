#!/usr/bin/env python3
"""確度別売上予測CLIエントリーポイント"""

import argparse
import sys

from utils.db import connect
from utils.kpi import revenue_forecast_weighted


def print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def main() -> None:
    parser = argparse.ArgumentParser(description="確度別売上予測")
    parser.add_argument(
        "fiscal_year", nargs="?", type=int, default=2026, help="対象年度 (default: 2026)"
    )
    args = parser.parse_args()

    conn = connect()
    try:
        result = revenue_forecast_weighted(conn, args.fiscal_year)
    finally:
        conn.close()

    if not result:
        print(f"エラー: FY{args.fiscal_year} のデータがありません", file=sys.stderr)
        sys.exit(1)

    print_section(f"売上予測 (FY{args.fiscal_year})")
    print(f"\n  目標: {result['revenue_target']:,}円")

    # 契約状態別
    print(f"\n  {'契約状態':<12}{'案件数':>6}  {'計画売上':>14}")
    for s in result["by_status"]:
        print(
            f"  {s['contract_status']:<12}{s['project_count']:>6}  {s['planned_revenue']:>14,}"
        )
    total_revenue = sum(s["planned_revenue"] for s in result["by_status"])
    total_count = sum(s["project_count"] for s in result["by_status"])
    print(f"  {'─' * 34}")
    print(f"  {'合計':<12}{total_count:>6}  {total_revenue:>14,}")

    # シナリオ別
    print(f"\n  {'シナリオ':<12}{'予測売上':>14}  {'達成率':>8}")
    labels = {"optimistic": "楽観", "standard": "標準", "pessimistic": "悲観"}
    for key, label in labels.items():
        s = result["scenarios"][key]
        rate = f"{s['achievement_rate'] * 100:.1f}%" if s["achievement_rate"] else "-"
        print(f"  {label:<12}{s['forecast_revenue']:>14,}  {rate:>8}")


if __name__ == "__main__":
    main()
