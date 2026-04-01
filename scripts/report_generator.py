"""月次レポート生成"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils.db import connect
from utils.kpi import (
    budget_burn,
    compression_ratio,
    dept_utilization,
    progress_gap,
    utilization_by_member,
)
from alerts import run_all_alerts

REPORT_DIR = Path(__file__).resolve().parent.parent / "reports" / "monthly"


def generate_report(year_month: str) -> str:
    conn = connect()

    dept_rate = dept_utilization(conn, year_month)
    members = utilization_by_member(conn, year_month)
    burns = budget_burn(conn)
    gaps = progress_gap(conn, year_month)
    compressed = compression_ratio(conn)
    alerts = run_all_alerts(conn, year_month)

    fy = conn.execute("SELECT * FROM fiscal_year WHERE fiscal_year = 2026").fetchone()
    revenue_target = dict(fy)["revenue_target"] if fy else 0

    total_planned_revenue = conn.execute(
        "SELECT COALESCE(SUM(planned_revenue), 0) FROM budget_plan WHERE year_month <= ?",
        (year_month,),
    ).fetchone()[0]

    alert_count = len(alerts)
    critical = sum(1 for a in alerts if a["level"] == "危険")
    warnings = sum(1 for a in alerts if a["level"] == "警告")

    lines = []
    lines.append(f"# 月次レポート: {year_month}")
    lines.append("")

    # サマリ
    lines.append("## 1. エグゼクティブサマリ")
    lines.append("")
    lines.append(f"- 部署稼働率: **{dept_rate * 100:.0f}%**")
    lines.append(
        f"- 累計売上予測: {total_planned_revenue:,}円 / 目標 {revenue_target:,}円"
    )
    lines.append(f"- アラート: {alert_count}件（危険{critical} / 警告{warnings}）")
    lines.append("")

    # 稼働率
    lines.append("## 2. 人員稼働状況")
    lines.append("")
    lines.append("| 氏名 | 種別 | 割当計 | 実効キャパ | 稼働率 | 状態 |")
    lines.append("|------|------|--------|-----------|--------|------|")
    for m in members:
        rate = m["utilization_rate"]
        status = (
            "危険"
            if rate > 1.0
            else "注意"
            if rate > 0.95
            else "余剰"
            if rate < 0.5
            else "適正"
        )
        lines.append(
            f"| {m['name']} | {m['type']} | {m['total_allocation']:.2f} "
            f"| {m['effective_capacity']:.3f} | {rate * 100:.0f}% | {status} |"
        )
    lines.append("")

    # 予算
    lines.append("## 3. 予算消化状況")
    lines.append("")
    lines.append("| 案件 | 予算 | 実績 | 消化率 | 内訳 |")
    lines.append("|------|------|------|--------|------|")
    for b in burns:
        lines.append(
            f"| {b['project_name']} | {b['budget_total']:,} | {b['actual_total']:,} "
            f"| {b['burn_rate_total'] * 100:.0f}% "
            f"| 人{b['burn_rate_labor'] * 100:.0f}%/外{b['burn_rate_outsource'] * 100:.0f}%/経{b['burn_rate_expense'] * 100:.0f}% |"
        )
    lines.append("")

    # 進捗
    lines.append("## 4. 進捗状況")
    lines.append("")
    lines.append("| 案件 | 実績 | 期待 | 乖離 | 状態 |")
    lines.append("|------|------|------|------|------|")
    for g in gaps:
        pct = g["overall_completion_pct"]
        if pct is not None:
            gap = g["gap"]
            expected = g["expected_completion_pct"]
            status = (
                "要対策" if gap and gap > 30 else "警告" if gap and gap > 15 else "順調"
            )
            gap_str = (
                f"+{gap:.0f}pt" if gap and gap > 0 else f"{gap:.0f}pt" if gap else "-"
            )
            lines.append(
                f"| {g['project_name']} | {pct}% | {expected:.0f}% | {gap_str} | {status} |"
            )
        else:
            lines.append(
                f"| {g['project_name']} | - | - | - | {g['contract_status']} |"
            )
    lines.append("")

    # 遅延
    if compressed:
        lines.append("## 5. 契約遅延案件")
        lines.append("")
        lines.append("| 案件 | 当初 | 実際 | 圧縮率 | 備考 |")
        lines.append("|------|------|------|--------|------|")
        for c in compressed:
            lines.append(
                f"| {c['project_name']} | {c['original_work_start']} "
                f"| {c['actual_work_start']} | {c['ratio']}x | {c['delay_note'] or ''} |"
            )
        lines.append("")

    # アラート
    if alerts:
        lines.append("## 6. アラート")
        lines.append("")
        level_order = {"危険": 0, "警告": 1, "注意": 2, "情報": 3}
        alerts.sort(key=lambda a: level_order.get(a["level"], 9))
        for a in alerts:
            lines.append(f"- **[{a['level']}]** {a['type']}: {a['message']}")
        lines.append("")

    # AI分析用プレースホルダ
    lines.append("## 7. AI分析コメント")
    lines.append("")
    lines.append("<!-- Claude Code が分析結果に基づき記入 -->")
    lines.append("")

    conn.close()
    return "\n".join(lines)


def main() -> None:
    ym = (
        sys.argv[1]
        if len(sys.argv) > 1
        else __import__("datetime").date.today().strftime("%Y-%m")
    )
    report = generate_report(ym)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{ym}_monthly_report.md"
    path.write_text(report, encoding="utf-8")
    print(f"レポート生成: {path}")


if __name__ == "__main__":
    main()
