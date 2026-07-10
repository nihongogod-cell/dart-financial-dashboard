import json
from pathlib import Path

from extract_accounts import ACCOUNT_MAPPING


BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
COMPANY_NAME = "삼성전자"
YEARS = ["2021", "2022"]
FS_DIVS = ["CFS", "OFS"]
CASH_FLOW_ACCOUNTS = [
    "영업활동현금흐름",
    "투자활동현금흐름",
    "재무활동현금흐름",
]


def build_raw_json_path(company_name, year, fs_div):
    """Build the raw JSON file path for one company, year, and fs_div."""
    file_name = f"{company_name}_{year}_11011_{fs_div}_financial_statement.json"
    return RAW_DIR / file_name


def read_json_file(json_path):
    """Read one saved DART raw JSON file."""
    with json_path.open("r", encoding="utf-8") as json_file:
        return json.load(json_file)


def find_matching_row(rows, standard_account_name):
    """Find the first row that matches the updated account mapping."""
    account_settings = ACCOUNT_MAPPING[standard_account_name]

    for raw_account_name in account_settings["account_names"]:
        for row in rows:
            account_matches = row.get("account_nm", "") == raw_account_name
            section_matches = row.get("sj_nm", "") in account_settings["sj_names"]

            if account_matches and section_matches:
                return row

    return None


def print_mapping_result(year, fs_div, standard_account_name, matched_row):
    """Print whether one standard cash flow account matched."""
    if matched_row is None:
        print(f"{year} {fs_div} {standard_account_name}: no match")
        return

    print(
        f"{year} {fs_div} {standard_account_name}: matched | "
        f'raw_account_nm="{matched_row.get("account_nm", "")}" | '
        f'thstrm_amount={matched_row.get("thstrm_amount", "")}'
    )


def inspect_file(json_path, year, fs_div):
    """Inspect one raw JSON file without modifying any data."""
    if not json_path.exists():
        print(f"Missing raw JSON file: {json_path}")
        return

    response_data = read_json_file(json_path)
    rows = response_data.get("list", [])

    print(f"\nFile: {json_path.name}")
    print(
        f"status={response_data.get('status', '')} | "
        f"message={response_data.get('message', '')} | "
        f"list_rows={len(rows)}"
    )

    for standard_account_name in CASH_FLOW_ACCOUNTS:
        matched_row = find_matching_row(rows, standard_account_name)
        print_mapping_result(year, fs_div, standard_account_name, matched_row)


def main():
    print(f"Checking cash flow mapping for {COMPANY_NAME}")

    for year in YEARS:
        for fs_div in FS_DIVS:
            json_path = build_raw_json_path(COMPANY_NAME, year, fs_div)
            inspect_file(json_path, year, fs_div)


if __name__ == "__main__":
    main()
