import csv
import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_CSV_PATH = BASE_DIR / "data" / "processed" / "financial_statement.csv"
EXAMPLE_JSON_PATH = BASE_DIR / "data" / "raw" / "samsung_2023_financial_statement.json"
TARGET_ACCOUNTS = [
    "자산총계",
    "부채총계",
    "자본총계",
    "매출액",
    "매출원가",
    "매출총이익",
    "영업이익",
    "당기순이익",
    "영업활동현금흐름",
    "투자활동현금흐름",
    "재무활동현금흐름",
]
AMOUNT_FIELDS = [
    ("thstrm_amount", 0),
    ("frmtrm_amount", 1),
    ("bfefrmtrm_amount", 2),
]
OUTPUT_COLUMNS = [
    "corp_code",
    "corp_name",
    "year",
    "report_code",
    "fs_div",
    "account_nm",
    "amount",
]
DUPLICATE_KEY_COLUMNS = ["corp_code", "year", "report_code", "fs_div", "account_nm"]


def read_json_file(json_path):
    """Read a saved DART financial statement JSON file."""
    with Path(json_path).open("r", encoding="utf-8") as json_file:
        return json.load(json_file)


def convert_amount_to_int(amount_text):
    """Convert an amount string to an integer, or return None if it is invalid."""
    if amount_text is None:
        return None

    cleaned_amount = str(amount_text).replace(",", "").strip()

    if not cleaned_amount:
        return None

    try:
        return int(cleaned_amount)
    except ValueError:
        return None


def is_target_account(account_name):
    """Check whether the account name is one of the target accounts."""
    return account_name in TARGET_ACCOUNTS


def build_output_rows(response_data, corp_name, corp_code, report_code, fs_div):
    """Build generic financial statement rows from the DART JSON response."""
    output_rows = []
    dart_rows = response_data.get("list", [])

    for dart_row in dart_rows:
        account_name = dart_row.get("account_nm", "")

        if not is_target_account(account_name):
            continue

        business_year = int(dart_row.get("bsns_year", ""))

        for amount_field, years_ago in AMOUNT_FIELDS:
            amount = convert_amount_to_int(dart_row.get(amount_field, ""))

            if amount is None:
                continue

            output_rows.append(
                {
                    "corp_code": corp_code,
                    "corp_name": corp_name,
                    "year": business_year - years_ago,
                    "report_code": report_code,
                    "fs_div": fs_div,
                    "account_nm": account_name,
                    "amount": amount,
                }
            )

    return output_rows


def read_existing_rows(csv_path):
    """Read existing processed rows if the CSV already exists."""
    if not csv_path.exists():
        return []

    with csv_path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        return list(reader)


def make_duplicate_key(row):
    """Create the key used to remove duplicate financial statement rows."""
    key_values = []

    for column in DUPLICATE_KEY_COLUMNS:
        key_values.append(str(row.get(column, "")))

    return tuple(key_values)


def remove_duplicate_rows(rows):
    """Remove duplicates while keeping the newest row for each key."""
    rows_by_key = {}

    for row in rows:
        duplicate_key = make_duplicate_key(row)
        rows_by_key[duplicate_key] = row

    return list(rows_by_key.values())


def save_rows(rows, csv_path):
    """Save rows to financial_statement.csv."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def append_and_dedupe_rows(new_rows, csv_path):
    """Append new rows and remove duplicates."""
    existing_rows = read_existing_rows(csv_path)
    combined_rows = existing_rows + new_rows
    unique_rows = remove_duplicate_rows(combined_rows)
    save_rows(unique_rows, csv_path)
    return unique_rows


def extract_accounts(json_path, corp_name, corp_code, report_code, fs_div):
    """Extract selected accounts from a saved DART JSON file."""
    try:
        print(f"Reading JSON file: {json_path}")
        response_data = read_json_file(json_path)

        print("Extracting selected financial statement accounts...")
        new_rows = build_output_rows(response_data, corp_name, corp_code, report_code, fs_div)

        if not new_rows:
            print("Result: No matching account rows were found.")
            return []

        print(f"Success: Extracted {len(new_rows)} rows before duplicate removal.")
        saved_rows = append_and_dedupe_rows(new_rows, OUTPUT_CSV_PATH)
        print(f"Success: Saved {len(saved_rows)} total rows to {OUTPUT_CSV_PATH}")
        return new_rows
    except FileNotFoundError:
        print(f"Failure: JSON file was not found: {json_path}")
    except json.JSONDecodeError as error:
        print(f"Failure: Could not read JSON data: {error}")
    except ValueError as error:
        print(f"Failure: Could not convert business year to an integer: {error}")
    except OSError as error:
        print(f"Failure: Could not read or write a file: {error}")

    return []


if __name__ == "__main__":
    if EXAMPLE_JSON_PATH.exists():
        extract_accounts(
            json_path=EXAMPLE_JSON_PATH,
            corp_name="삼성전자",
            corp_code="00126380",
            report_code="11011",
            fs_div="CFS",
        )
    else:
        print(f"Example JSON file does not exist yet: {EXAMPLE_JSON_PATH}")
