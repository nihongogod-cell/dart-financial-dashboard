import csv
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
COMPANY_MASTER_PATH = BASE_DIR / "data" / "processed" / "company_master.csv"
COMPANY_OVERVIEW_URL = "https://opendart.fss.or.kr/api/company.json"
VALID_CORP_CLS_VALUES = ["Y", "K", "N", "E"]
SLEEP_SECONDS = 0.2


def load_api_key():
    """Load DART_API_KEY from the project root .env file."""
    load_dotenv(ENV_PATH)
    return os.getenv("DART_API_KEY")


def read_company_master(csv_path):
    """Read company_master.csv while preserving values as strings."""
    with csv_path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        return reader.fieldnames or [], list(reader)


def ensure_corp_cls_column(columns, rows):
    """Ensure corp_cls exists after stock_code without changing other values."""
    if "corp_cls" not in columns:
        stock_code_index = columns.index("stock_code")
        columns.insert(stock_code_index + 1, "corp_cls")

    for row in rows:
        if "corp_cls" not in row:
            row["corp_cls"] = ""

    return columns, rows


def save_company_master(columns, rows, csv_path):
    """Save company_master.csv with all existing rows preserved."""
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_company_overview_url(api_key, corp_code):
    """Build the DART company overview API URL."""
    query_params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
    }
    query_string = urlencode(query_params)
    return f"{COMPANY_OVERVIEW_URL}?{query_string}"


def fetch_corp_cls(api_key, corp_code):
    """Fetch only corp_cls from DART company.json."""
    request_url = build_company_overview_url(api_key, corp_code)

    with urlopen(request_url) as response:
        response_text = response.read().decode("utf-8")

    overview_data = json.loads(response_text)
    corp_cls = overview_data.get("corp_cls", "")

    if corp_cls is None:
        return ""

    return str(corp_cls).strip()


def has_existing_corp_cls(row):
    """Return True when corp_cls already has any saved value."""
    return bool(row.get("corp_cls", "").strip())


def count_corp_cls_values(rows):
    """Count known and blank or unknown corp_cls values."""
    counts = {
        "Y": 0,
        "K": 0,
        "N": 0,
        "E": 0,
        "blank_or_unknown": 0,
    }

    for row in rows:
        corp_cls = row.get("corp_cls", "").strip()

        if corp_cls in VALID_CORP_CLS_VALUES:
            counts[corp_cls] += 1
        else:
            counts["blank_or_unknown"] += 1

    return counts


def print_summary(total_rows, updated_rows, skipped_rows, failed_rows, rows):
    """Print a concise enrichment summary."""
    counts = count_corp_cls_values(rows)

    print("\nDone")
    print(f"total rows: {total_rows}")
    print(f"updated rows: {updated_rows}")
    print(f"skipped rows: {skipped_rows}")
    print(f"failed rows: {failed_rows}")
    print(f"count of Y companies: {counts['Y']}")
    print(f"count of K companies: {counts['K']}")
    print(f"count of N companies: {counts['N']}")
    print(f"count of E companies: {counts['E']}")
    print(f"count of blank or unknown values: {counts['blank_or_unknown']}")


def enrich_market_classification():
    """Fill blank corp_cls values in company_master.csv."""
    api_key = load_api_key()

    if not api_key:
        print("Failure: DART_API_KEY was not found in the project root .env file.")
        return

    if not COMPANY_MASTER_PATH.exists():
        print(f"Failure: Company master CSV was not found: {COMPANY_MASTER_PATH}")
        return

    columns, rows = read_company_master(COMPANY_MASTER_PATH)
    columns, rows = ensure_corp_cls_column(columns, rows)
    total_rows = len(rows)
    updated_rows = 0
    skipped_rows = 0
    failed_rows = 0

    for index, row in enumerate(rows, start=1):
        corp_name = row.get("corp_name", "")
        corp_code = row.get("corp_code", "")

        if has_existing_corp_cls(row):
            skipped_rows += 1
            continue

        try:
            corp_cls = fetch_corp_cls(api_key, corp_code)
            row["corp_cls"] = corp_cls
            updated_rows += 1
            save_company_master(columns, rows, COMPANY_MASTER_PATH)
            print(f"[{index}/{total_rows}] {corp_name}: {corp_cls or '(blank)'}")
        except json.JSONDecodeError as error:
            failed_rows += 1
            print(f"[{index}/{total_rows}] {corp_name}: JSON error - {error}")
        except HTTPError as error:
            failed_rows += 1
            print(f"[{index}/{total_rows}] {corp_name}: HTTP error - {error.code}")
        except URLError as error:
            failed_rows += 1
            print(f"[{index}/{total_rows}] {corp_name}: network error - {error.reason}")
        except OSError as error:
            failed_rows += 1
            print(f"[{index}/{total_rows}] {corp_name}: file or network error - {error}")

        time.sleep(SLEEP_SECONDS)

    print_summary(total_rows, updated_rows, skipped_rows, failed_rows, rows)


if __name__ == "__main__":
    enrich_market_classification()
