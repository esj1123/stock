# NH/NAMUH Import Pipeline

## 역할
`70_Imports/raw/`의 NH/NAMUH Excel 파일을 읽어 정규화 CSV와 SQLite DB를 만들고, Obsidian 대시보드/회사 노트를 AUTO-GENERATED 블록 안에서만 갱신합니다.

## 실행
```powershell
$VenvDir = Join-Path $env:LOCALAPPDATA "06_Stock\.venv"
$env:STOCK_PYTEST_TMPDIR = Join-Path $env:LOCALAPPDATA "06_Stock\pytest_tmp_cases"
python -m venv $VenvDir
cd 70_Imports/scripts
& "$VenvDir\Scripts\python.exe" -m pip install -r requirements.txt
& "$VenvDir\Scripts\python.exe" main.py import --vault-root ../.. --raw-dir ../raw --dry-run
& "$VenvDir\Scripts\python.exe" main.py all --vault-root ../.. --raw-dir ../raw
& "$VenvDir\Scripts\python.exe" main.py qa --vault-root ../..
& "$VenvDir\Scripts\python.exe" -m pytest -p no:cacheprovider --basetemp (Join-Path $env:LOCALAPPDATA "06_Stock\pytest_tmp_pytest")
```

Actual writes to the configured live/final vault root or any child path under it are blocked unless the live-write gate flags are supplied:

```bash
python main.py all --vault-root "C:\Users\KSLV-II\Desktop\Obsidian\ESJ\06_Stock" --raw-dir "C:\Users\KSLV-II\Desktop\Obsidian\ESJ\06_Stock\70_Imports\raw" \
  --live-baseline-updated \
  --live-tests-passed \
  --live-quality-gate-passed \
  --live-dry-run-reviewed \
  --live-expected-changes-reviewed \
  --live-write-confirmation LIVE_06_STOCK_WRITE_REVIEWED
```

Set `STOCK_LIVE_VAULT_ROOT` when the live vault path differs. Dry-runs against the live vault do not require these flags.

## 주요 출력
- `70_Imports/processed/processed_transactions.csv`
- `70_Imports/processed/processed_holdings.csv`
- `70_Imports/processed/processed_cashflows.csv`
- `70_Imports/processed/processed_dividends.csv`
- `70_Imports/processed/portfolio_summary.csv`
- `70_Imports/processed/risk_watchlist.csv`
- `70_Imports/processed/review_queue.csv`
- `70_Imports/processed/qa_exceptions.csv`
- `70_Imports/processed/source_file_index.csv`
- `70_Imports/processed/unclassified_rows.csv`
- `70_Imports/processed/investment.db`
