import csv
import inspect
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY_ROOT))
ENV_PATH = REPOSITORY_ROOT / ".env"
PROCESSED_DIR = REPOSITORY_ROOT / "data" / "processed"
RAW_DIR = REPOSITORY_ROOT / "data" / "raw"
COMPANY_LIST_PATH = PROCESSED_DIR / "company_list.csv"
COMPANY_MASTER_PATH = PROCESSED_DIR / "company_master.csv"
FINANCIAL_STATEMENT_PATH = PROCESSED_DIR / "financial_statement.csv"
REPORT_CODE = "11011"
FS_DIV = "CFS"
REQUEST_TIMEOUT_SECONDS = 30
PREFERRED_NEW_COMPANIES = ["카카오", "NAVER", "셀트리온", "알테오젠", "툴젠", "기아", "POSCO홀딩스"]


def print_check(check_number, message):
    """Print a timestamped diagnostic check."""
    timestamp = datetime.now().isoformat(timespec="seconds")
    print(f"{timestamp} [{check_number:02d}] {message}", flush=True)


def read_csv_rows(csv_path):
    """Read CSV rows without modifying the file."""
    with csv_path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def require_readable_path(path):
    """Validate that a path exists and is readable."""
    if not path.exists():
        raise FileNotFoundError(f"Required path does not exist: {path}")

    if not os.access(path, os.R_OK):
        raise PermissionError(f"Required path is not readable: {path}")


def get_streamlit_secret_api_key():
    """Read DART_API_KEY from Streamlit secrets when available outside the app."""
    try:
        import streamlit as st

        return st.secrets.get("DART_API_KEY")
    except Exception:
        return None


def resolve_api_key():
    """Resolve the API key without printing the secret value."""
    streamlit_secret_key = get_streamlit_secret_api_key()

    if streamlit_secret_key:
        return streamlit_secret_key, "streamlit_secrets"

    try:
        from dotenv import load_dotenv

        load_dotenv(ENV_PATH)
    except Exception:
        pass

    environment_key = os.getenv("DART_API_KEY")

    if environment_key:
        return environment_key, "environment_variable"

    return None, "missing"


def get_existing_financial_corp_codes(financial_rows):
    """Return corp_codes already stored in financial_statement.csv."""
    return {row.get("corp_code", "") for row in financial_rows if row.get("corp_code", "")}


def find_existing_company(financial_rows):
    """Find one company already stored in financial_statement.csv."""
    for row in financial_rows:
        corp_name = row.get("corp_name", "")
        corp_code = row.get("corp_code", "")

        if corp_name and corp_code:
            return row

    raise RuntimeError("No existing company was found in financial_statement.csv.")


def find_company_by_name(company_rows, company_name):
    """Find a company in company_master.csv by exact corp_name."""
    for row in company_rows:
        if row.get("corp_name", "") == company_name:
            return row

    return None


def find_new_company(company_rows, existing_corp_codes):
    """Find one company that is not already stored in financial_statement.csv."""
    for company_name in PREFERRED_NEW_COMPANIES:
        company = find_company_by_name(company_rows, company_name)

        if company and company.get("corp_code", "") not in existing_corp_codes:
            return company

    for company in company_rows:
        corp_code = company.get("corp_code", "")
        stock_code = company.get("stock_code", "")

        if corp_code and stock_code and corp_code not in existing_corp_codes:
            return company

    raise RuntimeError("No new-company candidate was found in company_master.csv.")


def get_latest_completed_year():
    """Return the latest completed business year."""
    return str(datetime.now().year - 1)


def production_http_has_timeout(fetch_module):
    """Inspect production fetch functions for explicit timeout usage."""
    functions_to_check = [
        fetch_module.download_json,
    ]

    for function in functions_to_check:
        source = inspect.getsource(function)

        if "timeout=" not in source:
            return False

    return True


def fetch_dart_response(api_key, fetch_module, corp_code, business_year):
    """Perform one minimal OpenDART request without saving raw JSON."""
    request_url = fetch_module.build_request_url(api_key, corp_code, business_year, REPORT_CODE, FS_DIV)

    with urlopen(request_url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        http_status = getattr(response, "status", "unknown")
        response_text = response.read().decode("utf-8")

    return http_status, json.loads(response_text)


def check_write_path_visibility():
    """Report write-path visibility without creating or modifying files."""
    processed_parent = FINANCIAL_STATEMENT_PATH.parent
    raw_parent = RAW_DIR.parent
    return {
        "processed_dir_exists": processed_parent.exists(),
        "processed_dir_writable": os.access(processed_parent, os.W_OK),
        "raw_parent_exists": raw_parent.exists(),
        "raw_parent_writable": os.access(raw_parent, os.W_OK),
        "raw_dir_exists": RAW_DIR.exists(),
    }


def main():
    print_check(1, f"Repository root resolved: {REPOSITORY_ROOT}")
    print_check(2, f"Python version: {sys.version.split()[0]}")
    print_check(3, f"Current working directory: {Path.cwd()}")

    for path in [COMPANY_LIST_PATH, COMPANY_MASTER_PATH, FINANCIAL_STATEMENT_PATH]:
        require_readable_path(path)

    print_check(4, "Key project paths exist and are readable")
    print_check(5, f"Processed financial statement CSV exists: {FINANCIAL_STATEMENT_PATH.exists()}")

    company_rows = read_csv_rows(COMPANY_MASTER_PATH)
    financial_rows = read_csv_rows(FINANCIAL_STATEMENT_PATH)
    print_check(6, f"Processed financial statement CSV row count: {len(financial_rows)}")

    existing_company = find_existing_company(financial_rows)
    print_check(
        7,
        f'Existing stored company identified: {existing_company.get("corp_name", "")} '
        f'({existing_company.get("corp_code", "")})',
    )

    api_key, api_key_source = resolve_api_key()
    print_check(8, f"API-key availability: {bool(api_key)}")
    print_check(9, f"API-key source: {api_key_source}")

    if not api_key:
        raise RuntimeError("DART_API_KEY is missing. Configure Streamlit Secrets or an environment variable.")

    from src import extract_accounts
    from src import fetch_financial_statement

    print_check(10, "Production OpenDART fetch modules imported")
    print_check(11, f"Production HTTP call has explicit finite timeout: {production_http_has_timeout(fetch_financial_statement)}")

    existing_corp_codes = get_existing_financial_corp_codes(financial_rows)
    new_company = find_new_company(company_rows, existing_corp_codes)
    new_company_name = new_company.get("corp_name", "")
    new_company_corp_code = fetch_financial_statement.find_corp_code(COMPANY_LIST_PATH, new_company_name)

    if not new_company_corp_code:
        raise RuntimeError(f"Could not find corp_code in company_list.csv for {new_company_name}.")

    business_year = get_latest_completed_year()
    print_check(
        12,
        f"Minimal OpenDART request target selected: {new_company_name}, "
        f"year={business_year}, report={REPORT_CODE}, fs_div={FS_DIV}",
    )

    http_status, response_data = fetch_dart_response(
        api_key,
        fetch_financial_statement,
        new_company_corp_code,
        business_year,
    )
    print_check(13, f"HTTP status code: {http_status}")

    dart_status = response_data.get("status", "")
    dart_message = response_data.get("message", "")
    dart_rows = response_data.get("list", [])
    print_check(14, f"OpenDART status/message: {dart_status} / {dart_message}")
    print_check(15, f"Returned row count: {len(dart_rows)}")

    if http_status != 200:
        raise RuntimeError(f"Unexpected HTTP status: {http_status}")

    if dart_status != "000":
        raise RuntimeError(f"OpenDART returned non-success status: {dart_status} / {dart_message}")

    if not dart_rows:
        raise RuntimeError("OpenDART returned no financial statement rows.")

    extracted_rows = extract_accounts.build_output_rows(
        response_data,
        new_company_name,
        new_company_corp_code,
        REPORT_CODE,
        FS_DIV,
        current_period_only=True,
    )
    print_check(16, f"In-memory extraction result row count: {len(extracted_rows)}")

    if not extracted_rows:
        raise RuntimeError("In-memory extraction found no standardized account rows.")

    write_path_status = check_write_path_visibility()
    print_check(17, f"Repository write-path visibility: {write_path_status}")
    print_check(18, "Overall summary: PASS")
    print("Diagnostic completed successfully.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print_check(18, "Overall summary: FAIL")
        print("Diagnostic failed with traceback:", flush=True)
        traceback.print_exc()
        sys.exit(1)
