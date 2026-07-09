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
COMPANY_LIST_PATH = BASE_DIR / "data" / "processed" / "company_list.csv"
COMPANY_MASTER_PATH = BASE_DIR / "data" / "processed" / "company_master_sample.csv"
COMPANY_OVERVIEW_URL = "https://opendart.fss.or.kr/api/company.json"
TARGET_KEYWORD = "삼성"
SLEEP_SECONDS = 0.3
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
]


def load_api_key():
    """Load DART_API_KEY from the project root .env file."""
    load_dotenv(ENV_PATH)
    return os.getenv("DART_API_KEY")


def read_company_list(csv_path):
    """Read the processed company list CSV."""
    with csv_path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        return list(reader)


def filter_companies_by_name(companies, keyword):
    """Keep companies whose corp_name contains the keyword."""
    matching_companies = []

    for company in companies:
        if keyword in company.get("corp_name", ""):
            matching_companies.append(company)

    return matching_companies


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


def build_master_row(company, overview_data):
    """Build one row for company_master_sample.csv."""
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
    }


def read_company_master(csv_path):
    """Read existing company master rows if the CSV exists."""
    if not csv_path.exists():
        return []

    with csv_path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        return list(reader)


def remove_duplicate_companies(rows):
    """Remove duplicate company master rows by corp_code."""
    rows_by_corp_code = {}

    for row in rows:
        corp_code = row.get("corp_code", "")
        rows_by_corp_code[corp_code] = row

    return list(rows_by_corp_code.values())


def save_company_master(rows, csv_path):
    """Save enriched company master rows to a CSV file."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def append_or_update_company_master(row, csv_path):
    """Append one company master row, or update it if corp_code already exists."""
    existing_rows = read_company_master(csv_path)
    combined_rows = existing_rows + [row]
    unique_rows = remove_duplicate_companies(combined_rows)
    save_company_master(unique_rows, csv_path)


def enrich_single_company(corp_code, corp_name, stock_code):
    """Fetch and save company overview data for one company."""
    api_key = load_api_key()

    if not api_key:
        print("Failure: DART_API_KEY was not found in the project root .env file.")
        return None

    try:
        print(f"Fetching company overview: {corp_name}")
        overview_data = fetch_company_overview(api_key, corp_code)
        company = {
            "corp_code": corp_code,
            "corp_name": corp_name,
            "stock_code": stock_code,
        }
        master_row = build_master_row(company, overview_data)
        append_or_update_company_master(master_row, COMPANY_MASTER_PATH)
        print(f"Success: Saved company overview to {COMPANY_MASTER_PATH}")
        return master_row
    except json.JSONDecodeError as error:
        print(f"Failure: Could not read DART JSON response: {error}")
    except HTTPError as error:
        print(f"Failure: DART API returned an HTTP error: {error.code}")
    except URLError as error:
        print(f"Failure: Could not connect to DART API: {error.reason}")
    except OSError as error:
        print(f"Failure: Could not read or write a file: {error}")

    return None


def enrich_companies(api_key, companies):
    """Fetch overview data and build company master rows."""
    master_rows = []
    total_count = len(companies)

    for index, company in enumerate(companies, start=1):
        corp_name = company.get("corp_name", "")
        corp_code = company.get("corp_code", "")
        print(f"Fetching {index}/{total_count}: {corp_name}")

        overview_data = fetch_company_overview(api_key, corp_code)
        master_row = build_master_row(company, overview_data)
        master_rows.append(master_row)

        time.sleep(SLEEP_SECONDS)

    return master_rows


def main():
    api_key = load_api_key()

    if not api_key:
        print("Failure: DART_API_KEY was not found in the project root .env file.")
        return

    try:
        print(f"Reading company list from {COMPANY_LIST_PATH}...")
        companies = read_company_list(COMPANY_LIST_PATH)
        samsung_companies = filter_companies_by_name(companies, TARGET_KEYWORD)

        if not samsung_companies:
            print(f'Failure: No companies found with corp_name containing "{TARGET_KEYWORD}".')
            return

        print(f"Success: Found {len(samsung_companies)} companies containing {TARGET_KEYWORD}.")

        master_rows = enrich_companies(api_key, samsung_companies)
        save_company_master(master_rows, COMPANY_MASTER_PATH)
        print(f"Success: Saved enriched company master CSV to {COMPANY_MASTER_PATH}")
    except FileNotFoundError:
        print(f"Failure: Company list CSV was not found: {COMPANY_LIST_PATH}")
    except KeyError as error:
        print(f"Failure: Missing expected column in company_list.csv: {error}")
    except json.JSONDecodeError as error:
        print(f"Failure: Could not read DART JSON response: {error}")
    except HTTPError as error:
        print(f"Failure: DART API returned an HTTP error: {error.code}")
    except URLError as error:
        print(f"Failure: Could not connect to DART API: {error.reason}")
    except OSError as error:
        print(f"Failure: Could not read or write a file: {error}")


if __name__ == "__main__":
    main()
