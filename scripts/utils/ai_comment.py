"""レポートAIコメント自動生成ロジック"""


def _assess_level(alerts: list[dict]) -> tuple[str, str]:
    """アラートから総合評価レベルとサマリーを決定"""
    critical = sum(1 for a in alerts if a["level"] == "危険")
    warnings = sum(1 for a in alerts if a["level"] == "警告")
    cautions = sum(1 for a in alerts if a["level"] == "注意")

    if critical > 0:
        level = "要対応"
    elif warnings > 0 or cautions > 0:
        level = "注意"
    else:
        level = "良好"
        return level, "重大な問題なし"

    parts = []
    if critical:
        parts.append(f"危険{critical}件")
    if warnings:
        parts.append(f"警告{warnings}件")
    if cautions:
        parts.append(f"注意{cautions}件")
    summary = "、".join(parts) + "を検出"
    return level, summary


def _utilization_comment(dept_rate: float, members: list[dict]) -> str:
    """稼働状況のコメントを生成"""
    pct = f"{dept_rate * 100:.0f}%"

    if dept_rate >= 0.80 and dept_rate <= 0.95:
        assessment = "適正範囲"
    elif dept_rate > 0.95:
        assessment = "高負荷"
    elif dept_rate >= 0.60:
        assessment = "やや低め"
    else:
        assessment = "低稼働"

    comment = f"部署平均{pct}（{assessment}）"

    # 過負荷メンバーの検出
    overloaded = [
        m for m in members if m.get("utilization_rate", 0) > 0.95
    ]
    if overloaded:
        names = "、".join(m["name"] for m in overloaded[:3])
        comment += f"。{names}が95%超で余裕なし"

    return comment


def _budget_comment(burns: list[dict]) -> str | None:
    """予算状況のコメントを生成"""
    issues = []
    for b in burns:
        # 区分別に超過チェック
        if b.get("burn_rate_outsource", 0) > 1.0:
            issues.append(
                f"{b['project_name']}の外注費消化{b['burn_rate_outsource']:.1f}倍"
            )
        elif b.get("burn_rate_total", 0) > 1.0:
            issues.append(
                f"{b['project_name']}の予算消化{b['burn_rate_total']:.1f}倍"
            )

    if issues:
        return "。".join(issues[:3])
    return "全案件の消化ペースは適正"


def _progress_comment(gaps: list[dict], compressed: list[dict]) -> str | None:
    """進捗状況のコメントを生成"""
    comments = []

    # 遅延案件（gap > 5pt）
    delayed = [g for g in gaps if g.get("gap") and g["gap"] > 5]
    for g in delayed[:3]:
        comment = f"{g['project_name']}が期待比-{g['gap']:.0f}pt遅延"
        # 圧縮率があれば追加
        comp = [c for c in compressed if c["project_name"] == g["project_name"]]
        if comp and comp[0].get("ratio"):
            comment += f"（圧縮率{comp[0]['ratio']}x）"
        comments.append(comment)

    if comments:
        return "。".join(comments)
    return "全案件で進捗は順調"


def generate_ai_comment(
    dept_rate: float,
    members: list[dict],
    burns: list[dict],
    gaps: list[dict],
    compressed: list[dict],
    alerts: list[dict],
) -> str:
    """KPIデータからMarkdown形式の分析コメントを生成"""
    level, summary = _assess_level(alerts)
    util_comment = _utilization_comment(dept_rate, members)
    budget_comment = _budget_comment(burns)
    progress_comment = _progress_comment(gaps, compressed)

    lines = [
        f"**総合評価: {level}** — {summary}",
        "",
        f"- **稼働**: {util_comment}",
        f"- **予算**: {budget_comment}",
        f"- **進捗**: {progress_comment}",
    ]

    return "\n".join(lines)
