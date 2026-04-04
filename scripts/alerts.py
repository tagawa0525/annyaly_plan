"""アラート検出（14種）"""

import sqlite3
import sys
from datetime import date

from utils.db import connect
from utils.kpi import utilization_by_member, budget_burn, compression_ratio


def _today() -> str:
    return date.today().isoformat()


def check_overloaded(conn: sqlite3.Connection, year_month: str) -> list[dict]:
    """#3 個人過負荷"""
    alerts = []
    for m in utilization_by_member(conn, year_month):
        rate = m["utilization_rate"]
        if rate > 1.0:
            alerts.append(
                {
                    "level": "危険",
                    "type": "個人過負荷",
                    "message": f"{m['name']}: 稼働率 {rate * 100:.0f}%（実効キャパ {m['effective_capacity']}）",
                    "year_month": year_month,
                }
            )
        elif rate > 0.95:
            alerts.append(
                {
                    "level": "注意",
                    "type": "個人過負荷",
                    "message": f"{m['name']}: 稼働率 {rate * 100:.0f}%（余裕なし）",
                    "year_month": year_month,
                }
            )
    return alerts


def check_underloaded(conn: sqlite3.Connection, year_month: str) -> list[dict]:
    """#4 個人稼働不足"""
    alerts = []
    for m in utilization_by_member(conn, year_month):
        if m["data_source"] == "none":
            continue
        if m["utilization_rate"] < 0.5:
            alerts.append(
                {
                    "level": "情報",
                    "type": "稼働不足",
                    "message": f"{m['name']}: 稼働率 {m['utilization_rate'] * 100:.0f}%（アサイン余地あり）",
                    "year_month": year_month,
                }
            )
    return alerts


def check_budget_overrun(conn: sqlite3.Connection) -> list[dict]:
    """#7 予算超過ペース / #13 外注費超過"""
    alerts = []
    today = _today()
    fy_start = "2026-04-01"
    elapsed_months = max(
        1,
        (int(today[:4]) - int(fy_start[:4])) * 12
        + int(today[5:7])
        - int(fy_start[5:7]),
    )
    time_rate = elapsed_months / 12.0

    for b in budget_burn(conn):
        if b["budget_total"] == 0:
            continue
        pace = b["burn_rate_total"] / time_rate if time_rate > 0 else 0
        if pace > 1.15:
            alerts.append(
                {
                    "level": "警告",
                    "type": "予算超過ペース",
                    "message": f"{b['project_name']}: 消化ペース {pace:.2f}（消化率 {b['burn_rate_total'] * 100:.0f}% / 経過率 {time_rate * 100:.0f}%）",
                }
            )
        # 外注費のみ超過
        if b["budget_outsource"] > 0:
            outsource_pace = (
                b["burn_rate_outsource"] / time_rate if time_rate > 0 else 0
            )
            if outsource_pace > 1.15 and pace <= 1.15:
                alerts.append(
                    {
                        "level": "注意",
                        "type": "外注費超過",
                        "message": f"{b['project_name']}: 外注費ペース {outsource_pace:.2f}",
                    }
                )
    return alerts


def check_compression(conn: sqlite3.Connection) -> list[dict]:
    """#10 契約遅延圧縮"""
    alerts = []
    for c in compression_ratio(conn):
        ratio = c["ratio"]
        if ratio > 2.0:
            alerts.append(
                {
                    "level": "危険",
                    "type": "契約遅延圧縮",
                    "message": f"{c['project_name']}: 圧縮率 {ratio}x（納期・スコープの再交渉を推奨）",
                }
            )
        elif ratio > 1.5:
            alerts.append(
                {
                    "level": "警告",
                    "type": "契約遅延圧縮",
                    "message": f"{c['project_name']}: 圧縮率 {ratio}x（人員追加 or スコープ縮小が必要）",
                }
            )
        elif ratio > 1.2:
            alerts.append(
                {
                    "level": "注意",
                    "type": "契約遅延圧縮",
                    "message": f"{c['project_name']}: 圧縮率 {ratio}x（アサイン計画見直しを推奨）",
                }
            )
    return alerts


def check_milestone_delay(conn: sqlite3.Connection) -> list[dict]:
    """#6 マイルストーン遅延"""
    today = _today()
    rows = conn.execute(
        """
        SELECT ms.id, ms.name, ms.due_date, p.name AS project_name
        FROM milestones ms
        JOIN projects p ON ms.project_id = p.id
        WHERE ms.due_date < ? AND ms.status != 'completed'
    """,
        (today,),
    ).fetchall()
    return [
        {
            "level": "警告",
            "type": "マイルストーン遅延",
            "message": f"{dict(r)['project_name']}/{dict(r)['name']}: 期限 {dict(r)['due_date']}（超過中）",
        }
        for r in rows
    ]


def check_unassigned_projects(conn: sqlite3.Connection, year_month: str) -> list[dict]:
    """#8 未アサイン案件"""
    rows = conn.execute(
        """
        SELECT p.id, p.name
        FROM projects p
        WHERE p.status IN ('in_progress', 'planned')
          AND p.actual_work_start <= ? || '-31'
          AND p.id NOT IN (
              SELECT DISTINCT project_id FROM assignments_plan WHERE year_month = ?
          )
    """,
        (year_month, year_month),
    ).fetchall()
    return [
        {
            "level": "警告",
            "type": "未アサイン案件",
            "message": f"{dict(r)['name']}: {year_month}にアサインなし",
            "year_month": year_month,
        }
        for r in rows
    ]


def check_unassigned_members(conn: sqlite3.Connection, year_month: str) -> list[dict]:
    """#9 アサインなし人員"""
    rows = conn.execute(
        """
        SELECT m.id, m.name
        FROM members m
        WHERE m.id NOT IN (
            SELECT DISTINCT member_id FROM assignments_plan WHERE year_month = ?
        )
        AND (m.type = 'internal'
             OR (m.contract_start <= ? || '-31' AND m.contract_end >= ? || '-01'))
    """,
        (year_month, year_month, year_month),
    ).fetchall()
    return [
        {
            "level": "情報",
            "type": "アサインなし人員",
            "message": f"{dict(r)['name']}: {year_month}にアサインなし",
            "year_month": year_month,
        }
        for r in rows
    ]


def check_dispatch_expiry(conn: sqlite3.Connection) -> list[dict]:
    """#14 派遣契約期限"""
    today = _today()
    rows = conn.execute(
        """
        SELECT id, name, contract_end
        FROM members
        WHERE type = 'dispatch' AND contract_end IS NOT NULL
          AND julianday(contract_end) - julianday(?) <= 60
          AND contract_end >= ?
    """,
        (today, today),
    ).fetchall()
    return [
        {
            "level": "注意",
            "type": "派遣契約期限",
            "message": f"{dict(r)['name']}: 契約終了 {dict(r)['contract_end']}（更新判断が必要）",
        }
        for r in rows
    ]


def check_future_capacity(
    conn: sqlite3.Connection, months_ahead: int = 3
) -> list[dict]:
    """#1 人員不足予測 / #2 派遣要請 / #11 年度末駆け込み"""
    alerts = []
    today = _today()
    year = int(today[:4])
    month = int(today[5:7])

    for i in range(1, months_ahead + 1):
        m = month + i
        y = year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        ym = f"{y:04d}-{m:02d}"

        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(ap.allocation), 0) AS total_demand,
                COALESCE(SUM(vc.effective_capacity), 0) AS total_capacity
            FROM members m2
            LEFT JOIN (
                SELECT member_id, SUM(allocation) AS allocation
                FROM assignments_plan WHERE year_month = ?
                GROUP BY member_id
            ) ap ON m2.id = ap.member_id
            LEFT JOIN v_effective_capacity vc
                ON m2.id = vc.member_id AND vc.year_month = ?
        """,
            (ym, ym),
        ).fetchone()

        if row is None:
            continue
        demand = row["total_demand"] or 0
        capacity = row["total_capacity"] or 0
        if capacity == 0:
            continue

        rate = demand / capacity
        if rate > 1.0:
            shortage = round(demand - capacity, 1)
            alerts.append(
                {
                    "level": "危険",
                    "type": "人員不足予測",
                    "message": f"{ym}: 稼働率 {rate * 100:.0f}%（不足 {shortage}人月）。派遣要請を推奨",
                }
            )
        elif rate > 0.95:
            alerts.append(
                {
                    "level": "注意",
                    "type": "人員不足予測",
                    "message": f"{ym}: 稼働率 {rate * 100:.0f}%（余裕なし）",
                }
            )
    return alerts


def run_all_alerts(conn: sqlite3.Connection, year_month: str) -> list[dict]:
    """全アラートを実行"""
    all_alerts = []
    all_alerts.extend(check_overloaded(conn, year_month))
    all_alerts.extend(check_underloaded(conn, year_month))
    all_alerts.extend(check_budget_overrun(conn))
    all_alerts.extend(check_compression(conn))
    all_alerts.extend(check_milestone_delay(conn))
    all_alerts.extend(check_unassigned_projects(conn, year_month))
    all_alerts.extend(check_unassigned_members(conn, year_month))
    all_alerts.extend(check_dispatch_expiry(conn))
    all_alerts.extend(check_future_capacity(conn))
    return all_alerts


def main() -> None:
    ym = sys.argv[1] if len(sys.argv) > 1 else _today()[:7]
    conn = connect()
    alerts = run_all_alerts(conn, ym)
    conn.close()

    if not alerts:
        print("アラートなし")
        return

    level_order = {"危険": 0, "警告": 1, "注意": 2, "情報": 3}
    alerts.sort(key=lambda a: level_order.get(a["level"], 9))

    for a in alerts:
        print(f"[{a['level']}] {a['type']}: {a['message']}")


if __name__ == "__main__":
    main()
