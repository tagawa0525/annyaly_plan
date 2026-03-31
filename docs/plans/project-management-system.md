# 部署プロジェクト管理システム 実装計画

## Context

部署（15名・25案件・売上目標2億円）のプロジェクト管理をゼロから構築する。
管理軸は **進捗・人員充足・予算消化率** の3つ。AIが直接データを読み分析できる形式を採用する。

---

## 要件一覧（全26項目）

### A. 基本要件

1. **プロジェクトの進捗管理**: ステータス・マイルストーン・完了率
2. **人員の充足/過剰判定**: 過負荷・余剰の検出
3. **予算消化率**: 案件ごとの予算と実績、消化ペース

### B. 入力方式・データ取込み

4. **年間計画先行入力**: 12ヶ月分の計画を先に入れ、月次は差分だけ更新
5. **計画と実績の予実管理**: 乖離を自動検出
6. **TeamSpirit → 工数実績**: 正社員の工数CSVインポート（派遣は対象外）
7. **SAP → コスト実績**: 案件別の実績コストCSVインポート
8. **将来的にAPI連携**: まずCSVインポート、将来はAPI

### C. 売上管理

9. **売上は予測値のみ**: 契約不履行の実績がないため、実売上の追跡は不要

### D. 人員管理・キャパシティ

10. **外注・派遣の管理**: 社内/外注/派遣を区別。コスト構造・契約期間・スキル
11. **個人過負荷の検出**: allocation合計が高すぎる人へのアラート
12. **派遣の工数は手入力**: TeamSpirit対象外のため
13. **月別営業日数の考慮**: GW・お盆・年末年始等で月ごとにキャパが異なる
14. **有給取得予定の反映**: 個人ごとの有休予定 → 実質稼働日数を算出
15. **残業時間の考慮**: 平均残業時間 → 実効キャパシティを算出

**実効キャパシティ** = ((営業日 - 有給日) × 8h + 残業h) / (営業日 × 8h)

### E. 予算管理

16. **予算内訳3区分**: 人件費（単価×稼働）/ 外注費 / 経費（設備・旅費・ライセンス）
17. **予算消化ペース監視**: 区分ごとの超過・遅延の早期検出

### F. 案件変動パターン

18. **契約遅延 → 年度末駆け込み**: 予算は同じ、残り期間に圧縮
19. **年度跨ぎ案件**: 今年度分/来年度分の予算按分
20. **突発案件の追加**: 既存リソースへの影響を即座に可視化

### G. アサイン最適化

21. **スキルベースのアサイン提案**: 必要スキルと保有スキルのマッチング
22. **稼働バランスの最適化**: 部署全体のバランスを考慮
23. **制約条件**: PM継続性、スキル適合度、稼働率均等化、派遣契約期間

### H. アラート（先を見通す）

24. **人員不足予測 / 派遣要請**: 何月に何人足りないか
25. **年度末駆け込みリスク**: 遅延案件のQ4集中
26. **完了見込み危険 / 突発インパクト**: 間に合わない案件の検出

---

## 実装方式: ハイブリッド（Python + Claude Code）

| 担当            | 役割                                                              |
| --------------- | ----------------------------------------------------------------- |
| **Python**      | CSVインポート、DB管理、KPI計算、閾値アラート                      |
| **Claude Code** | 分析コメント、対策提案、What-if分析、アサイン最適化、レポート文章 |

---

## データ形式: SQLite

単一ファイル `data/project_mgmt.db` で全データを管理。
Git差分追跡は `data/export/*.csv` への自動エクスポートで対応。

---

## ディレクトリ構造

```text
annyaly_plan/
├── CLAUDE.md
├── README.md
├── data/
│   ├── project_mgmt.db                # SQLite（.gitignore対象）
│   └── export/                        # Git差分追跡用CSV
├── scripts/
│   ├── init_db.py                     # DB初期化
│   ├── analyze.py                     # メイン分析
│   ├── alerts.py                      # アラート検出（14種）
│   ├── optimize.py                    # アサイン最適化
│   ├── import_teamspirit.py           # TeamSpirit CSV取込み
│   ├── import_sap.py                  # SAP CSV取込み
│   ├── export_csv.py                  # DB → CSVエクスポート
│   ├── report_generator.py            # 月次レポート生成
│   └── utils/
│       ├── __init__.py
│       ├── db.py                      # DB接続・共通クエリ
│       └── kpi.py                     # KPI計算
├── reports/
│   └── monthly/
├── .gitignore
└── requirements.txt                   # pandas, jinja2, tabulate
```

---

## データ構造（SQLite 14テーブル）

### テーブル一覧

| テーブル                  | 種別   | 説明                               |
| ------------------------- | ------ | ---------------------------------- |
| `fiscal_year`             | 設定   | 年度設定                           |
| `monthly_calendar`        | 設定   | 月別営業日数                       |
| `members`                 | マスタ | 人員（正社員・派遣・外注）         |
| `member_skills`           | マスタ | 保有スキル                         |
| `member_capacity`         | マスタ | 月別の有給予定・残業時間           |
| `projects`                | マスタ | 案件（契約遅延・年度跨ぎ対応含む） |
| `project_budgets`         | マスタ | 予算内訳（人件費/外注費/経費）     |
| `project_required_skills` | マスタ | 必要スキル                         |
| `milestones`              | マスタ | マイルストーン                     |
| `assignments_plan`        | 計画   | 年間アサイン計画                   |
| `budget_plan`             | 計画   | 年間予算計画（内訳3区分+売上予測） |
| `assignments_actual`      | 実績   | アサイン実績（TeamSpirit/手入力）  |
| `budget_actual`           | 実績   | コスト実績（SAP/手入力）           |
| `progress`                | 実績   | 進捗記録                           |

### DDL

```sql
CREATE TABLE fiscal_year (
    fiscal_year    INTEGER PRIMARY KEY,
    period_start   TEXT NOT NULL,
    period_end     TEXT NOT NULL,
    revenue_target INTEGER NOT NULL,
    headcount      INTEGER NOT NULL
);

CREATE TABLE monthly_calendar (
    year_month   TEXT PRIMARY KEY,     -- '2026-04'
    working_days INTEGER NOT NULL,     -- 22 (GW月は少ない等)
    base_hours   REAL GENERATED ALWAYS AS (working_days * 8.0) STORED
);

CREATE TABLE members (
    id                 TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    type               TEXT NOT NULL CHECK (type IN ('internal', 'outsource', 'dispatch')),
    role               TEXT NOT NULL,
    grade              TEXT NOT NULL CHECK (grade IN ('junior', 'mid', 'senior', 'lead')),
    unit_cost          INTEGER NOT NULL,
    hourly_rate        INTEGER,
    max_capacity       REAL NOT NULL DEFAULT 1.0,
    avg_overtime_hours REAL DEFAULT 0,
    join_date          TEXT,
    contract_start     TEXT,
    contract_end       TEXT,
    note               TEXT
);

CREATE TABLE member_skills (
    member_id TEXT NOT NULL REFERENCES members(id),
    skill     TEXT NOT NULL,
    level     TEXT NOT NULL CHECK (level IN ('junior', 'mid', 'senior')),
    PRIMARY KEY (member_id, skill)
);

CREATE TABLE member_capacity (
    member_id        TEXT NOT NULL REFERENCES members(id),
    year_month       TEXT NOT NULL REFERENCES monthly_calendar(year_month),
    planned_pto_days INTEGER NOT NULL DEFAULT 0,
    overtime_hours   REAL,  -- NULL → members.avg_overtime_hoursを使用
    PRIMARY KEY (member_id, year_month)
);

CREATE TABLE projects (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    client              TEXT NOT NULL,
    status              TEXT NOT NULL CHECK (status IN
                          ('planned','in_progress','on_hold','completed','cancelled')),
    priority            TEXT NOT NULL CHECK (priority IN ('high','medium','low')),
    start_date          TEXT NOT NULL,
    end_date            TEXT NOT NULL,
    pm                  TEXT REFERENCES members(id),
    contract_status     TEXT NOT NULL DEFAULT 'planned'
                          CHECK (contract_status IN ('planned','delayed','signed')),
    original_work_start TEXT NOT NULL,
    actual_work_start   TEXT NOT NULL,
    delay_note          TEXT,
    budget_this_fy      INTEGER,
    budget_next_fy      INTEGER,
    note                TEXT
);

CREATE TABLE project_budgets (
    project_id     TEXT PRIMARY KEY REFERENCES projects(id),
    labor_cost     INTEGER NOT NULL DEFAULT 0,
    outsource_cost INTEGER NOT NULL DEFAULT 0,
    expense        INTEGER NOT NULL DEFAULT 0,
    total          INTEGER GENERATED ALWAYS AS (labor_cost + outsource_cost + expense) STORED
);

CREATE TABLE project_required_skills (
    project_id TEXT NOT NULL REFERENCES projects(id),
    skill      TEXT NOT NULL,
    level      TEXT NOT NULL CHECK (level IN ('junior','mid','senior')),
    need_count INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (project_id, skill)
);

CREATE TABLE milestones (
    id             TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL REFERENCES projects(id),
    name           TEXT NOT NULL,
    due_date       TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'not_started'
                     CHECK (status IN ('not_started','in_progress','completed','delayed')),
    completion_pct INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE assignments_plan (
    member_id       TEXT NOT NULL REFERENCES members(id),
    project_id      TEXT NOT NULL REFERENCES projects(id),
    year_month      TEXT NOT NULL,
    allocation      REAL NOT NULL CHECK (allocation BETWEEN 0.0 AND 1.5),
    role_in_project TEXT NOT NULL,
    PRIMARY KEY (member_id, project_id, year_month)
);

CREATE TABLE assignments_actual (
    member_id       TEXT NOT NULL REFERENCES members(id),
    project_id      TEXT NOT NULL REFERENCES projects(id),
    year_month      TEXT NOT NULL,
    actual_hours    REAL NOT NULL,
    role_in_project TEXT NOT NULL,
    source          TEXT NOT NULL CHECK (source IN ('teamspirit','manual')),
    note            TEXT,
    PRIMARY KEY (member_id, project_id, year_month)
);

CREATE TABLE budget_plan (
    project_id             TEXT NOT NULL REFERENCES projects(id),
    year_month             TEXT NOT NULL,
    planned_labor_cost     INTEGER NOT NULL DEFAULT 0,
    planned_outsource_cost INTEGER NOT NULL DEFAULT 0,
    planned_expense        INTEGER NOT NULL DEFAULT 0,
    planned_revenue        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (project_id, year_month)
);

CREATE TABLE budget_actual (
    project_id             TEXT NOT NULL REFERENCES projects(id),
    year_month             TEXT NOT NULL,
    actual_labor_cost      INTEGER NOT NULL DEFAULT 0,
    actual_outsource_cost  INTEGER NOT NULL DEFAULT 0,
    actual_expense         INTEGER NOT NULL DEFAULT 0,
    source                 TEXT NOT NULL CHECK (source IN ('sap','manual')),
    note                   TEXT,
    PRIMARY KEY (project_id, year_month)
);

CREATE TABLE progress (
    project_id             TEXT NOT NULL REFERENCES projects(id),
    year_month             TEXT NOT NULL,
    overall_completion_pct INTEGER NOT NULL CHECK (overall_completion_pct BETWEEN 0 AND 100),
    note                   TEXT,
    PRIMARY KEY (project_id, year_month)
);
```

### 実効キャパシティVIEW

```sql
CREATE VIEW v_effective_capacity AS
SELECT
    mc.member_id,
    mc.year_month,
    cal.working_days,
    mc.planned_pto_days,
    (cal.working_days - mc.planned_pto_days) * 8.0
      - COALESCE(mc.overtime_hours, m.avg_overtime_hours, 0) AS effective_hours,
    cal.working_days * 8.0 AS base_hours,
    ROUND(
      ((cal.working_days - mc.planned_pto_days) * 8.0
        - COALESCE(mc.overtime_hours, m.avg_overtime_hours, 0))
      / (cal.working_days * 8.0), 3
    ) AS effective_capacity
FROM member_capacity mc
JOIN monthly_calendar cal ON mc.year_month = cal.year_month
JOIN members m ON mc.member_id = m.id;
```

### アサイン実績のallocationもVIEWで算出

```sql
CREATE VIEW v_assignments_actual AS
SELECT
    aa.*,
    cal.base_hours,
    ROUND(aa.actual_hours / cal.base_hours, 3) AS allocation
FROM assignments_actual aa
JOIN monthly_calendar cal ON aa.year_month = cal.year_month;
```

---

## アラートシステム（14種）

| #  | アラート名               | 対象      |
| -- | ------------------------ | --------- |
| 1  | **人員不足予測**         | 将来      |
| 2  | **派遣要請**             | 将来      |
| 3  | **個人過負荷**           | 当月+将来 |
| 4  | **個人稼働不足**         | 当月+将来 |
| 5  | **完了見込み危険**       | 当月      |
| 6  | **マイルストーン遅延**   | 当月      |
| 7  | **予算超過ペース**       | 当月      |
| 8  | **未アサイン案件**       | 将来      |
| 9  | **アサインなし人員**     | 将来      |
| 10 | **契約遅延圧縮**         | 当月+将来 |
| 11 | **年度末駆け込みリスク** | 将来      |
| 12 | **突発案件インパクト**   | 将来      |
| 13 | **外注費超過**           | 当月      |
| 14 | **派遣契約期限**         | 将来      |

### 主要アラートの詳細ロジック

**個人過負荷** (実効キャパシティベース):

```text
個人稼働率 = SUM(allocation) / effective_capacity
95-100% → [注意]  >100% → [危険]
```

**契約遅延圧縮**:

```text
圧縮率 = (end_date - original_work_start) / (end_date - actual_work_start)
1.2-1.5 → [注意]  1.5-2.0 → [警告]  >2.0 → [危険]
```

**年度末駆け込みリスク**:

```text
Q4必要工数 = 通常計画 + 遅延圧縮分
Q4キャパ = SUM(effective_capacity) × 月数
超過 → 必要な派遣人月数を算出
```

**完了見込み危険**:

```text
実質経過率 = (今日 - actual_work_start) / (end_date - actual_work_start)
予測完了率 = 進捗率 / 実質経過率
<0.85 → [警告]  <0.70 → [危険]
```

---

## 主要KPI

1. **稼働率** = SUM(allocation) / effective_capacity（適正: 80-95%）
2. **予算消化率** = 累計実績 / 予算（区分別。ペース: 0.85-1.15が適正）
3. **進捗乖離** = 期待完了率 - 実際完了率（>15pt: 警告、>30pt: 要対策）
4. **売上着地予測** = 月平均計画売上 × 12 vs revenue_target

---

## 実装フェーズ

### Phase 1: 基盤

1. ディレクトリ構造・.gitignore・requirements.txt
2. CLAUDE.md
3. README.md
4. init_db.py（全テーブル作成 + VIEWs）

### Phase 2: データ定義（サンプルデータ投入）

5. 月別カレンダー（12ヶ月分の営業日数）
6. サンプル人員 3名（正社員2+派遣1、スキル・キャパシティ含む）
7. サンプル案件 3件（通常・遅延・年度跨ぎ各1、予算内訳・スキル要件含む）
8. サンプルアサイン計画・予算計画・進捗

### Phase 3: スクリプト開発

9. db.py + kpi.py（DB接続・KPI計算の基盤）
10. import_teamspirit.py + import_sap.py（CSV取込み）
11. export_csv.py（Git追跡用エクスポート）
12. alerts.py（14種のアラート検出）
13. analyze.py（メイン分析、--impact オプション含む）
14. optimize.py（アサイン最適化提案）
15. report_generator.py（月次レポートMarkdown生成）

### Phase 4: 本番データ投入（ユーザーと協力）

16. 15名の人員・スキル・キャパシティ
17. 25件の案件・予算内訳・スキル要件
18. 12ヶ月のアサイン計画・予算計画
19. バリデーション・初回分析・アラート確認

---

## 月次運用フロー

```text
毎月第1営業日（15-20分）:

  [自動取込み]
  1. python scripts/import_teamspirit.py YYYY-MM ts_export.csv
  2. python scripts/import_sap.py YYYY-MM sap_export.csv

  [手入力（10-15分）]
  3. 派遣の工数を追記
  4. 案件ごとの進捗率を更新

  [分析]
  5. python scripts/analyze.py YYYY-MM
  6. python scripts/report_generator.py YYYY-MM
  7. Claude Code が分析・対策提案
  8. python scripts/export_csv.py && git commit & push
```

---

## 検証方法

1. サンプルデータで全スクリプトが正常動作すること
2. 過負荷データで個人過負荷アラートが出ること
3. 遅延案件で圧縮率・年度末リスクが検出されること
4. 有給・残業を変えると実効キャパシティが正しく変化すること
5. TeamSpirit/SAP CSVインポートが正常にUPSERTされること
6. Claude Code がDBを読んで分析・提案できること

---

## Python依存パッケージ

```text
pandas
jinja2
tabulate
```

SQLiteは標準ライブラリ（sqlite3）のため追加不要。
