# ユーザーマニュアル - 部署プロジェクト管理システム

2026年度の部署年次計画を管理するシステムです。15名・25案件・売上目標2億円の部署運営に必要な稼働率・予算消化・進捗を一元管理します。

## 目次

1. [セットアップ](#1-セットアップ)
2. [月次運用フロー](#2-月次運用フロー)
3. [コマンドリファレンス](#3-コマンドリファレンス)
4. [データの見方](#4-データの見方)
5. [データ入力・変更](#5-データ入力変更)
6. [CSVフォーマット仕様](#6-csvフォーマット仕様)
7. [トラブルシューティング](#7-トラブルシューティング)

---

## 1. セットアップ

### 初回セットアップ

```bash
pip install -r requirements.txt   # pandas, jinja2
python scripts/init_db.py          # DBスキーマ作成
python scripts/seed_sample.py      # サンプルデータ投入（任意）
```

`data/project_mgmt.db` が生成されます（`.gitignore` 対象）。

### ディレクトリ構成

```text
annyaly_plan/
├── data/
│   ├── project_mgmt.db      # SQLiteデータベース本体
│   └── export/               # Git差分追跡用CSVエクスポート
├── scripts/
│   ├── init_db.py            # DB初期化
│   ├── seed_sample.py        # サンプルデータ投入
│   ├── import_teamspirit.py  # TeamSpirit工数CSV取込
│   ├── import_sap.py         # SAPコストCSV取込
│   ├── analyze.py            # 分析・レポート表示
│   ├── alerts.py             # アラート検出
│   ├── optimize.py           # アサイン最適化提案
│   ├── report_generator.py   # 月次レポートMarkdown生成
│   ├── export_csv.py         # DB→CSVエクスポート
│   └── utils/
│       ├── db.py             # DB接続
│       └── kpi.py            # KPI計算ロジック
└── reports/monthly/          # 月次レポート出力先
```

---

## 2. 月次運用フロー

毎月第1営業日に実施する標準手順です。

### ステップ1: 実績データの取込

```bash
# TeamSpirit: 正社員の工数実績（派遣は対象外）
python scripts/import_teamspirit.py 2026-05 ts_export_202605.csv

# SAP: コスト実績
python scripts/import_sap.py 2026-05 sap_export_202605.csv
```

### ステップ2: 手入力データの更新

SQLiteクライアント（DB Browser for SQLite等）で以下を入力します。

```sql
-- 派遣メンバーの工数実績（TeamSpirit対象外のため手入力）
INSERT INTO assignments_actual
  (member_id, project_id, year_month, actual_hours, role_in_project, source, note)
VALUES ('D001', 'P001', '2026-05', 150, 'SE', 'manual', NULL)
ON CONFLICT(member_id, project_id, year_month) DO UPDATE SET
  actual_hours = excluded.actual_hours;

-- 案件の進捗率
INSERT INTO progress (project_id, year_month, overall_completion_pct, note)
VALUES ('P001', '2026-05', 15, '要件定義完了目前')
ON CONFLICT(project_id, year_month) DO UPDATE SET
  overall_completion_pct = excluded.overall_completion_pct,
  note = excluded.note;
```

### ステップ3: 分析の実行

```bash
python scripts/analyze.py 2026-05    # 月次分析
python scripts/alerts.py 2026-05      # アラート確認
python scripts/report_generator.py 2026-05  # レポート生成
```

### ステップ4: CSVエクスポートとGitコミット

```bash
python scripts/export_csv.py
git add data/export/*.csv
git commit -m "chore: monthly export for 2026-05"
```

---

## 3. コマンドリファレンス

### analyze.py - 月次分析

```bash
python scripts/analyze.py [YYYY-MM]
python scripts/analyze.py --impact PROJECT_ID
```

`YYYY-MM` を省略すると今月が対象になります。

#### 通常モード

以下の6セクションを表示します。

| セクション   | 内容                                                     |
| ------------ | -------------------------------------------------------- |
| 部署サマリ   | 部署全体の稼働率・アクティブ案件数・アラート数           |
| 個人別稼働率 | メンバーごとの割当・実効キャパ・稼働率・状態             |
| 予算消化状況 | 案件ごとの予算・実績・消化率（人件費/外注費/経費の内訳） |
| 進捗状況     | 案件ごとの実績完了率・期待完了率・乖離                   |
| 契約遅延案件 | 遅延案件の当初/実際開始日・圧縮率                        |
| アラート     | 全アラート（優先度順）                                   |

出力例:

```text
============================================================
  部署サマリ (2026-04)
============================================================
  部署稼働率: 63%
  アクティブ案件: 3件（うち遅延: 1件）
  アラート: 2件

============================================================
  個人別稼働率
============================================================
氏名      種別      割当計  実効キャパ  稼働率  状態  データ
--------  --------  ------  ---------  ------  ----  ------
佐藤次郎  internal  0.80    1.011      79%     適正  actual
田中太郎  internal  0.50    1.068      47%     余剰  actual
```

#### 影響分析モード (`--impact`)

指定した案件のアサイン計画をもとに、各メンバーの稼働率への影響をシミュレーションします。

```bash
python scripts/analyze.py --impact P003
```

稼働率が95%を超えるメンバーだけがリストアップされます。溢れる人がいなければ「溢れる人はいません」と表示されます。

---

### alerts.py - アラート検出

```bash
python scripts/alerts.py [YYYY-MM]
```

9種類のチェックを実行し、検出されたアラートを優先度順に表示します。

| チェック           | 優先度         | 検出条件                       |
| ------------------ | -------------- | ------------------------------ |
| 個人過負荷         | 危険/注意      | 稼働率 >100% / >95%            |
| 稼働不足           | 情報           | 稼働率 <50%                    |
| 予算超過ペース     | 警告           | 消化ペース >1.15               |
| 外注費超過         | 注意           | 外注費のみペース >1.15         |
| 契約遅延圧縮       | 危険/警告/注意 | 圧縮率 >2.0 / >1.5 / >1.2      |
| マイルストーン遅延 | 警告           | 期限超過 & 未完了              |
| 未アサイン案件     | 警告           | 開始月にアサイン計画なし       |
| アサインなし人員   | 情報           | 当月にアサインなし             |
| 派遣契約期限       | 注意           | 契約終了まで60日以内           |
| 人員不足予測       | 危険/注意      | 将来3ヶ月で稼働率 >100% / >95% |

出力例:

```text
[危険] 個人過負荷: 田中太郎: 稼働率 120%（実効キャパ 1.068）
[警告] 契約遅延圧縮: B社会計システム導入: 圧縮率 1.5x（人員追加 or スコープ縮小が必要）
[注意] 派遣契約期限: 鈴木花子: 契約終了 2027-03-31（更新判断が必要）
```

アラートがなければ「アラートなし」と表示されます。

---

### optimize.py - アサイン最適化提案

```bash
python scripts/optimize.py [YYYY-MM]
```

2つの分析を行います。

**スキルギャップ分析**: 案件が求めるスキル・レベルに対し、実際にアサインされている人員のスキルが不足している箇所を検出します。不足がある場合は候補者（そのスキルを持ち他案件にアサイン中のメンバー）を提案します。候補者がいない場合は外部リソースの検討を推奨します。

**稼働バランス**: 過負荷メンバー（>95%）と余剰メンバー（<50%）を検出し、再配置の提案を表示します。

---

### report_generator.py - 月次レポート生成

```bash
python scripts/report_generator.py [YYYY-MM]
```

`reports/monthly/YYYY-MM_monthly_report.md` にMarkdownレポートを生成します。内容は `analyze.py` と同等ですが、ファイルとして保存されるため共有に適しています。

レポートの構成:

1. エグゼクティブサマリ（稼働率・累計売上予測・アラート数）
2. 人員稼働状況
3. 予算消化状況
4. 進捗状況
5. 契約遅延案件
6. アラート一覧
7. AI分析コメント（プレースホルダ）

---

### import_teamspirit.py - TeamSpirit工数CSVインポート

```bash
python scripts/import_teamspirit.py YYYY-MM file.csv
```

正社員の工数実績を `assignments_actual` テーブルに取り込みます。同じ（member_id, project_id, year_month）の組み合わせが既に存在する場合は上書きされます。CSV内の年月カラムが引数の年月と一致しない場合はエラーになります。

---

### import_sap.py - SAPコストCSVインポート

```bash
python scripts/import_sap.py YYYY-MM file.csv
```

コスト実績を `budget_actual` テーブルに取り込みます。同じ（project_id, year_month）の組み合わせが既に存在する場合は上書きされます。

---

### export_csv.py - CSVエクスポート

```bash
python scripts/export_csv.py
```

全14テーブルを `data/export/` にCSVファイルとして出力します。SQLiteファイルはバイナリでGit差分が見えないため、CSVで変更を追跡します。

---

### init_db.py - DB初期化

```bash
python scripts/init_db.py
```

`data/project_mgmt.db` を新規作成し、全テーブル・VIEWを生成します。既存のDBがある場合は `CREATE TABLE IF NOT EXISTS` により安全に実行できます。

---

### seed_sample.py - サンプルデータ投入

```bash
python scripts/seed_sample.py
```

デモ用のサンプルデータ（メンバー3名・案件3件・12ヶ月分の計画・4月分の実績）を投入します。再実行時は既存データを全て削除してから投入するため、本番データがある場合は実行しないでください。

---

## 4. データの見方

### 稼働率

稼働率は **実効キャパシティ** をベースに計算します。

```text
実効キャパシティ = ((営業日 - 有給日) x 8h + 残業時間) / (営業日 x 8h)
稼働率 = 割当合計 / 実効キャパシティ
```

例: 4月（営業日22日）、有給1日、平均残業20hの場合

```text
実効キャパシティ = ((22 - 1) x 8 + 20) / (22 x 8)
                = 188 / 176
                = 1.068
```

実績データがある月は `assignments_actual` の時間から割当率を逆算します。実績がない月は `assignments_plan` の計画値を使います。

| 稼働率  | 状態 | 意味                             |
| ------- | ---- | -------------------------------- |
| >100%   | 危険 | 実効キャパを超過。人員追加が必要 |
| 95-100% | 注意 | 余裕がない。変動で危険に転ぶ     |
| 50-95%  | 適正 | 理想的な稼働                     |
| <50%    | 余剰 | アサイン余地あり                 |

### 予算消化率

予算は人件費・外注費・経費の3区分で管理します。

```text
消化率 = 累計実績 / 予算総額
消化ペース = 消化率 / 経過率（経過月数 / 12）
```

消化ペースが1.15を超えると警告になります。

### 進捗乖離

```text
期待完了率 = (月末日 - actual_work_start) / (end_date - actual_work_start) x 100
乖離 = 期待完了率 - 実績完了率
```

契約遅延案件は `actual_work_start`（実際の開始日）を基準にするため、遅延による期間圧縮が反映されます。

| 乖離     | 状態   |
| -------- | ------ |
| 15pt以下 | 順調   |
| 15-30pt  | 警告   |
| 30pt超   | 要対策 |

### 契約遅延の圧縮率

```text
圧縮率 = (end_date - original_work_start) / (end_date - actual_work_start)
```

例: 12ヶ月の工期が4ヶ月遅延した場合、残り8ヶ月で12ヶ月分の作業を行う必要があり、圧縮率は1.5xになります。

| 圧縮率  | アラート                             |
| ------- | ------------------------------------ |
| 1.0-1.2 | なし                                 |
| 1.2-1.5 | 注意: アサイン計画見直しを推奨       |
| 1.5-2.0 | 警告: 人員追加 or スコープ縮小が必要 |
| >2.0    | 危険: 納期・スコープの再交渉を推奨   |

---

## 5. データ入力・変更

### ID命名規則

| 種類           | プレフィックス | 例                        |
| -------------- | -------------- | ------------------------- |
| 正社員         | M              | M001, M002, ...           |
| 派遣           | D              | D001, D002, ...           |
| 外注           | O              | O001, O002, ...           |
| 案件           | P              | P001, P002, ...           |
| マイルストーン | 案件ID-MS      | P001-MS01, P001-MS02, ... |

### 新規メンバーの追加

```sql
-- メンバー登録
INSERT INTO members
  (id, name, type, role, grade, unit_cost, hourly_rate,
   max_capacity, avg_overtime_hours, join_date, contract_start, contract_end, note)
VALUES
  ('M003', '山田太郎', 'internal', 'SE', 'junior', 450000, NULL,
   1.0, 0, '2026-06-01', NULL, NULL, NULL);

-- スキル登録
INSERT INTO member_skills VALUES ('M003', 'Java', 'junior');
INSERT INTO member_skills VALUES ('M003', 'SQL', 'junior');

-- 12ヶ月分のキャパシティ登録
INSERT INTO member_capacity (member_id, year_month, planned_pto_days, overtime_hours)
SELECT 'M003', year_month, 1, NULL FROM monthly_calendar;
```

`overtime_hours` を NULL にすると `members.avg_overtime_hours` がフォールバックとして使われます。

### 新規案件の追加

```sql
-- 案件登録
INSERT INTO projects
  (id, name, client, status, priority, start_date, end_date, pm,
   contract_status, original_work_start, actual_work_start, delay_note,
   budget_this_fy, budget_next_fy, note)
VALUES
  ('P004', '新規案件', 'X株式会社', 'planned', 'high',
   '2026-07-01', '2027-03-31', 'M001',
   'planned', '2026-07-01', '2026-07-01', NULL,
   5000000, NULL, NULL);

-- 予算内訳
INSERT INTO project_budgets (project_id, labor_cost, outsource_cost, expense)
VALUES ('P004', 3000000, 1500000, 500000);

-- 必要スキル
INSERT INTO project_required_skills VALUES ('P004', 'Java', 'mid', 2);
INSERT INTO project_required_skills VALUES ('P004', 'SQL', 'junior', 1);
```

`project_budgets.total` は `labor_cost + outsource_cost + expense` から自動計算されます（GENERATED ALWAYS AS）。

### 案件のステータス変更

```sql
-- 案件開始
UPDATE projects SET status = 'in_progress' WHERE id = 'P004';

-- 契約遅延が発生
UPDATE projects SET
  contract_status = 'delayed',
  actual_work_start = '2026-10-01',
  delay_note = '先方の予算確保が遅延'
WHERE id = 'P004';

-- 案件完了
UPDATE projects SET status = 'completed' WHERE id = 'P001';
```

### マイルストーンの更新

```sql
UPDATE milestones SET
  status = 'in_progress',
  completion_pct = 50
WHERE id = 'P001-MS01';
```

### 月別営業日数の変更

```sql
UPDATE monthly_calendar SET working_days = 19 WHERE year_month = '2026-05';
```

`base_hours`（= working_days x 8.0）は自動計算されます。

---

## 6. CSVフォーマット仕様

### TeamSpirit CSV

ファイルエンコーディング: UTF-8

```csv
社員番号,社員名,プロジェクトコード,年月,実績時間,役割
M001,田中太郎,P001,2026-04,88,PM
M002,佐藤次郎,P001,2026-04,140,SE
M002,佐藤次郎,P002,2026-04,30,SE
```

| カラム             | 説明                         | 制約                   |
| ------------------ | ---------------------------- | ---------------------- |
| 社員番号           | members.id に対応            | 存在するIDであること   |
| 社員名             | 参照用（DBには格納されない） | -                      |
| プロジェクトコード | projects.id に対応           | 存在するIDであること   |
| 年月               | YYYY-MM形式                  | コマンド引数と一致必須 |
| 実績時間           | 小数点可                     | 0以上                  |
| 役割               | PM, SE 等                    | -                      |

### SAP CSV

ファイルエンコーディング: UTF-8

```csv
プロジェクトコード,年月,人件費,外注費,経費
P001,2026-04,800000,280000,150000
P002,2026-04,0,0,0
```

| カラム             | 説明               | 制約                   |
| ------------------ | ------------------ | ---------------------- |
| プロジェクトコード | projects.id に対応 | 存在するIDであること   |
| 年月               | YYYY-MM形式        | コマンド引数と一致必須 |
| 人件費             | 円（整数）         | 0以上                  |
| 外注費             | 円（整数）         | 0以上                  |
| 経費               | 円（整数）         | 0以上                  |

---

## 7. トラブルシューティング

### CSVインポート時に年月不一致エラー

```text
エラー: CSV内の年月 '2026-05' が引数 '2026-04' と不一致
```

CSV内の「年月」カラムの値がコマンド引数と一致しません。CSVの内容を確認し、正しい年月を引数に指定してください。

### DB接続エラー

```text
FileNotFoundError: data/project_mgmt.db
```

`python scripts/init_db.py` でDBを初期化してください。

### 外部キー制約エラー

```text
FOREIGN KEY constraint failed
```

存在しないメンバーID・案件IDを参照しています。先にマスタデータを登録してから実績データを投入してください。

```sql
-- 登録済みのIDを確認
SELECT id, name FROM members;
SELECT id, name FROM projects;
```

### 稼働率が0%と表示される

`member_capacity` に対象月のデータがない場合、実効キャパシティが計算できず稼働率が正しく出ません。メンバーの12ヶ月分のキャパシティが登録されているか確認してください。

```sql
SELECT member_id, year_month FROM member_capacity
WHERE member_id = 'M001' ORDER BY year_month;
```

### DBを壊してしまった場合

CSVエクスポートがGitに残っていれば、DBを再初期化してデータを手動で復元できます。

```bash
rm data/project_mgmt.db
python scripts/init_db.py
# data/export/*.csv を参照しながらデータを再投入
```

### モジュールが見つからないエラー

```text
ModuleNotFoundError: No module named 'pandas'
```

```bash
pip install -r requirements.txt
```
