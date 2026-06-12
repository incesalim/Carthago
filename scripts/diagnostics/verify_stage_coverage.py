"""Post-backfill verification: print coverage stats for bank_audit_stages."""
import sqlite3, sys
sys.stdout.reconfigure(encoding="utf-8")
conn = sqlite3.connect("data/bddk_data.db")
c = conn.cursor()

print("=== bank_audit_credit_quality coverage by section ===")
for row in c.execute("""
    SELECT section,
           COUNT(DISTINCT bank_ticker || '|' || period || '|' || kind) AS pdfs,
           SUM(CASE WHEN stage1_amount IS NOT NULL THEN 1 ELSE 0 END) AS s1,
           SUM(CASE WHEN stage2_amount IS NOT NULL THEN 1 ELSE 0 END) AS s2,
           SUM(CASE WHEN stage3_amount IS NOT NULL THEN 1 ELSE 0 END) AS s3
    FROM bank_audit_credit_quality
    WHERE period_type='current'
    GROUP BY section ORDER BY pdfs DESC
"""):
    print(f"  {row[0]:<22} pdfs={row[1]:>4}  S1={row[2]:>4} S2={row[3]:>4} S3={row[4]:>4}")

print()
print("=== bank_audit_stages completeness ===")
for row in c.execute("""
    SELECT COUNT(*) AS total,
           SUM(CASE WHEN stage1_amount IS NOT NULL AND stage2_amount IS NOT NULL AND stage3_amount IS NOT NULL THEN 1 ELSE 0 END) AS full_amt,
           SUM(CASE WHEN stage1_amount IS NULL THEN 1 ELSE 0 END) AS miss_s1,
           SUM(CASE WHEN stage2_amount IS NULL THEN 1 ELSE 0 END) AS miss_s2,
           SUM(CASE WHEN stage3_amount IS NULL THEN 1 ELSE 0 END) AS miss_s3,
           SUM(CASE WHEN stage1_ecl IS NULL THEN 1 ELSE 0 END) AS miss_e1,
           SUM(CASE WHEN stage2_ecl IS NULL THEN 1 ELSE 0 END) AS miss_e2,
           SUM(CASE WHEN stage3_ecl IS NULL THEN 1 ELSE 0 END) AS miss_e3
    FROM bank_audit_stages WHERE period_type='current'
"""):
    print(f"  total={row[0]} full_amt={row[1]}  miss S1={row[2]} S2={row[3]} S3={row[4]} | "
          f"miss E1={row[5]} E2={row[6]} E3={row[7]}")

print()
print("=== Per-bank gaps (current period_type) ===")
for row in c.execute("""
    SELECT bank_ticker,
           COUNT(*) AS n,
           SUM(CASE WHEN stage1_amount IS NULL THEN 1 ELSE 0 END) AS miss_s1,
           SUM(CASE WHEN stage2_amount IS NULL THEN 1 ELSE 0 END) AS miss_s2,
           SUM(CASE WHEN stage3_amount IS NULL THEN 1 ELSE 0 END) AS miss_s3
    FROM bank_audit_stages WHERE period_type='current'
    GROUP BY bank_ticker
    HAVING miss_s1 + miss_s2 + miss_s3 > 0
    ORDER BY miss_s1 + miss_s2 + miss_s3 DESC
"""):
    print(f"  {row[0]:<10} n={row[1]:>3} miss_s1={row[2]:>3} miss_s2={row[3]:>3} miss_s3={row[4]:>3}")

print()
print("=== Spot-check: latest period per failing bank ===")
for bank in ('ZIRAATK', 'ISCTR', 'EXIM', 'VAKIFK', 'TFKB', 'AKBNK'):
    row = c.execute("""
        SELECT period, kind, stage1_amount, stage2_amount, stage3_amount,
               stage1_ecl, stage2_ecl, stage3_ecl
        FROM bank_audit_stages
        WHERE bank_ticker=? AND period_type='current'
        ORDER BY period DESC LIMIT 1
    """, (bank,)).fetchone()
    if row:
        p, k, s1, s2, s3, e1, e2, e3 = row
        f = lambda v: f"{v:,.0f}" if v is not None else "-"
        print(f"  {bank:<10} {p} {k:<14} "
              f"amt=[{f(s1):>15} {f(s2):>15} {f(s3):>15}] "
              f"ecl=[{f(e1):>12} {f(e2):>12} {f(e3):>12}]")
