# レポートAIコメント自動生成 実装計画

## Context

`report_generator.py` にはセクション7「AIコメント」のプレースホルダー（`<!-- Claude Code が分析結果に基づき記入 -->`）があるが未実装。レポート生成時点で全KPIが算出済みなので、これらを統合した分析コメントをルールベースで自動生成する。

## 実装する機能

### 生成するコメントの構成

1. **総合評価**（良好/注意/要対応）- アラート数に基づく
2. **稼働状況** - 部署平均と個人のリスク
3. **予算状況** - 消化ペースの健全性
4. **進捗状況** - 遅延案件の有無
5. **推奨アクション** - 上記から導かれる具体的な対応

### 出力イメージ

```markdown
### AIコメント

**総合評価: 注意** — 警告2件、注意1件を検出

- **稼働**: 部署平均78%（適正範囲）。田中太郎が95%超で余裕なし
- **予算**: P001の外注費消化ペースが1.2倍。Q3以降の抑制が必要
- **進捗**: B社会計システムが期待比-8pt遅延。圧縮率1.5xで人員追加を検討
- **推奨**: ①田中太郎のP002アサインを佐藤次郎に一部移管 ②B社の納期・スコープ再交渉
```

## アーキテクチャ

```text
scripts/utils/ai_comment.py     # コメント生成ロジック（テスト対象）
scripts/report_generator.py     # プレースホルダー置換を追加（既存改修）
```

### ai_comment.py

```python
def generate_ai_comment(
    dept_rate: float,
    members: list[dict],
    burns: list[dict],
    gaps: list[dict],
    compressed: list[dict],
    alerts: list[dict],
) -> str:
    """KPIデータからMarkdown形式の分析コメントを生成"""
```

### report_generator.py の改修

`_generate_report_impl()` 内で、プレースホルダーを `generate_ai_comment()` の戻り値で置換。

## TDDサイクル

### コミット1: RED - テスト作成
- `tests/test_ai_comment.py`
- 正常データでの総合評価テスト
- アラートなし/あり時のコメント内容テスト
- 各セクション（稼働/予算/進捗）の生成テスト

### コミット2: GREEN - ロジック実装
- `scripts/utils/ai_comment.py` にコメント生成ロジック

### コミット3: GREEN - report_generator.py 改修
- プレースホルダーを生成コメントで置換

## 関連ファイル

- `scripts/report_generator.py:164-168` - AI_COMMENTプレースホルダー位置
- `scripts/utils/kpi.py` - 全KPI関数（`dept_utilization`, `budget_burn`, `progress_gap` 等）
- `scripts/alerts.py:292-304` - `run_all_alerts()` のアラート構造

## 検証方法

```bash
python -m unittest discover -s tests -p 'test_ai_comment.py' -v
python scripts/init_db.py && python scripts/seed_sample.py
python scripts/report_generator.py 2026-04
cat reports/monthly/2026-04_monthly_report.md
```
