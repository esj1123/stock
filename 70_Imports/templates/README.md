# Import Templates

## initial_holdings_template.xlsx

`initial_holdings_template.xlsx` is not included in this repository. Spreadsheet files are ignored by default because they commonly contain personal holdings, quantities, cost basis, account labels, or other private investment data.

If you need an initial holdings workbook, create it locally in your private vault and keep it out of Git.

Recommended local path:

```text
70_Imports/raw/initial_holdings_template.xlsx
```

Suggested columns:

| column | purpose |
| --- | --- |
| ticker | Security ticker or code |
| security_name | Security name |
| quantity | Current holding quantity |
| average_cost | Average cost basis |
| currency | Holding currency, such as KRW or USD |
| account_type | Optional local account label |
| as_of_date | Snapshot date for the initial holding |

## Usage

1. Create a local workbook with the columns above.
2. Fill it with your current holdings only in the private vault.
3. Put the file under `70_Imports/raw/`.
4. Run the standard import entrypoint:

```bash
python 70_Imports/scripts/main.py all --vault-root . --raw-dir 70_Imports/raw
```

This method treats the initial balance as a starting snapshot. To avoid duplicates, operate with either:

- initial holdings plus later transaction history, or
- full transaction history from the beginning.

Adding a blank `.xlsx` template to this repository should be handled as a separate reviewed change with an explicit `.gitignore` exception.
