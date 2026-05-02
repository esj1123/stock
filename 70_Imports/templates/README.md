# Templates (Import 보조)

## initial_holdings_template.xlsx

과거 거래내역을 전부 가져오기 어렵거나(기간 제한/번거로움),
이미 보유 중인 종목을 “시작점”으로 잡고 싶을 때 사용합니다.

### 사용 흐름(요약)
1) `initial_holdings_template.xlsx`를 열고, 현재 보유 종목/수량/평단을 채웁니다.
2) 저장한 파일을 `70_Imports/raw/`에 넣습니다.
3) Import 실행:

```bash
python 70_Imports/scripts/namoo_excel_import.py --create-companies
```

> 주의: 이 방식은 “초기 잔고를 한 번에 매수한 것처럼” 넣는 방식입니다.
> 나중에 과거 거래내역을 다시 Import하면 중복될 수 있으니,
> **(A) 초기잔고+이후 거래내역** 또는 **(B) 과거부터 전체 거래내역** 중 하나로 운영하는 것을 권장합니다.
