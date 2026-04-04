"""アサイン最適化提案"""

import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

from utils.db import connect
from utils.kpi import utilization_by_member


def optimize(year_month: str) -> None:
    conn = connect()

    # 1. スキルギャップ分析
    print(f"\n=== スキルギャップ分析 ({year_month}) ===")
    gaps = conn.execute(
        """
        SELECT
            prs.project_id, p.name AS project_name,
            prs.skill, prs.level AS required_level, prs.need_count,
            COUNT(DISTINCT CASE
                WHEN ms.level >= prs.level
                     AND ap.member_id IS NOT NULL
                THEN ms.member_id
            END) AS assigned_count
        FROM project_required_skills prs
        JOIN projects p ON prs.project_id = p.id
        LEFT JOIN assignments_plan ap
            ON ap.project_id = prs.project_id AND ap.year_month = ?
        LEFT JOIN member_skills ms
            ON ap.member_id = ms.member_id AND ms.skill = prs.skill
        WHERE p.status IN ('in_progress', 'planned')
          AND p.actual_work_start <= ? || '-31'
        GROUP BY prs.project_id, prs.skill
        HAVING assigned_count < prs.need_count
    """,
        (year_month, year_month),
    ).fetchall()

    if gaps:
        for g in gaps:
            d = dict(g)
            shortage = d["need_count"] - d["assigned_count"]
            # 候補者を探す
            candidates = conn.execute(
                """
                SELECT ms.member_id, m.name, ms.level,
                    COALESCE(
                        (SELECT SUM(allocation) FROM assignments_plan
                         WHERE member_id = ms.member_id AND year_month = ?),
                        0
                    ) AS current_alloc
                FROM member_skills ms
                JOIN members m ON ms.member_id = m.id
                WHERE ms.skill = ? AND ms.level >= ?
                  AND ms.member_id NOT IN (
                      SELECT member_id FROM assignments_plan
                      WHERE project_id = ? AND year_month = ?
                  )
                ORDER BY current_alloc ASC
            """,
                (
                    year_month,
                    d["skill"],
                    d["required_level"],
                    d["project_id"],
                    year_month,
                ),
            ).fetchall()

            print(
                f"\n  {d['project_name']}: {d['skill']}({d['required_level']}) "
                f"不足 {shortage}名"
            )
            if candidates:
                for c in candidates:
                    cd = dict(c)
                    print(
                        f"    候補: {cd['name']} ({cd['level']}) "
                        f"現稼働率 {cd['current_alloc'] * 100:.0f}%"
                    )
            else:
                print("    候補なし（外部リソースの検討を推奨）")
    else:
        print("  スキルギャップなし")

    # 2. 稼働バランスの確認と再配置提案
    print(f"\n=== 稼働バランス ({year_month}) ===")
    members = utilization_by_member(conn, year_month)
    overloaded = [m for m in members if m["utilization_rate"] > 0.95]
    underloaded = [m for m in members if 0 < m["utilization_rate"] < 0.5]

    if overloaded and underloaded:
        print("  再配置提案:")
        for over in overloaded:
            for under in underloaded:
                print(
                    f"    {over['name']}({over['utilization_rate'] * 100:.0f}%) → "
                    f"{under['name']}({under['utilization_rate'] * 100:.0f}%) に一部移管を検討"
                )
    elif overloaded:
        print("  過負荷メンバーあり、余剰メンバーなし → 外部リソースが必要")
    elif underloaded:
        print("  余剰メンバーあり:")
        for u in underloaded:
            print(
                f"    {u['name']}: {u['utilization_rate'] * 100:.0f}%（アサイン余地あり）"
            )
    else:
        print("  バランス良好")

    conn.close()


def main() -> None:
    ym = (
        sys.argv[1]
        if len(sys.argv) > 1
        else __import__("datetime").date.today().strftime("%Y-%m")
    )
    optimize(ym)


if __name__ == "__main__":
    main()
