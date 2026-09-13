import { describe, expect, it, vi } from "vitest";
vi.mock("./db", () => ({ cachedAll: vi.fn() }));
import { balanceSheetStructure, operatingNetworkViews, type BalancePartRow } from "./sector-overview";

function fixture(): BalancePartRow[] {
  const rows = Array.from({length:56}, (_, i) => ({period:"2026-07", item_order:i+1, amount_total:0 as number|null}));
  const put = (id:number, value:number) => { rows[id-1].amount_total=value; };
  put(10,700); put(11,40); put(12,30); put(5,150); put(1,100); put(25,40); put(26,1000);
  put(27,600); put(33,200); put(36,50); put(46,50); put(55,100); put(56,1000);
  return rows;
}
describe("sector balance-sheet structure", () => {
  it("uses net credit and disjoint balance-sheet blocks", () => {
    const data=balanceSheetStructure(fixture());
    expect(data.assets[0].values.amount).toBe(710);
    expect(data.assets.reduce((s,r)=>s+r.values.amount!,0)).toBe(1000);
    expect(data.funding.reduce((s,r)=>s+r.values.amount!,0)).toBe(1000);
  });
  it("keeps missing inputs unknown while preserving the other side", () => {
    const rows=fixture(); rows[11].amount_total=null;
    const data=balanceSheetStructure(rows);
    expect(data.assets.every(r=>r.values.amount===null)).toBe(true);
    expect(data.funding[0].values.amount).toBe(600);
  });
  it("rejects a non-reconciling partition and duplicate rows", () => {
    const rows=fixture(); rows[25].amount_total=1500;
    expect(balanceSheetStructure(rows).assets.every(r=>r.values.amount===null)).toBe(true);
    expect(balanceSheetStructure([...fixture(),fixture()[0]]).funding.every(r=>r.values.amount===null)).toBe(true);
  });
  it("never fills a missing latest-period item from earlier data", () => {
    const rows=fixture().filter(r=>r.item_order!==27);
    rows.push({...fixture()[26],period:"2025-07"});
    expect(balanceSheetStructure(rows).funding.every(r=>r.values.amount===null)).toBe(true);
  });
});

it("indexes network counts only against a complete common month", () => {
  const result=operatingNetworkViews({overseas:[],network:[
    {period:"2024-01",item_order:2,value:5},
    ...[2,5,6].map(item_order=>({period:"2024-02",item_order,value:10})),
    {period:"2024-03",item_order:2,value:null},
    {period:"2024-03",item_order:5,value:12},
  ]});
  expect(result.basePeriod).toBe("2024-02");
  expect(result.history.at(-1)?.value).toBe(120);
  expect(result.history.at(-2)?.value).toBeNull();
  expect(result.overseas.every(row=>Object.values(row.values).every(v=>v===null))).toBe(true);
});
