# FX Conversion Rules

## Scope

These rules govern KRW conversion for non-KRW broker rows in the baseline import pipeline.

The pipeline must not apply a current or live FX rate to a historical transaction, dividend, fee, tax, realized PnL, or valuation row.

## Provenance Priority

Use the first available source in this order:

1. Broker-provided KRW amount.
2. Broker raw FX rate on the row.
3. Local archived `fx_rates.csv`.
4. API-cached or archived FX rate already stored locally.
5. `fx_missing`.

Live API responses are not ledger evidence. If an external API is used, its result must first be cached or archived with an effective date, provider, use case, status, and source note. The pipeline may then use the cached row on a later run.

## Historical Matching

FX rates must match the row event date exactly.

For income rows, the event date is `trade_date`. For realized PnL requirements, the event date is the underlying buy or sell transaction date. A rate from today must not be used for a past row unless the row event date is today and the rate has already been archived locally.

## Official KRW Amounts

Official KRW totals may include only rows with provenance:

- KRW native rows.
- Non-KRW rows with a broker KRW amount.
- Non-KRW rows with a broker raw FX rate.
- Non-KRW rows with a same-date local or API-cached FX rate.

Rows with `amount_review_status=fx_missing` must preserve native amounts and remain excluded from official KRW totals.

## Requirements Output

When a non-KRW row needs an FX rate and no permitted same-date source exists, the pipeline writes `70_Imports/processed/fx_rate_requirements.csv`.

The requirements file is a work queue, not a rate source. Adding a requirement row does not make any KRW total official.

## USD Income And Realized PnL

USD dividend income can be KRW-converted when same-date provenance exists.

USD realized PnL remains limited: the pipeline may produce historical FX requirements for the underlying buy/sell rows, but it must not officialize KRW realized PnL unless all required KRW proceeds, cost basis, fee, and tax values have provenance.
