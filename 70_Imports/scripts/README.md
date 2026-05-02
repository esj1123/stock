# NH/NAMUH Import Pipeline

## 역할
`70_Imports/raw/`의 NH/NAMUH Excel 파일을 읽어 정규화 CSV와 SQLite DB를 만들고, Obsidian 대시보드/회사 노트를 AUTO-GENERATED 블록 안에서만 갱신합니다.

## 실행
```bash
cd 70_Imports/scripts
pip install -r requirements.txt
python main.py import --vault-root ../.. --raw-dir ../raw --dry-run
python main.py all --vault-root ../.. --raw-dir ../raw
python main.py qa --vault-root ../..
pytest
```

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
