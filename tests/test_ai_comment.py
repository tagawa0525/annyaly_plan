"""AIコメント自動生成のテスト"""

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from utils.ai_comment import generate_ai_comment


class TestOverallAssessment(unittest.TestCase):
    """総合評価のテスト"""

    def test_good_when_no_alerts(self):
        """アラートなし → 良好"""
        result = generate_ai_comment(
            dept_rate=0.8,
            members=[],
            burns=[],
            gaps=[],
            compressed=[],
            alerts=[],
        )
        self.assertIn("良好", result)

    def test_caution_when_warnings(self):
        """警告あり → 注意"""
        alerts = [
            {"level": "警告", "type": "予算超過ペース", "message": "P001: 消化ペース 1.2"},
        ]
        result = generate_ai_comment(
            dept_rate=0.8,
            members=[],
            burns=[],
            gaps=[],
            compressed=[],
            alerts=alerts,
        )
        self.assertIn("注意", result)

    def test_caution_when_only_cautions(self):
        """注意のみ → 注意（良好にしない）"""
        alerts = [
            {"level": "注意", "type": "派遣契約期限", "message": "D001: 残60日"},
        ]
        result = generate_ai_comment(
            dept_rate=0.8,
            members=[],
            burns=[],
            gaps=[],
            compressed=[],
            alerts=alerts,
        )
        self.assertIn("注意", result)
        self.assertNotIn("良好", result)

    def test_critical_when_danger(self):
        """危険あり → 要対応"""
        alerts = [
            {"level": "危険", "type": "個人過負荷", "message": "田中太郎: 稼働率 110%"},
        ]
        result = generate_ai_comment(
            dept_rate=0.9,
            members=[],
            burns=[],
            gaps=[],
            compressed=[],
            alerts=alerts,
        )
        self.assertIn("要対応", result)


class TestUtilizationComment(unittest.TestCase):
    """稼働コメントのテスト"""

    def test_normal_utilization(self):
        """適正範囲のコメント"""
        result = generate_ai_comment(
            dept_rate=0.82,
            members=[
                {"name": "田中太郎", "utilization_rate": 0.8, "type": "internal"},
                {"name": "佐藤次郎", "utilization_rate": 0.7, "type": "internal"},
            ],
            burns=[],
            gaps=[],
            compressed=[],
            alerts=[],
        )
        self.assertIn("稼働", result)

    def test_overloaded_member_mentioned(self):
        """過負荷メンバーが言及される"""
        result = generate_ai_comment(
            dept_rate=0.85,
            members=[
                {"name": "田中太郎", "utilization_rate": 0.98, "type": "internal"},
                {"name": "佐藤次郎", "utilization_rate": 0.5, "type": "internal"},
            ],
            burns=[],
            gaps=[],
            compressed=[],
            alerts=[],
        )
        self.assertIn("田中太郎", result)

    def test_low_utilization_mentioned(self):
        """低稼働の部署平均が言及される"""
        result = generate_ai_comment(
            dept_rate=0.45,
            members=[],
            burns=[],
            gaps=[],
            compressed=[],
            alerts=[],
        )
        self.assertIn("稼働", result)


class TestBudgetComment(unittest.TestCase):
    """予算コメントのテスト"""

    def test_overrun_project_mentioned(self):
        """超過ペースの案件が言及される"""
        result = generate_ai_comment(
            dept_rate=0.8,
            members=[],
            burns=[
                {
                    "project_name": "A社システム",
                    "budget_total": 50000000,
                    "actual_total": 30000000,
                    "burn_rate_total": 0.6,
                    "burn_rate_labor": 0.5,
                    "burn_rate_outsource": 1.3,
                    "burn_rate_expense": 0.4,
                },
            ],
            gaps=[],
            compressed=[],
            alerts=[],
        )
        self.assertIn("予算", result)


class TestProgressComment(unittest.TestCase):
    """進捗コメントのテスト"""

    def test_delayed_project_mentioned(self):
        """遅延案件が言及される"""
        result = generate_ai_comment(
            dept_rate=0.8,
            members=[],
            burns=[],
            gaps=[
                {
                    "project_name": "B社システム",
                    "overall_completion_pct": 10,
                    "expected_completion_pct": 25.0,
                    "gap": 15.0,
                    "contract_status": "delayed",
                },
            ],
            compressed=[
                {
                    "project_name": "B社システム",
                    "ratio": 1.8,
                    "delay_note": None,
                },
            ],
            alerts=[],
        )
        self.assertIn("進捗", result)

    def test_no_gaps_ok(self):
        """遅延なし"""
        result = generate_ai_comment(
            dept_rate=0.8,
            members=[],
            burns=[],
            gaps=[],
            compressed=[],
            alerts=[],
        )
        # Should still have the section header or indicate no issues
        self.assertIsInstance(result, str)


class TestMarkdownFormat(unittest.TestCase):
    """Markdown形式のテスト"""

    def test_starts_with_header(self):
        """Markdownヘッダーで始まる"""
        result = generate_ai_comment(
            dept_rate=0.8,
            members=[],
            burns=[],
            gaps=[],
            compressed=[],
            alerts=[],
        )
        self.assertTrue(result.startswith("### ") or result.startswith("**"))

    def test_contains_bold_assessment(self):
        """総合評価が太字"""
        result = generate_ai_comment(
            dept_rate=0.8,
            members=[],
            burns=[],
            gaps=[],
            compressed=[],
            alerts=[],
        )
        self.assertIn("**総合評価", result)


if __name__ == "__main__":
    unittest.main()
