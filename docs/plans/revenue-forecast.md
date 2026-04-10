# 売上予測の精緻化 実装計画

## Context

現状の `revenue_forecast()` は `budget_plan.planned_revenue` を全案件無条件で合算するだけで、契約状態（signed/planned/delayed）の確度を考慮しない。経営報告では「確実に見込める売上」と「リスクを含む売上」を区別する必要がある。

## 実装する機能

### 確度別売上予測（3シナリオ）

| シナリオ | signed | planned | delayed |
| -------- | ------ | ------- | ------- |
| 楽観     | 100%   | 100%    | 80%     |
| 標準     | 100%   | 70%     | 50%     |
| 悲観     | 100%   | 40%     | 20%     |

### 出力イメージ

```text
============================================================
  売上予測 (FY2026)
============================================================
目標: 200,000,000円

  契約状態      案件数  計画売上
  signed          2    27,600,000
  delayed         1     9,000,000
  planned         0             0
  ──────────────────────────────
  合計            3    36,600,000

  シナリオ      予測売上        達成率
  楽観        34,800,000      17.4%
  標準        32,100,000      16.1%
  悲観        29,400,000      14.7%
```

## アーキテクチャ

```text
scripts/utils/kpi.py           # revenue_forecast_weighted() を追加
scripts/forecast.py            # CLIエントリーポイント
```

### kpi.py への追加

```python
def revenue_forecast_weighted(conn, fiscal_year=2026) -> dict:
    # Returns: {
    #   revenue_target, 
    #   by_status: [{contract_status, project_count, planned_revenue}, ...],
    #   scenarios: {optimistic, standard, pessimistic}
    # }
```

既存の `revenue_forecast()` は変更しない（後方互換）。

## TDDサイクル

### コミット1: RED - テスト作成

- `tests/test_forecast.py`
- シナリオ別の重み付け計算テスト
- 契約状態別の集計テスト

### コミット2: GREEN - ロジック実装

- `revenue_forecast_weighted()` を `kpi.py` に追加

### コミット3: GREEN - CLI実装

- `scripts/forecast.py`

## 関連ファイル

- `scripts/utils/kpi.py:199-218` - 既存の `revenue_forecast()` 参考
- `scripts/init_db.py` - `projects.contract_status`, `budget_plan.planned_revenue` スキーマ
- `scripts/seed_sample.py` - テストデータ: P001(signed), P002(delayed), P003(signed)

## 検証方法

```bash
python -m unittest discover -s tests -p 'test_forecast.py' -v
python scripts/seed_sample.py
python scripts/forecast.py
python scripts/forecast.py 2026
```
