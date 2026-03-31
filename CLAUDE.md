# CLAUDE.md - 部署プロジェクト管理システム

## リポジトリの目的

2026年度の部署年次計画管理。15名、25案件、売上目標2億円。
SQLite + Python + Claude Code のハイブリッド方式。

## データ構造

- `data/project_mgmt.db`: SQLiteデータベース（本体）
- `data/export/*.csv`: Git差分追跡用のCSVエクスポート

### 主要テーブル

| テーブル             | 説明                                                  |
| -------------------- | ----------------------------------------------------- |
| `members`            | 人員マスタ（type: internal/outsource/dispatch）       |
| `member_skills`      | 保有スキル（skill + level）                           |
| `member_capacity`    | 月別の有給予定・残業時間                              |
| `projects`           | 案件マスタ（contract_status: planned/delayed/signed） |
| `project_budgets`    | 予算内訳（labor_cost/outsource_cost/expense）         |
| `assignments_plan`   | 年間アサイン計画                                      |
| `assignments_actual` | アサイン実績（source: teamspirit/manual）             |
| `budget_plan`        | 年間予算計画                                          |
| `budget_actual`      | コスト実績（source: sap/manual）                      |
| `progress`           | 進捗記録                                              |
| `monthly_calendar`   | 月別営業日数                                          |

### VIEW

- `v_effective_capacity`: 実効キャパシティ（営業日・有給・残業を考慮）
- `v_assignments_actual`: アサイン実績 + allocation自動算出

### ID命名規則

- 人員: M001〜（正社員）, D001〜（派遣）, O001〜（外注）
- 案件: P001〜
- マイルストーン: P001-MS01〜

## よく使う操作

```bash
# DB初期化
python scripts/init_db.py

# データ取込み
python scripts/import_teamspirit.py YYYY-MM file.csv
python scripts/import_sap.py YYYY-MM file.csv

# 分析
python scripts/analyze.py YYYY-MM
python scripts/analyze.py --impact P099  # 突発案件の影響分析

# アラート確認
python scripts/alerts.py YYYY-MM

# アサイン最適化
python scripts/optimize.py YYYY-MM

# レポート生成
python scripts/report_generator.py YYYY-MM

# CSVエクスポート（Git追跡用）
python scripts/export_csv.py
```

## 分析の観点

1. **稼働率**: 実効キャパシティベースで80-95%が適正。v_effective_capacityを使用
2. **予算消化ペース**: 区分別（人件費/外注費/経費）に監視。1.15超で警告
3. **契約遅延の圧縮率**: (end_date - original_work_start) / (end_date - actual_work_start)
4. **年度末駆け込み**: Q4（1-3月）への作業集中を検出。遅延案件の圧縮分を加算
5. **完了見込み**: actual_work_startを基準に実質経過率を算出

## 既存システム連携

- **TeamSpirit**: 正社員の工数実績（派遣は対象外）
- **SAP**: 予算・コスト実績（人件費/外注費/経費）
- 売上は予測値のみ管理（実績追跡不要）

## データ更新ルール

- マスタデータの変更はPRで行い、レビュー必須
- 月次の実績取込みはTeamSpirit/SAP CSVインポートで自動化
- 派遣の工数と案件進捗のみ手入力
- CSVエクスポートはコミット前に必ず実行
