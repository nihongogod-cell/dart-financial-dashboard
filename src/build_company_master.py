import csv
import json
import os
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
COMPANY_LIST_PATH = BASE_DIR / "data" / "processed" / "company_list.csv"
COMPANY_MASTER_PATH = BASE_DIR / "data" / "processed" / "company_master.csv"
COMPANY_OVERVIEW_URL = "https://opendart.fss.or.kr/api/company.json"
SLEEP_SECONDS = 0.2
OUTPUT_COLUMNS = [
    "corp_code",
    "corp_name",
    "stock_code",
    "ceo_nm",
    "induty_code",
    "adres",
    "hm_url",
    "est_dt",
    "acc_mt",
    "updated_at",
]


def load_api_key():
    """Load DART_API_KEY from the project root .env file."""
    load_dotenv(ENV_PATH)
    return os.getenv("DART_API_KEY")


def read_csv_rows(csv_path):
    """Read CSV rows, or return an empty list if the file does not exist."""
    if not csv_path.exists():
        return []

    with csv_path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        return list(reader)


def build_company_overview_url(api_key, corp_code):
    """Build the DART company overview API URL."""
    query_params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
    }
    query_string = urlencode(query_params)
    return f"{COMPANY_OVERVIEW_URL}?{query_string}"


def fetch_company_overview(api_key, corp_code):
    """Fetch one company overview from DART."""
    request_url = build_company_overview_url(api_key, corp_code)

    with urlopen(request_url) as response:
        response_text = response.read().decode("utf-8")

    return json.loads(response_text)


def get_field(data, field_name):
    """Get a field from a DART response, or return an empty string."""
    value = data.get(field_name, "")

    if value is None:
        return ""

    return value


def get_current_timestamp():
    """Return the current timestamp for updated_at."""
    return datetime.now().isoformat(timespec="seconds")


def build_master_row(company, overview_data):
    """Build one row for company_master.csv."""
    return {
        "corp_code": company.get("corp_code", ""),
        "corp_name": company.get("corp_name", ""),
        "stock_code": company.get("stock_code", ""),
        "ceo_nm": get_field(overview_data, "ceo_nm"),
        "induty_code": get_field(overview_data, "induty_code"),
        "adres": get_field(overview_data, "adres"),
        "hm_url": get_field(overview_data, "hm_url"),
        "est_dt": get_field(overview_data, "est_dt"),
        "acc_mt": get_field(overview_data, "acc_mt"),
        "updated_at": get_current_timestamp(),
    }


def remove_duplicate_companies(rows):
    """Remove duplicate rows by corp_code."""
    rows_by_corp_code = {}

    for row in rows:
        corp_code = row.get("corp_code", "")
        rows_by_corp_code[corp_code] = row

    return list(rows_by_corp_code.values())


def save_company_master(rows, csv_path):
    """Save company master rows to a CSV file."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    unique_rows = remove_duplicate_companies(rows)

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(unique_rows)


def get_existing_corp_codes(rows):
    """Return corp_codes already saved in company_master.csv."""
    corp_codes = set()

    for row in rows:
        corp_code = row.get("corp_code", "")

        if corp_code:
            corp_codes.add(corp_code)

    return corp_codes


def enrich_one_company(api_key, company, index, total_count):
    """Fetch and build one company master row."""
    corp_name = company.get("corp_name", "")
    corp_code = company.get("corp_code", "")
    print(f"Fetching {index}/{total_count}: {corp_name}")

    overview_data = fetch_company_overview(api_key, corp_code)
    return build_master_row(company, overview_data)


def build_company_master():
    """Build the full company master CSV in a resumable way."""
    api_key = load_api_key()

    if not api_key:
        print("Failure: DART_API_KEY was not found in the project root .env file.")
        return

    if not COMPANY_LIST_PATH.exists():
        print(f"Failure: Company list CSV was not found: {COMPANY_LIST_PATH}")
        return

    companies = read_csv_rows(COMPANY_LIST_PATH)
    saved_rows = read_csv_rows(COMPANY_MASTER_PATH)
    saved_corp_codes = get_existing_corp_codes(saved_rows)
    total_count = len(companies)

    print(f"Loaded {total_count} companies from {COMPANY_LIST_PATH}")
    print(f"Already saved {len(saved_corp_codes)} companies in {COMPANY_MASTER_PATH}")

    for index, company in enumerate(companies, start=1):
        corp_code = company.get("corp_code", "")
        corp_name = company.get("corp_name", "")

        if corp_code in saved_corp_codes:
            print(f"Skipping {index}/{total_count}: {corp_name} already exists")
            continue

        try:
            master_row = enrich_one_company(api_key, company, index, total_count)
            saved_rows.append(master_row)
            saved_rows = remove_duplicate_companies(saved_rows)
            saved_corp_codes.add(corp_code)
            save_company_master(saved_rows, COMPANY_MASTER_PATH)
            print(f"Success: Saved {corp_name}")
        except json.JSONDecodeError as error:
            print(f"Failure: Could not read DART JSON response for {corp_name}: {error}")
        except HTTPError as error:
            print(f"Failure: DART API HTTP error for {corp_name}: {error.code}")
        except URLError as error:
            print(f"Failure: Could not connect to DART API for {corp_name}: {error.reason}")
        except OSError as error:
            print(f"Failure: Could not read or write data for {corp_name}: {error}")

        time.sleep(SLEEP_SECONDS)

    save_company_master(saved_rows, COMPANY_MASTER_PATH)
    print(f"Done: Saved company master CSV to {COMPANY_MASTER_PATH}")


if __name__ == "__main__":
    build_company_master()
