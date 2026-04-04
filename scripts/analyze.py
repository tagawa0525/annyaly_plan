"""メイン分析スクリプト"""

import argparse
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

from utils.db import connect
from utils.kpi import (
    budget_burn,
    compression_ratio,
    dept_utilization,
    progress_gap,
    utilization_by_member,
)
from alerts import run_all_alerts


def tabulate(rows: list[list], headers: list[str], **_: object) -> str:
    """簡易テーブル表示（tabulate互換）"""
    if not rows:
        return "(データなし)"
    all_rows = [headers] + [[str(c) for c in r] for r in rows]
    widths = [max(len(r[i]) for r in all_rows) for i in range(len(headers))]
    header_line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    sep = "  ".join("-" * w for w in widths)
    body = "\n".join(
        "  ".join(str(c).ljust(w) for c, w in zip(r, widths)) for r in all_rows[1:]
    )
    return f"{header_line}\n{sep}\n{body}"


def print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def analyze(year_month: str) -> None:
    conn = connect()

    # --- 1. 部署サマリ ---
    print_section(f"部署サマリ ({year_month})")
    dept_rate = dept_utilization(conn, year_month)
    active = conn.execute(
        "SELECT COUNT(*) FROM projects WHERE status IN ('in_progress', 'planned')"
    ).fetchone()[0]
    delayed = conn.execute(
        "SELECT COUNT(*) FROM projects WHERE contract_status = 'delayed'"
    ).fetchone()[0]
    alerts = run_all_alerts(conn, year_month)
    print(f"  部署稼働率: {dept_rate * 100:.0f}%")
    print(f"  アクティブ案件: {active}件（うち遅延: {delayed}件）")
    print(f"  アラート: {len(alerts)}件")

    # --- 2. 個人別稼働率 ---
    print_section("個人別稼働率")
    members = utilization_by_member(conn, year_month)
    table = []
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
        table.append(
            [
                m["name"],
                m["type"],
                f"{m['total_allocation']:.2f}",
                f"{m['effective_capacity']:.3f}",
                f"{rate * 100:.0f}%",
                status,
                m["data_source"],
            ]
        )
    print(
        tabulate(
            table,
            headers=[
                "氏名",
                "種別",
                "割当計",
                "実効キャパ",
                "稼働率",
                "状態",
                "データ",
            ],
            tablefmt="simple",
        )
    )

    # --- 3. 予算消化状況 ---
    print_section("予算消化状況")
    burns = budget_burn(conn)
    table = []
    for b in burns:
        table.append(
            [
                b["project_name"],
                f"{b['budget_total']:,}",
                f"{b['actual_total']:,}",
                f"{b['burn_rate_total'] * 100:.0f}%",
                f"人{b['burn_rate_labor'] * 100:.0f}% / 外{b['burn_rate_outsource'] * 100:.0f}% / 経{b['burn_rate_expense'] * 100:.0f}%",
            ]
        )
    print(
        tabulate(
            table,
            headers=["案件", "予算総額", "実績総額", "消化率", "内訳消化率"],
            tablefmt="simple",
        )
    )

    # --- 4. 進捗状況 ---
    print_section("進捗状況")
    gaps = progress_gap(conn, year_month)
    table = []
    for g in gaps:
        pct = g["overall_completion_pct"]
        expected = g["expected_completion_pct"]
        gap = g["gap"]
        if pct is None:
            table.append([g["project_name"], "-", "-", "-", g["contract_status"]])
        else:
            status = (
                "要対策" if gap and gap > 30 else "警告" if gap and gap > 15 else "順調"
            )
            table.append(
                [
                    g["project_name"],
                    f"{pct}%",
                    f"{expected:.0f}%" if expected else "-",
                    f"+{gap:.0f}pt"
                    if gap and gap > 0
                    else f"{gap:.0f}pt"
                    if gap
                    else "-",
                    status,
                ]
            )
    print(
        tabulate(
            table, headers=["案件", "実績", "期待", "乖離", "状態"], tablefmt="simple"
        )
    )

    # --- 5. 契約遅延 ---
    delayed_projects = compression_ratio(conn)
    if delayed_projects:
        print_section("契約遅延案件")
        table = []
        for c in delayed_projects:
            table.append(
                [
                    c["project_name"],
                    c["original_work_start"],
                    c["actual_work_start"],
                    f"{c['ratio']}x",
                    c["delay_note"] or "",
                ]
            )
        print(
            tabulate(
                table,
                headers=["案件", "当初開始", "実際開始", "圧縮率", "備考"],
                tablefmt="simple",
            )
        )

    # --- 6. アラート ---
    if alerts:
        print_section("アラート")
        level_order = {"危険": 0, "警告": 1, "注意": 2, "情報": 3}
        alerts.sort(key=lambda a: level_order.get(a["level"], 9))
        for a in alerts:
            print(f"  [{a['level']}] {a['type']}: {a['message']}")

    conn.close()


def impact_analysis(project_id: str) -> None:
    """突発案件の影響分析"""
    conn = connect()
    project = conn.execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    if not project:
        print(f"案件 {project_id} が見つかりません")
        conn.close()
        return

    print_section(f"影響分析: {dict(project)['name']} ({project_id})")

    # この案件のアサイン計画を取得
    rows = conn.execute(
        """
        SELECT ap.year_month, ap.member_id, m.name, ap.allocation
        FROM assignments_plan ap
        JOIN members m ON ap.member_id = m.id
        WHERE ap.project_id = ?
        ORDER BY ap.year_month, m.name
    """,
        (project_id,),
    ).fetchall()

    if not rows:
        print("  アサイン計画なし")
        conn.close()
        return

    # 月ごとに、この案件を追加した場合の各人の合計稼働率を計算
    months = sorted(set(dict(r)["year_month"] for r in rows))
    print("\n  この案件を追加した場合の影響:")
    overloaded = []
    for ym in months:
        month_members = [dict(r) for r in rows if dict(r)["year_month"] == ym]
        for mm in month_members:
            existing = conn.execute(
                """
                SELECT COALESCE(SUM(allocation), 0) AS current_alloc
                FROM assignments_plan
                WHERE member_id = ? AND year_month = ? AND project_id != ?
            """,
                (mm["member_id"], ym, project_id),
            ).fetchone()
            current = existing["current_alloc"] if existing else 0
            new_total = current + mm["allocation"]
            if new_total > 0.95:
                overloaded.append(
                    (ym, mm["name"], current, mm["allocation"], new_total)
                )

    if overloaded:
        table = [
            [
                ym,
                name,
                f"{cur:.2f}",
                f"+{add:.2f}",
                f"{total:.2f}",
                "危険" if total > 1.0 else "注意",
            ]
            for ym, name, cur, add, total in overloaded
        ]
        print(
            tabulate(
                table,
                headers=["月", "氏名", "既存割当", "追加分", "合計", "状態"],
                tablefmt="simple",
            )
        )
    else:
        print("  溢れる人はいません")

    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="プロジェクト分析")
    parser.add_argument("year_month", nargs="?", help="対象月 (YYYY-MM)")
    parser.add_argument("--impact", help="突発案件の影響分析 (project_id)")
    args = parser.parse_args()

    if args.impact:
        impact_analysis(args.impact)
    else:
        ym = args.year_month or __import__("datetime").date.today().strftime("%Y-%m")
        analyze(ym)


if __name__ == "__main__":
    main()
