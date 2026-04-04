# 部署プロジェクト管理システム

15名・25案件・売上目標2億円の部署向けプロジェクト管理ツール。

## 管理軸

- **進捗**: 案件のステータス・マイルストーン・完了率
- **人員充足**: 稼働率・過負荷検出・スキルマッチング
- **予算消化率**: 人件費/外注費/経費の3区分で追跡

## 技術スタック

- **データ**: SQLite（`data/project_mgmt.db`）
- **分析スクリプト**: Python（KPI計算・アラート・インポート）
- **AI分析**: Claude Code（対策提案・What-if分析・レポート文章）

## セットアップ

```bash
pip install -r requirements.txt
python scripts/init_db.py

# 動作確認用のサンプルデータ投入（任意）
python scripts/seed_sample.py
```

## 月次運用

```bash
# 1. TeamSpirit/SAP からCSVインポート
python scripts/import_teamspirit.py YYYY-MM ts_export.csv
python scripts/import_sap.py YYYY-MM sap_export.csv

# 2. 分析・レポート生成
python scripts/analyze.py YYYY-MM
python scripts/report_generator.py YYYY-MM

# 3. Git追跡用CSVエクスポート
python scripts/export_csv.py
```

## 詳細

設計・要件の詳細は [実装計画](docs/plans/project-management-system.md) を参照。
