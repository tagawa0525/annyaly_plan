# アサイン整合性チェック (`scripts/validate.py`) 実装計画

## Context

現状、割当計画（`assignments_plan`）にデータを投入しても、個人の月別合計が上限を超えていないか、終了済み案件に割当が残っていないか等を検証する仕組がない。`alerts.py` は「月次運用時の異常検知」に特化しているが、**データ投入時の整合性チェック**は別の関心事であり、専用スクリプトとして切り出す。

## 実装するチェック項目

### アサイン整合性（年月指定）

| # | チェック名                 | レベル | 条件                                                            |
| - | -------------------------- | ------ | --------------------------------------------------------------- |
| 1 | 個人月別アロケーション超過 | 警告   | SUM(allocation) > 1.0 の月がある                                |
| 2 | 派遣の契約期間外アサイン   | 警告   | dispatch メンバーの contract_start〜contract_end 外に割当がある |
| 3 | 終了案件へのアサイン       | 警告   | status が completed/cancelled の案件に割当がある                |
| 4 | 未アサイン案件             | 注意   | status が in_progress/planned の案件に、対象月の割当が0件       |

### データ整合性（年月不要・全体チェック）

| # | チェック名         | レベル | 条件                                                              |
| - | ------------------ | ------ | ----------------------------------------------------------------- |
| 5 | 有給超過           | 警告   | planned_pto_days > working_days                                   |
| 6 | キャパシティ未定義 | 注意   | active メンバーの月に member_capacity レコードがない              |
| 7 | カレンダー未定義   | 警告   | assignments_plan に存在する year_month が monthly_calendar にない |

## アーキテクチャ

`alerts.py` のパターンに準拠:

```text
scripts/validate.py          # メインスクリプト（CLI）
scripts/utils/validation.py  # チェックロジック（テスト対象）
```

- 各チェックは `check_*` 関数（`conn, year_month` → `list[dict]`）
- `run_all_validations()` で集約
- 出力は `[レベル] タイプ: メッセージ` 形式
- 終了コード: 警告以上があれば 1、なければ 0

## TDDサイクル

CLAUDE.md のルールに従い、以下の順序でコミットする:

### コミット1: RED - テスト作成

- `tests/test_validation.py` を作成
- インメモリ SQLite でスキーマ+テストデータを投入するフィクスチャ
- 各チェック関数に対するテストケース（正常系+異常系）
- この時点ではテストは fail/skip

### コミット2: GREEN - ロジック実装

- `scripts/utils/validation.py` にチェックロジックを実装
- テストが全て通る状態にする

### コミット3: GREEN - CLI実装

- `scripts/validate.py` に CLI エントリポイントを実装
- `python scripts/validate.py [YYYY-MM]` で実行可能にする

### コミット4: REFACTOR（必要に応じて）

## 関連ファイル

- `scripts/utils/db.py` - DB接続パターン（再利用）
- `scripts/utils/kpi.py` - `utilization_by_member()` 等は参考にするが、validate は独自クエリ
- `scripts/alerts.py` - 出力パターンの参考
- `scripts/init_db.py` - スキーマ定義（テストフィクスチャで再利用）

## 検証方法

```bash
# テスト実行
python -m unittest discover -s tests -p 'test_validation.py' -v

# シードデータでの動作確認
python scripts/seed_sample.py
python scripts/validate.py 2026-04
# → シードデータの M002 は P001 に 0.8 のみなので警告なし
# → 意図的に不整合データを入れて検出を確認

# 全体チェック（年月なし）
python scripts/validate.py
```
