# 전략별 성과(승률/기대값)

> 매도가 거의 없으면 표본이 적어서 의미가 약할 수 있습니다.  
> 그래도 DB를 쌓아두면 나중에 자동으로 통계가 채워집니다.

- 기준: **SELL 1건을 1회 트레이드로 계산**
- 수수료/세금 포함한 실현손익 기준

```dataviewjs
const TRADES_FOLDER = '"30_Trades"';

const num = (x) => (x === null || x === undefined || x === "" ? 0 : Number(x));
const str = (x) => (x === null || x === undefined ? "" : String(x));
const upper = (x) => str(x).toUpperCase();

const sells = dv.pages(TRADES_FOLDER)
  .where(p => p.ticker && p.type && upper(p.type) === "SELL")
  .array();

if (sells.length === 0) {
  dv.paragraph("아직 SELL 거래가 없습니다. (승률/기대값 계산 불가)");
  return;
}

// 티커별 이동평균 원가를 제대로 계산하려면 BUY까지 함께 봐야 하지만,
// 여기서는 간단히 'importer가 넣어준 realized_pnl'이 있을 경우 그걸 우선 사용.
// 없으면 Portfolio 대시보드의 방식(이동평균)을 확장해서 동일하게 계산하도록 개선 가능.
function getPnl(s) {
  if (s.realized_pnl !== null && s.realized_pnl !== undefined) return num(s.realized_pnl);
  return num(s.pnl); // 혹시 pnl 필드가 있으면
}

const byStrat = new Map();

for (const s of sells) {
  const strategy = (s.strategy ? String(s.strategy) : "unspecified");
  const pnl = getPnl(s);

  if (!byStrat.has(strategy)) {
    byStrat.set(strategy, { n:0, wins:0, losses:0, sumWin:0, sumLoss:0, sum:0 });
  }
  const v = byStrat.get(strategy);
  v.n += 1;
  v.sum += pnl;
  if (pnl >= 0) { v.wins += 1; v.sumWin += pnl; }
  else { v.losses += 1; v.sumLoss += pnl; }
}

const rows = Array.from(byStrat.entries()).map(([k,v]) => {
  const winRate = v.n ? v.wins / v.n : 0;
  const avgWin = v.wins ? v.sumWin / v.wins : 0;
  const avgLoss = v.losses ? v.sumLoss / v.losses : 0; // 음수
  const expectancy = winRate * avgWin + (1-winRate) * avgLoss;
  const profitFactor = (Math.abs(v.sumLoss) > 0) ? (v.sumWin / Math.abs(v.sumLoss)) : null;

  return {
    strategy: k,
    n: v.n,
    winRate,
    avgWin,
    avgLoss,
    expectancy,
    profitFactor
  };
}).sort((a,b)=>b.expectancy-a.expectancy);

const fmt = (x) => Number(x).toLocaleString("ko-KR", { maximumFractionDigits: 0 });

dv.table(
  ["전략", "표본(Sell)", "승률", "평균이익", "평균손실", "기대값(1회당)", "Profit Factor"],
  rows.map(r => [
    r.strategy,
    r.n,
    (r.winRate*100).toFixed(1) + "%",
    fmt(r.avgWin),
    fmt(r.avgLoss),
    fmt(r.expectancy),
    (r.profitFactor === null ? "" : r.profitFactor.toFixed(2))
  ])
);
```
