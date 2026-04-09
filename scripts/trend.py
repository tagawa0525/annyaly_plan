#!/usr/bin/env python3
"""月次トレンド分析CLIエントリーポイント"""

import argparse
import csv
import re
import sys
from datetime import date
from pathlib import Path

from utils.db import connect
from utils.trend import utilization_trend, budget_trend, progress_trend


def print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def _default_range() -> tuple[str, str]:
    """デフォルト: 直近6ヶ月"""
    today = date.today()
    y, m = today.year, today.month
    # 6ヶ月前
    m -= 5
    if m <= 0:
        m += 12
        y -= 1
    start = f"{y:04d}-{m:02d}"
    end = today.strftime("%Y-%m")
    return start, end


def _validate_ym(value: str) -> str:
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", value):
        raise argparse.ArgumentTypeError(f"無効な年月: {value}")
    return value


def show_utilization(conn, start, end) -> list[list]:
    """稼働率トレンドを表示"""
    print_section(f"稼働率トレンド ({start} 〜 {end})")
    data = utilization_trend(conn, start, end)

    print(f"{'月':<10}{'稼働率':>8}")
    print(f"{'-' * 10}{'-' * 8}")
    rows = []
    for d in data:
        rate_str = f"{d['rate'] * 100:.0f}%" if d["rate"] else "-"
        print(f"{d['year_month']:<10}{rate_str:>8}")
        rows.append([d["year_month"], d["rate"]])
    return rows


def show_budget(conn, start, end) -> list[list]:
    """予算消化トレンドを表示"""
    print_section(f"予算消化トレンド ({start} 〜 {end})")
    data = budget_trend(conn, start, end)

    print(f"{'月':<10}{'計画累計':>14}{'実績累計':>14}{'消化率':>8}")
    print(f"{'-' * 10}{'-' * 14}{'-' * 14}{'-' * 8}")
    rows = []
    for d in data:
        planned = f"{d['planned_cumulative']:>13,}"
        actual = f"{d['actual_cumulative']:>13,}"
        rate = f"{d['burn_rate'] * 100:.1f}%" if d["burn_rate"] else "-"
        print(f"{d['year_month']:<10}{planned}{actual}{rate:>8}")
        rows.append(
            [
                d["year_month"],
                d["planned_cumulative"],
                d["actual_cumulative"],
                d["burn_rate"],
            ]
        )
    return rows


def show_progress(conn, start, end) -> list[list]:
    """進捗トレンドを表示"""
    print_section(f"進捗トレンド ({start} 〜 {end})")
    data = progress_trend(conn, start, end)

    if not data:
        print("(データなし)")
        return []

    # Collect months
    all_months = sorted(
        set(ym for d in data for ym in d["months"]),
    )
    # Short month labels (MM)
    month_labels = [ym[5:7] for ym in all_months]

    header = f"{'案件':<20}" + "".join(f"{ml:>6}" for ml in month_labels)
    print(header)
    print("-" * len(header))

    rows = []
    for d in data:
        name = d["project_name"][:18]
        cells = []
        for ym in all_months:
            pct = d["months"].get(ym)
            cells.append(f"{pct}%" if pct is not None else "-")
        print(f"{name:<20}" + "".join(f"{c:>6}" for c in cells))
        row = [d["project_id"], d["project_name"]]
        row.extend(d["months"].get(ym) for ym in all_months)
        rows.append(row)

    return rows


def export_csv(conn, start, end, output_dir: Path) -> None:
    """CSVファイルにエクスポート"""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Utilization CSV
    util_data = utilization_trend(conn, start, end)
    with open(output_dir / "trend_utilization.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["year_month", "rate"])
        writer.writeheader()
        writer.writerows(util_data)

    # Budget CSV
    budget_data = budget_trend(conn, start, end)
    with open(output_dir / "trend_budget.csv", "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "year_month",
                "planned_cumulative",
                "actual_cumulative",
                "burn_rate",
            ],
        )
        writer.writeheader()
        writer.writerows(budget_data)

    # Progress CSV
    prog_data = progress_trend(conn, start, end)
    if prog_data:
        all_months = sorted(set(ym for d in prog_data for ym in d["months"]))
        with open(output_dir / "trend_progress.csv", "w", newline="") as f:
            fieldnames = ["project_id", "project_name"] + all_months
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for d in prog_data:
                row = {
                    "project_id": d["project_id"],
                    "project_name": d["project_name"],
                }
                row.update({ym: d["months"].get(ym, "") for ym in all_months})
                writer.writerow(row)

    print(f"CSVエクスポート完了: {output_dir}/trend_*.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description="月次トレンド分析")
    parser.add_argument(
        "start_month", nargs="?", type=_validate_ym, help="開始月 (YYYY-MM)"
    )
    parser.add_argument(
        "end_month", nargs="?", type=_validate_ym, help="終了月 (YYYY-MM)"
    )
    parser.add_argument("--csv", action="store_true", help="CSV出力")
    args = parser.parse_args()

    if args.start_month and args.end_month:
        start, end = args.start_month, args.end_month
    else:
        start, end = _default_range()

    conn = connect()
    try:
        if args.csv:
            export_csv(conn, start, end, Path("data/export"))

        show_utilization(conn, start, end)
        show_budget(conn, start, end)
        show_progress(conn, start, end)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
