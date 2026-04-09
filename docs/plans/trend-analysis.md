# 月次トレンド分析 (`scripts/trend.py`) 実装計画

## Context

現状の `analyze.py` は単月スナップショットのみで、稼働率・予算消化・進捗率が月をまたいでどう変化しているかを把握できない。経営報告やリソース計画の判断には「推移」の情報が不可欠。

## 実装する機能

### トレンド対象KPI（3指標）

| # | KPI        | 既存関数                     | 改修要否                                |
| - | ---------- | ---------------------------- | --------------------------------------- |
| 1 | 部署稼働率 | `dept_utilization(conn, ym)` | 不要（ループ呼び出し）                  |
| 2 | 予算消化率 | `budget_burn(conn)`          | **要改修**（year_month パラメータ追加） |
| 3 | 進捗率     | `progress_gap(conn, ym)`     | 不要（ループ呼び出し）                  |

### CLI

```bash
# 直近6ヶ月のトレンド（デフォルト）
python scripts/trend.py

# 範囲指定
python scripts/trend.py 2026-04 2026-09

# CSV出力
python scripts/trend.py 2026-04 2026-09 --csv
```

### 出力イメージ

```text
============================================================
  稼働率トレンド (2026-04 〜 2026-09)
============================================================
月        計画    実績    差分
2026-04   78%     82%     +4%
2026-05   85%     -       -
...

============================================================
  予算消化トレンド (2026-04 〜 2026-09)
============================================================
月        計画累計    実績累計    消化率
2026-04   8,500,000   8,230,000   96.8%
...

============================================================
  進捗トレンド (2026-04 〜 2026-09)
============================================================
案件          04    05    06    07    08    09
P001 A社...   8%   15%   25%   -     -     -
P002 B社...   -     -     -     0%    5%   10%
```

## アーキテクチャ

```text
scripts/trend.py               # CLIエントリーポイント
scripts/utils/trend.py         # トレンド集計ロジック（テスト対象）
scripts/utils/kpi.py           # budget_burn にyear_month対応を追加
```

### kpi.py の改修

`budget_burn` に `year_month` パラメータを追加。既存の呼び出し（`analyze.py`, `alerts.py`）は `year_month=None`（累積）で後方互換を維持。

```python
def budget_burn(conn, project_id=None, year_month=None) -> list[dict]:
    # year_month=None: 従来通り累積
    # year_month指定: その月までの累積
```

### utils/trend.py の関数

```python
def utilization_trend(conn, start_month, end_month) -> list[dict]
    # [{year_month, plan_rate, actual_rate}, ...]

def budget_trend(conn, start_month, end_month) -> list[dict]
    # [{year_month, planned_cumulative, actual_cumulative, burn_rate}, ...]

def progress_trend(conn, start_month, end_month) -> list[dict]
    # [{project_id, project_name, months: {ym: pct, ...}}, ...]
```

## TDDサイクル

### コミット1: RED - テスト作成

- `tests/test_trend.py` を作成
- 各トレンド関数のテスト（複数月にわたるデータの集計）
- `budget_burn` の year_month 対応テスト

### コミット2: GREEN - kpi.py 改修

- `budget_burn` に `year_month` パラメータを追加
- 既存テストがあれば通ることを確認

### コミット3: GREEN - トレンドロジック実装

- `scripts/utils/trend.py` に集計ロジックを実装
- テストが全て通る状態にする

### コミット4: GREEN - CLI実装

- `scripts/trend.py` にCLIとCSV出力を実装

## 関連ファイル

- `scripts/utils/kpi.py` - `budget_burn()` 改修対象、`dept_utilization()` / `progress_gap()` 再利用
- `scripts/analyze.py` - 出力パターンの参考（`tabulate()`, `print_section()`）
- `scripts/utils/db.py` - DB接続
- `scripts/init_db.py` - スキーマ（テストフィクスチャ用）

## 検証方法

```bash
# テスト実行
python -m unittest discover -s tests -p 'test_trend.py' -v

# シードデータでの動作確認
python scripts/seed_sample.py
python scripts/trend.py 2026-04 2026-09

# CSV出力
python scripts/trend.py 2026-04 2026-09 --csv
ls data/export/trend_*.csv
```
