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


def build_raw_json_path(company_name, bsns_year, report_code, fs_div):
    """Build the path for the raw financial statement JSON file."""
    file_name = f"{company_name}_{bsns_year}_{report_code}_{fs_div}_financial_statement.json"
    return BASE_DIR / "data" / "raw" / file_name


def download_json(request_url, save_path):
    """Download raw JSON from DART and save it to a file."""
    save_path.parent.mkdir(parents=True, exist_ok=True)

    with urlopen(request_url) as response:
        json_data = response.read()

    save_path.write_bytes(json_data)


def has_financial_statement_data(raw_json_path):
    """Check whether a saved DART response contains financial statement rows."""
    with raw_json_path.open("r", encoding="utf-8") as json_file:
        response_data = json.load(json_file)

    return bool(response_data.get("list", []))


def fetch_financial_statement(company_name, bsns_year, report_code, fs_div):
    """Fetch one company's financial statement and save the raw JSON."""
    api_key = load_api_key()

    if not api_key:
        print("Failure: DART_API_KEY was not found in the project root .env file.")
        return None, None, None

    try:
        print(f"Reading company list from {COMPANY_LIST_PATH}...")
        corp_code = find_corp_code(COMPANY_LIST_PATH, company_name)

        if not corp_code:
            print(f'Failure: Could not find corp_name "{company_name}" in company_list.csv.')
            return None, None, None

        print(f"Success: Found {company_name} corp_code: {corp_code}")

        report_name = REPORT_CODE_NAMES.get(report_code, report_code)
        fs_div_name = FS_DIV_NAMES.get(fs_div, fs_div)
        print(f"Downloading {company_name} {bsns_year} {fs_div_name} {report_name} financial statement JSON...")
        request_url = build_request_url(api_key, corp_code, bsns_year, report_code, fs_div)
        raw_json_path = build_raw_json_path(company_name, bsns_year, report_code, fs_div)
        download_json(request_url, raw_json_path)

        if not has_financial_statement_data(raw_json_path):
            print(f"Result: No financial statement data found for {company_name} {bsns_year}.")
            return None, company_name, corp_code

        print(f"Success: Saved raw JSON response to {raw_json_path}")
        return raw_json_path, company_name, corp_code
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

    return None, None, None


def fetch_multiple_years(company_name, years, report_code, fs_div):
    """Fetch financial statements for multiple business years."""
    successful_results = []

    for year in years:
        print(f"Starting fetch for business year {year}...")
        raw_json_path, fetched_company_name, corp_code = fetch_financial_statement(
            company_name=company_name,
            bsns_year=str(year),
            report_code=report_code,
            fs_div=fs_div,
        )

        if raw_json_path:
            successful_results.append(
                {
                    "raw_json_path": raw_json_path,
                    "bsns_year": str(year),
                    "corp_name": fetched_company_name,
                    "corp_code": corp_code,
                }
            )
        else:
            print(f"Skipping business year {year}: no saved financial statement data.")

    print(f"Success: Fetched {len(successful_results)} of {len(years)} requested years.")
    return successful_results


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
