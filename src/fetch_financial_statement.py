import csv
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
COMPANY_LIST_PATH = BASE_DIR / "data" / "processed" / "company_list.csv"
FINANCIAL_STATEMENT_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
ASSET_TOTAL_ACCOUNT_NAME = "자산총계"
ASSET_TOTAL_FIELDS = [
    "bsns_year",
    "account_nm",
    "fs_nm",
    "sj_nm",
    "thstrm_amount",
    "frmtrm_amount",
    "bfefrmtrm_amount",
]
REPORT_CODE_NAMES = {
    "11011": "annual",
    "11012": "half-year",
    "11013": "Q1",
    "11014": "Q3",
}
FS_DIV_NAMES = {
    "CFS": "consolidated",
    "OFS": "separate",
}


def load_api_key():
    """Load DART_API_KEY from the project root .env file."""
    load_dotenv(ENV_PATH)
    return os.getenv("DART_API_KEY")


def find_corp_code(company_list_path, company_name):
    """Find a company's corp_code in company_list.csv."""
    with company_list_path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)

        for row in reader:
            if row["corp_name"] == company_name:
                return row["corp_code"]

    return None


def build_request_url(api_key, corp_code, bsns_year, report_code, fs_div):
    """Build the DART financial statement API URL."""
    query_params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": report_code,
        "fs_div": fs_div,
    }
    query_string = urlencode(query_params)
    return f"{FINANCIAL_STATEMENT_URL}?{query_string}"


def build_raw_json_path(company_name, bsns_year):
    """Build the path for the raw financial statement JSON file."""
    file_name = f"{company_name}_{bsns_year}_financial_statement.json"
    return BASE_DIR / "data" / "raw" / file_name


def build_assets_csv_path(company_name):
    """Build the path for the processed asset total CSV file."""
    file_name = f"{company_name}_assets.csv"
    return BASE_DIR / "data" / "processed" / file_name


def download_json(request_url, save_path):
    """Download raw JSON from DART and save it to a file."""
    save_path.parent.mkdir(parents=True, exist_ok=True)

    with urlopen(request_url) as response:
        json_data = response.read()

    save_path.write_bytes(json_data)


def load_json_file(json_path):
    """Load a saved JSON file."""
    with json_path.open("r", encoding="utf-8") as json_file:
        return json.load(json_file)


def find_asset_total_rows(response_data):
    """Find rows where account_nm contains 자산총계."""
    rows = response_data.get("list", [])
    matching_rows = []

    for row in rows:
        account_name = row.get("account_nm", "")

        if ASSET_TOTAL_ACCOUNT_NAME in account_name:
            matching_rows.append(row)

    return matching_rows


def find_exact_asset_total_row(response_data):
    """Find the row where account_nm is exactly 자산총계."""
    rows = response_data.get("list", [])

    for row in rows:
        if row.get("account_nm", "") == ASSET_TOTAL_ACCOUNT_NAME:
            return row

    return None


def print_asset_total_rows(rows):
    """Print the asset total rows in a readable format."""
    if not rows:
        print("Result: No rows containing 자산총계 were found in the API response.")
        return

    print(f"Result: Found {len(rows)} rows containing 자산총계.")

    for row_number, row in enumerate(rows, start=1):
        print(f"\nAsset total row {row_number}:")

        for field_name in ASSET_TOTAL_FIELDS:
            print(f"{field_name}: {row.get(field_name, '')}")


def convert_amount_to_int(amount_text):
    """Convert an amount string like '1,234' to an integer."""
    cleaned_amount = amount_text.replace(",", "").strip()
    return int(cleaned_amount)


def build_asset_rows(asset_total_row, corp_name, corp_code):
    """Build CSV rows for current, previous, and two-years-ago assets."""
    business_year = int(asset_total_row["bsns_year"])
    amount_fields = [
        ("thstrm_amount", business_year),
        ("frmtrm_amount", business_year - 1),
        ("bfefrmtrm_amount", business_year - 2),
    ]
    asset_rows = []

    for amount_field, year in amount_fields:
        asset_rows.append(
            {
                "year": year,
                "corp_name": corp_name,
                "corp_code": corp_code,
                "account_nm": asset_total_row["account_nm"],
                "amount": convert_amount_to_int(asset_total_row[amount_field]),
            }
        )

    return asset_rows


def save_asset_rows(asset_rows, csv_path):
    """Save asset rows to a processed CSV file."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    field_names = ["year", "corp_name", "corp_code", "account_nm", "amount"]

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=field_names)
        writer.writeheader()
        writer.writerows(asset_rows)


def print_saved_asset_rows(asset_rows):
    """Print rows saved to the processed assets CSV."""
    print("Saved rows:")

    for row in asset_rows:
        print(
            f"year={row['year']}, "
            f"corp_name={row['corp_name']}, "
            f"corp_code={row['corp_code']}, "
            f"account_nm={row['account_nm']}, "
            f"amount={row['amount']}"
        )


def fetch_financial_statement(company_name, bsns_year, report_code, fs_div):
    """Fetch, inspect, and process one company's financial statement."""
    api_key = load_api_key()

    if not api_key:
        print("Failure: DART_API_KEY was not found in the project root .env file.")
        return

    try:
        print(f"Reading company list from {COMPANY_LIST_PATH}...")
        corp_code = find_corp_code(COMPANY_LIST_PATH, company_name)

        if not corp_code:
            print(f'Failure: Could not find corp_name "{company_name}" in company_list.csv.')
            return

        print(f"Success: Found {company_name} corp_code: {corp_code}")

        report_name = REPORT_CODE_NAMES.get(report_code, report_code)
        fs_div_name = FS_DIV_NAMES.get(fs_div, fs_div)
        print(f"Downloading {company_name} {bsns_year} {fs_div_name} {report_name} financial statement JSON...")
        request_url = build_request_url(api_key, corp_code, bsns_year, report_code, fs_div)
        raw_json_path = build_raw_json_path(company_name, bsns_year)
        download_json(request_url, raw_json_path)
        print(f"Success: Saved raw JSON response to {raw_json_path}")

        print("Inspecting saved JSON response for asset total data...")
        response_data = load_json_file(raw_json_path)
        asset_total_rows = find_asset_total_rows(response_data)
        print_asset_total_rows(asset_total_rows)

        print("Creating processed asset total CSV...")
        asset_total_row = find_exact_asset_total_row(response_data)

        if not asset_total_row:
            print('Failure: Could not find an account_nm exactly matching "자산총계".')
            return

        asset_rows = build_asset_rows(asset_total_row, company_name, corp_code)
        assets_csv_path = build_assets_csv_path(company_name)
        save_asset_rows(asset_rows, assets_csv_path)
        print(f"Success: Saved asset totals to {assets_csv_path}")
        print_saved_asset_rows(asset_rows)
    except FileNotFoundError:
        print(f"Failure: Company list CSV was not found: {COMPANY_LIST_PATH}")
    except KeyError as error:
        print(f"Failure: Missing expected column in company_list.csv: {error}")
    except ValueError as error:
        print(f"Failure: Could not convert an amount or year to an integer: {error}")
    except json.JSONDecodeError as error:
        print(f"Failure: Could not read JSON response: {error}")
    except HTTPError as error:
        print(f"Failure: DART API returned an HTTP error: {error.code}")
    except URLError as error:
        print(f"Failure: Could not connect to DART API: {error.reason}")
    except OSError as error:
        print(f"Failure: Could not read or write a file: {error}")


def main():
    print("Enter financial statement request settings.")
    print("report_code: 11011=annual, 11012=half-year, 11013=Q1, 11014=Q3")
    print("fs_div: CFS=consolidated, OFS=separate")

    company_name = input("company_name: ").strip()
    bsns_year = input("bsns_year: ").strip()
    report_code = input("report_code: ").strip()
    fs_div = input("fs_div: ").strip()

    if not company_name or not bsns_year or not report_code or not fs_div:
        print("Failure: company_name, bsns_year, report_code, and fs_div are all required.")
        return

    fetch_financial_statement(
        company_name=company_name,
        bsns_year=bsns_year,
        report_code=report_code,
        fs_div=fs_div,
    )


if __name__ == "__main__":
    main()
