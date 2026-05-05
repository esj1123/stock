# Review Holdings Dedupe

Use this prompt when overseas holdings appear to be double-counted across comprehensive `holdings` files and `overseas_balance` files.

## Scope
- Check `70_Imports/processed/processed_holdings.csv`.
- Check `70_Imports/processed/portfolio_summary.csv`.
- Check `70_Imports/processed/risk_watchlist.csv`.
- Check `10_Dashboard/Import_Review.md`.
- Focus on duplicated overseas positions such as the same ticker/name, market, currency, quantity, and near-equal evaluation or purchase amount.

## Safety Rules
- Do not modify the live Google Drive source Vault directly.
- Do not modify, move, or delete files in `70_Imports/raw/`.
- Do not infer current holdings from `transaction_history` balance columns.
- Do not write investment thesis, sell criteria, buy/sell recommendations, or investment opinions.
- Do not add broker API trading, automatic order placement, order password storage, tokens, or credentials.
- Preserve user-written Markdown outside AUTO-GENERATED blocks.
- Mask account numbers, resident IDs, phone numbers, API tokens, passwords, and other sensitive candidates in any report.

## Commands
```bash
cd 70_Imports/scripts
python main.py all --vault-root ../.. --raw-dir ../raw
pytest tests -p no:cacheprovider
```

## Review Checklist
- Confirm AEHR/CRDO-like duplicates appear once in `processed_holdings.csv`.
- Confirm `overseas_balance` is retained when it matches a duplicate generic holdings row.
- Confirm `portfolio_summary.csv` includes `holding_dedupe_*` metrics.
- Confirm total value, total cost, unrealized PnL, PnL percent, and leveraged ETF weight are calculated after dedupe.
- Confirm `risk_watchlist.csv` does not repeat the same duplicated overseas position.
- Confirm `Import_Review.md` shows the holding dedupe summary inside AUTO-GENERATED markers.
- Confirm raw file mtime/size is unchanged after import.
