"""
BDDK API Scraper with Database Integration
Downloads data from BDDK API and stores in SQLite database
"""

import requests
import sqlite3
import json
from datetime import datetime
from pathlib import Path
import sys
import time

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

# Constants
BDDK_API_URL = "https://www.bddk.org.tr/BultenAylik/tr/Home/BasitRaporGetir"
DB_PATH = Path(__file__).parent.parent / "data" / "bddk_data.db"

BANK_TYPES = [
    {"code": "10001", "name": "Sektör"},
    {"code": "10002", "name": "Mevduat"},
    {"code": "10008", "name": "Mevduat-Yerli Özel"},
    {"code": "10009", "name": "Mevduat-Kamu"},
    {"code": "10010", "name": "Mevduat-Yabancı"},
    {"code": "10003", "name": "Katılım"},
    {"code": "10004", "name": "Kalkınma ve Yatırım"},
    {"code": "10005", "name": "Yerli Özel"},
    {"code": "10006", "name": "Kamu"},
    {"code": "10007", "name": "Yabancı"},
]

HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


class BDDKAPIScraper:
    """Scraper for BDDK API with database integration"""

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.conn = None
        self.cursor = None

    def connect_db(self):
        """Connect to database"""
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()

    def close_db(self):
        """Close database connection"""
        if self.conn:
            self.conn.commit()
            self.conn.close()

    def fetch_table_data(self, table_no, year, month, currency, bank_type_code):
        """
        Fetch data from BDDK API

        Returns: dict with JSON response or None if failed
        """
        payload = {
            "tabloNo": str(table_no),
            "yil": str(year),
            "ay": str(month),
            "paraBirimi": currency,
            "taraf[0]": bank_type_code,
        }

        try:
            resp = requests.post(BDDK_API_URL, headers=HEADERS, data=payload, timeout=30)
            resp.raise_for_status()

            data = resp.json()
            if "Json" in data and data["Json"].get("data", {}).get("rows"):
                return data
            else:
                return None

        except Exception as e:
            print(f"Error fetching T{table_no} {year}-{month:02d} {bank_type_code}: {e}")
            return None

    def save_raw_response(self, table_no, year, month, currency, bank_type_code,
                         bank_type_name, response_data):
        """Save raw API response to database"""
        try:
            self.cursor.execute("""
                INSERT OR REPLACE INTO raw_api_responses
                (table_number, year, month, currency, bank_type_code, bank_type_name,
                 response_json, downloaded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (table_no, year, month, currency, bank_type_code, bank_type_name,
                  json.dumps(response_data, ensure_ascii=False)))
        except Exception as e:
            print(f"Error saving raw response: {e}")

    def parse_and_save_table(self, table_no, year, month, currency,
                            bank_type_code, response_data):
        """Parse response and save to appropriate table"""

        j = response_data.get("Json", {})
        col_models = j.get("colModels", [])
        col_names = j.get("colNames", [])
        rows = j.get("data", {}).get("rows", [])

        if not rows:
            return 0

        # Build column mapping
        columns = {}
        for i, (model, name) in enumerate(zip(col_models, col_names)):
            tech_name = model.get("name", "")
            display_name = name if name else tech_name
            columns[tech_name] = i

        saved_rows = 0

        # Route to appropriate table based on table_no
        if table_no == 1:
            saved_rows = self._save_balance_sheet(year, month, currency, bank_type_code,
                                                   columns, rows)
        elif table_no == 2:
            saved_rows = self._save_income_statement(year, month, currency, bank_type_code,
                                                     columns, rows)
        elif table_no in [3, 4, 5, 6, 7]:
            saved_rows = self._save_loans(table_no, year, month, currency, bank_type_code,
                                         columns, rows)
        elif table_no in [9, 10]:
            saved_rows = self._save_deposits(table_no, year, month, currency, bank_type_code,
                                            columns, rows)
        elif table_no in [15, 17]:
            saved_rows = self._save_ratios(table_no, year, month, bank_type_code,
                                          columns, rows)
        else:
            # Save to other_data table
            saved_rows = self._save_other_data(table_no, year, month, currency, bank_type_code,
                                              columns, rows)

        return saved_rows

    def _save_balance_sheet(self, year, month, currency, bank_type_code, columns, rows):
        """Save to balance_sheet table"""
        count = 0
        for row in rows:
            cells = row.get("cell", [])
            if len(cells) < 4:
                continue

            item_order = cells[columns.get("BasitSira", 1)] if "BasitSira" in columns else count + 1
            item_name = cells[columns.get("Ad", 2)] if "Ad" in columns else ""
            font_style = cells[columns.get("BasitFont", 3)] if "BasitFont" in columns else ""
            is_subtotal = font_style == "bold"

            amount_tl = cells[columns.get("Tp", 4)] if "Tp" in columns and len(cells) > columns.get("Tp", 4) else None
            amount_fx = cells[columns.get("Yp", 5)] if "Yp" in columns and len(cells) > columns.get("Yp", 5) else None
            amount_total = cells[columns.get("Toplam", 6)] if "Toplam" in columns and len(cells) > columns.get("Toplam", 6) else None

            try:
                self.cursor.execute("""
                    INSERT OR REPLACE INTO balance_sheet
                    (year, month, currency, bank_type_code, item_order, item_name,
                     is_subtotal, amount_tl, amount_fx, amount_total)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (year, month, currency, bank_type_code, item_order, item_name,
                      is_subtotal, amount_tl, amount_fx, amount_total))
                count += 1
            except Exception as e:
                print(f"Error saving balance sheet row: {e}")

        return count

    def _save_income_statement(self, year, month, currency, bank_type_code, columns, rows):
        """Save to income_statement table"""
        count = 0
        for row in rows:
            cells = row.get("cell", [])
            if len(cells) < 4:
                continue

            item_order = cells[columns.get("BasitSira", 1)] if "BasitSira" in columns else count + 1
            item_name = cells[columns.get("Ad", 2)] if "Ad" in columns else ""
            font_style = cells[columns.get("BasitFont", 3)] if "BasitFont" in columns else ""
            is_subtotal = font_style == "bold"

            amount_tl = cells[columns.get("Tp", 4)] if "Tp" in columns and len(cells) > columns.get("Tp", 4) else None
            amount_fx = cells[columns.get("Yp", 5)] if "Yp" in columns and len(cells) > columns.get("Yp", 5) else None
            amount_total = cells[columns.get("Toplam", 6)] if "Toplam" in columns and len(cells) > columns.get("Toplam", 6) else None

            try:
                self.cursor.execute("""
                    INSERT OR REPLACE INTO income_statement
                    (year, month, currency, bank_type_code, item_order, item_name,
                     is_subtotal, amount_tl, amount_fx, amount_total)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (year, month, currency, bank_type_code, item_order, item_name,
                      is_subtotal, amount_tl, amount_fx, amount_total))
                count += 1
            except Exception as e:
                print(f"Error saving income statement row: {e}")

        return count

    def _save_loans(self, table_no, year, month, currency, bank_type_code, columns, rows):
        """Save to loans table"""
        count = 0
        for row in rows:
            cells = row.get("cell", [])
            if len(cells) < 4:
                continue

            item_order = cells[columns.get("BasitSira", 1)] if "BasitSira" in columns else count + 1
            item_name = cells[columns.get("Ad", 2)] if "Ad" in columns else ""
            font_style = cells[columns.get("BasitFont", 3)] if "BasitFont" in columns else ""
            is_subtotal = font_style == "bold"

            # Extract values based on available columns
            def get_val(col_name):
                if col_name in columns and len(cells) > columns[col_name]:
                    return cells[columns[col_name]]
                return None

            try:
                self.cursor.execute("""
                    INSERT OR REPLACE INTO loans
                    (table_number, year, month, currency, bank_type_code, item_order, item_name,
                     is_subtotal, short_term_tl, short_term_fx, short_term_total,
                     medium_long_tl, medium_long_fx, medium_long_total,
                     total_tl, total_fx, total_amount, npl_amount, non_cash_amount, customer_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (table_no, year, month, currency, bank_type_code, item_order, item_name,
                      is_subtotal,
                      get_val("KisaTp"), get_val("KisaYp"), get_val("KisaToplam"),
                      get_val("OrtaUzunTp"), get_val("OrtaUzunYp"), get_val("OrtaUzunToplam"),
                      get_val("ToplamTp") or get_val("Tp") or get_val("NakdiKrediTp"),
                      get_val("ToplamYp") or get_val("Yp") or get_val("NakdiKrediYp"),
                      get_val("Toplam") or get_val("NakdiKrediToplam") or get_val("ToplamNakdi"),
                      get_val("Takipteki") or get_val("TakipKrediToplam"),
                      get_val("GayriNakdi") or get_val("GayriNakdiKrediToplam"),
                      get_val("NetMusteri")))
                count += 1
            except Exception as e:
                print(f"Error saving loans row: {e}")

        return count

    def _save_deposits(self, table_no, year, month, currency, bank_type_code, columns, rows):
        """Save to deposits table"""
        count = 0
        for row in rows:
            cells = row.get("cell", [])
            if len(cells) < 4:
                continue

            item_order = cells[columns.get("BasitSira", 1)] if "BasitSira" in columns else count + 1
            item_name = cells[columns.get("Ad", 2)] if "Ad" in columns else ""
            font_style = cells[columns.get("BasitFont", 3)] if "BasitFont" in columns else ""
            is_subtotal = font_style == "bold"

            def get_val(col_name):
                if col_name in columns and len(cells) > columns[col_name]:
                    return cells[columns[col_name]]
                return None

            try:
                self.cursor.execute("""
                    INSERT OR REPLACE INTO deposits
                    (table_number, year, month, currency, bank_type_code, item_order, item_name,
                     is_subtotal, bracket_10k, bracket_50k, bracket_250k, bracket_1m, bracket_over_1m,
                     demand, maturity_1m, maturity_1_3m, maturity_3_6m, maturity_6_12m, maturity_over_12m,
                     total_amount)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (table_no, year, month, currency, bank_type_code, item_order, item_name,
                      is_subtotal,
                      get_val("OnBin"), get_val("ElliBin"), get_val("IkiyuzelliBin"),
                      get_val("Milyon"), get_val("Milyonarti"),
                      get_val("Vadesiz"), get_val("BirAyaKadar"), get_val("BirAyUcAy"),
                      get_val("UcAyAltiAy"), get_val("AltiAyBirYil"), get_val("BirYil"),
                      get_val("Toplam")))
                count += 1
            except Exception as e:
                print(f"Error saving deposits row: {e}")

        return count

    def _save_ratios(self, table_no, year, month, bank_type_code, columns, rows):
        """Save to financial_ratios table"""
        count = 0
        for row in rows:
            cells = row.get("cell", [])
            if len(cells) < 4:
                continue

            item_order = cells[columns.get("BasitSira", 1)] if "BasitSira" in columns else count + 1
            item_name = cells[columns.get("Ad", 2)] if "Ad" in columns else ""
            ratio_value = cells[columns.get("Rasyo", 4)] if "Rasyo" in columns and len(cells) > columns.get("Rasyo", 4) else None

            # Categorize ratio
            item_lower = item_name.lower()
            if "takip" in item_lower or "npl" in item_lower:
                category = "asset_quality"
            elif "karlılık" in item_lower or "roa" in item_lower or "roe" in item_lower:
                category = "profitability"
            elif "likidite" in item_lower or "liquid" in item_lower:
                category = "liquidity"
            elif "sermaye" in item_lower or "capital" in item_lower or "car" in item_lower:
                category = "capital"
            else:
                category = "other"

            try:
                self.cursor.execute("""
                    INSERT OR REPLACE INTO financial_ratios
                    (table_number, year, month, bank_type_code, item_order, item_name,
                     ratio_value, ratio_category)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (table_no, year, month, bank_type_code, item_order, item_name,
                      ratio_value, category))
                count += 1
            except Exception as e:
                print(f"Error saving ratio row: {e}")

        return count

    def _save_other_data(self, table_no, year, month, currency, bank_type_code, columns, rows):
        """Save to other_data table for tables with varying structures"""
        count = 0
        for row in rows:
            cells = row.get("cell", [])
            if len(cells) < 4:
                continue

            item_order = cells[columns.get("BasitSira", 1)] if "BasitSira" in columns else count + 1
            item_name = cells[columns.get("Ad", 2)] if "Ad" in columns else ""
            font_style = cells[columns.get("BasitFont", 3)] if "BasitFont" in columns else ""
            is_subtotal = font_style == "bold"

            # Save each column value as a separate row
            for col_name, col_idx in columns.items():
                if col_name in ["BankaAdi", "BasitSira", "Ad", "BasitFont"]:
                    continue
                if col_idx >= len(cells):
                    continue

                value = cells[col_idx]
                if value is None or value == "":
                    continue

                # Try to convert to numeric
                value_numeric = None
                value_text = str(value)
                try:
                    value_numeric = float(value)
                except:
                    pass

                try:
                    self.cursor.execute("""
                        INSERT INTO other_data
                        (table_number, year, month, currency, bank_type_code, item_order,
                         item_name, is_subtotal, column_name, value_numeric, value_text)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (table_no, year, month, currency, bank_type_code, item_order,
                          item_name, is_subtotal, col_name, value_numeric, value_text))
                    count += 1
                except Exception as e:
                    print(f"Error saving other_data row: {e}")

        return count

    def log_download(self, table_no, year, month, currency, bank_type_code,
                    status, rows_downloaded, error_msg=None, started_at=None):
        """Log download attempt"""
        try:
            self.cursor.execute("""
                INSERT INTO download_log
                (table_number, year, month, currency, bank_type_code, status,
                 rows_downloaded, error_message, started_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (table_no, year, month, currency, bank_type_code, status,
                  rows_downloaded, error_msg, started_at))
        except Exception as e:
            print(f"Error logging download: {e}")

    def download_month(self, year, month, tables=None, currencies=None, bank_types=None):
        """Download data for a specific month"""
        if tables is None:
            tables = list(range(1, 18))
        if currencies is None:
            currencies = ["TL"]
        if bank_types is None:
            bank_types = BANK_TYPES

        total_downloaded = 0

        for table_no in tables:
            for currency in currencies:
                for bank_type in bank_types:
                    started_at = datetime.now().isoformat()

                    # Handle Turkish characters in console output
                    bank_name = bank_type['name'].encode('ascii', 'replace').decode('ascii')
                    print(f"Downloading T{table_no:2d} {year}-{month:02d} {currency} {bank_name:25s}...", end=" ")

                    # Fetch data
                    response_data = self.fetch_table_data(
                        table_no, year, month, currency, bank_type["code"]
                    )

                    if response_data:
                        # Save raw response
                        self.save_raw_response(
                            table_no, year, month, currency,
                            bank_type["code"], bank_type["name"], response_data
                        )

                        # Parse and save to appropriate table
                        rows_saved = self.parse_and_save_table(
                            table_no, year, month, currency, bank_type["code"], response_data
                        )

                        # Log success
                        self.log_download(
                            table_no, year, month, currency, bank_type["code"],
                            "success", rows_saved, None, started_at
                        )

                        print(f"OK {rows_saved} rows")
                        total_downloaded += rows_saved
                    else:
                        # Log failure
                        self.log_download(
                            table_no, year, month, currency, bank_type["code"],
                            "failed", 0, "No data returned", started_at
                        )
                        print("ERR No data")

                    # Commit after each table/bank type to avoid losing data
                    self.conn.commit()

                    # Small delay to be nice to the server
                    time.sleep(0.5)

        return total_downloaded

    def download_year(self, year, months=None, **kwargs):
        """Download data for a full year"""
        if months is None:
            months = list(range(1, 13))

        print(f"\n{'='*80}")
        print(f"Downloading data for year {year}")
        print(f"{'='*80}\n")

        total = 0
        for month in months:
            print(f"\n--- Month {year}-{month:02d} ---")
            count = self.download_month(year, month, **kwargs)
            total += count
            print(f"Month total: {count} rows")

        print(f"\nYear {year} total: {total} rows downloaded")
        return total


def main():
    """Main function for testing"""
    scraper = BDDKAPIScraper()

    try:
        scraper.connect_db()

        # Test with one month first
        print("Testing with October 2025, Table 1, Sector only...")
        count = scraper.download_month(
            year=2025,
            month=10,
            tables=[1],
            currencies=["TL"],
            bank_types=[BANK_TYPES[0]]  # Just Sector
        )

        print(f"\nTest complete: {count} rows downloaded")

    finally:
        scraper.close_db()


if __name__ == "__main__":
    main()
