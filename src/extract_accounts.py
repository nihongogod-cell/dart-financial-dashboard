import csv
import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_CSV_PATH = BASE_DIR / "data" / "processed" / "financial_statement.csv"
EXAMPLE_JSON_PATH = BASE_DIR / "data" / "raw" / "samsung_2023_financial_statement.json"
ACCOUNT_MAPPING = {
    "자산총계": {
        "account_ids": ["ifrs-full_Assets"],
        "account_names": ["자산총계"],
        "sj_names": ["재무상태표"],
    },
    "부채총계": {
        "account_ids": ["ifrs-full_Liabilities"],
        "account_names": ["부채총계"],
        "sj_names": ["재무상태표"],
    },
    "자본총계": {
        "account_ids": ["ifrs-full_Equity"],
        "account_names": ["자본총계"],
        "sj_names": ["재무상태표"],
    },
    "매출액": {
        "account_ids": ["ifrs-full_Revenue"],
        "account_names": ["매출액", "수익(매출액)", "영업수익"],
        "sj_names": ["손익계산서", "포괄손익계산서"],
    },
    "매출원가": {
        "account_ids": ["ifrs-full_CostOfSales"],
        "account_names": ["매출원가", "영업비용"],
        "sj_names": ["손익계산서", "포괄손익계산서"],
    },
    "매출총이익": {
        "account_ids": ["ifrs-full_GrossProfit"],
        "account_names": ["매출총이익"],
        "sj_names": ["손익계산서", "포괄손익계산서"],
    },
    "영업이익": {
        "account_ids": ["dart_OperatingIncomeLoss"],
        "account_names": ["영업이익", "영업이익(손실)"],
        "sj_names": ["손익계산서", "포괄손익계산서"],
    },
    "당기순이익": {
        "account_ids": ["ifrs-full_ProfitLoss"],
        "account_names": [
            "당기순이익",
            "당기순이익(손실)",
            "당기순이익(손실)(A)",
            "당기순손익",
            "당기순손실",
            "분기순이익",
            "분기순이익(손실)",
            "분기순손익",
            "분기순손실",
            "반기순이익",
            "반기순이익(손실)",
            "반기순손익",
            "반기순손실",
        ],
        "sj_names": ["손익계산서", "포괄손익계산서"],
    },
    "영업활동현금흐름": {
        "account_ids": ["ifrs-full_CashFlowsFromUsedInOperatingActivities"],
        "account_names": ["영업활동현금흐름", "영업활동 현금흐름", "영업활동으로 인한 현금흐름"],
        "sj_names": ["현금흐름표"],
    },
    "투자활동현금흐름": {
        "account_ids": ["ifrs-full_CashFlowsFromUsedInInvestingActivities"],
        "account_names": ["투자활동현금흐름", "투자활동 현금흐름", "투자활동으로 인한 현금흐름"],
        "sj_names": ["현금흐름표"],
    },
    "재무활동현금흐름": {
        "account_ids": ["ifrs-full_CashFlowsFromUsedInFinancingActivities"],
        "account_names": ["재무활동현금흐름", "재무활동 현금흐름", "재무활동으로 인한 현금흐름"],
        "sj_names": ["현금흐름표"],
    },
}
AMOUNT_FIELDS = [
    ("thstrm_amount", 0),
    ("frmtrm_amount", 1),
    ("bfefrmtrm_amount", 2),
]
CURRENT_PERIOD_AMOUNT_FIELDS = [
    ("thstrm_amount", 0),
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
NET_INCOME_EXCLUDED_TEXTS = [
    "지배기업",
    "비지배",
    "소유주",
    "귀속",
]


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


def is_excluded_net_income_row(standard_account_name, dart_row):
    """Avoid owner/non-controlling interest rows for 당기순이익."""
    if standard_account_name != "당기순이익":
        return False

    account_name = dart_row.get("account_nm", "")

    for excluded_text in NET_INCOME_EXCLUDED_TEXTS:
        if excluded_text in account_name:
            return True

    return False


def print_rejected_candidate(standard_account_name, dart_row, reason):
    """Print why a candidate row was rejected."""
    print(
        f'Rejected "{standard_account_name}" candidate | '
        f'raw_account="{dart_row.get("account_nm", "")}" | '
        f'sj_nm="{dart_row.get("sj_nm", "")}" | '
        f"reason={reason}"
    )


def find_rows_by_account_id_and_section(dart_rows, account_id, sj_names, standard_account_name):
    """Find DART rows matching both account_id and sj_nm."""
    matching_rows = []

    for dart_row in dart_rows:
        account_matches = dart_row.get("account_id", "") == account_id

        if not account_matches:
            continue

        section_matches = dart_row.get("sj_nm", "") in sj_names

        if not section_matches:
            print_rejected_candidate(standard_account_name, dart_row, "statement section did not match")
            continue

        if is_excluded_net_income_row(standard_account_name, dart_row):
            print_rejected_candidate(standard_account_name, dart_row, "ownership attribution row")
            continue

        matching_rows.append(dart_row)

    return matching_rows


def find_rows_by_account_name_and_section(dart_rows, account_name, sj_names, standard_account_name):
    """Find DART rows matching both account_nm and sj_nm."""
    matching_rows = []

    for dart_row in dart_rows:
        account_matches = dart_row.get("account_nm", "") == account_name

        if not account_matches:
            continue

        section_matches = dart_row.get("sj_nm", "") in sj_names

        if not section_matches:
            print_rejected_candidate(standard_account_name, dart_row, "statement section did not match")
            continue

        if is_excluded_net_income_row(standard_account_name, dart_row):
            print_rejected_candidate(standard_account_name, dart_row, "ownership attribution row")
            continue

        matching_rows.append(dart_row)

    return matching_rows


def build_row_from_dart_row(dart_row, standard_account_name, corp_name, corp_code, report_code, fs_div, amount_field, years_ago):
    """Build one output row from one DART row and amount field."""
    amount = convert_amount_to_int(dart_row.get(amount_field, ""))

    if amount is None:
        return None

    business_year = int(dart_row.get("bsns_year", ""))

    return {
        "corp_code": corp_code,
        "corp_name": corp_name,
        "year": business_year - years_ago,
        "report_code": report_code,
        "fs_div": fs_div,
        "account_nm": standard_account_name,
        "amount": amount,
    }


def get_valid_amounts(dart_row, amount_fields):
    """Return valid amount values from one DART row."""
    valid_amounts = []

    for amount_field, years_ago in amount_fields:
        amount = convert_amount_to_int(dart_row.get(amount_field, ""))

        if amount is not None:
            valid_amounts.append((amount_field, years_ago, amount))

    return valid_amounts


def has_non_zero_amount(valid_amounts):
    """Check whether any amount is not zero."""
    for amount_field, years_ago, amount in valid_amounts:
        if amount != 0:
            return True

    return False


def print_candidate_warning(standard_account_name, match_label, candidate_rows, amount_fields):
    """Print candidate rows when more than one valid row is available."""
    print(f'Warning: Multiple valid rows found for "{standard_account_name}" using {match_label}.')

    for row in candidate_rows:
        valid_amounts = get_valid_amounts(row, amount_fields)
        amount_values = [str(amount) for amount_field, years_ago, amount in valid_amounts]
        print(
            "  candidate: "
            f"sj_nm={row.get('sj_nm', '')}, "
            f"account_id={row.get('account_id', '')}, "
            f"account_nm={row.get('account_nm', '')}, "
            f"ord={row.get('ord', '')}, "
            f"amounts={', '.join(amount_values)}"
        )


def choose_best_candidate_row(candidate_rows, amount_fields):
    """Prefer non-zero amounts, otherwise use the first valid row."""
    rows_with_amounts = []

    for row in candidate_rows:
        valid_amounts = get_valid_amounts(row, amount_fields)

        if valid_amounts:
            rows_with_amounts.append((row, valid_amounts))

    if not rows_with_amounts:
        return None

    for row, valid_amounts in rows_with_amounts:
        if has_non_zero_amount(valid_amounts):
            return row

    return rows_with_amounts[0][0]


def get_valid_candidate_rows(candidate_rows, standard_account_name, amount_fields):
    """Keep only candidate rows with at least one valid amount."""
    valid_candidate_rows = []

    for candidate_row in candidate_rows:
        if get_valid_amounts(candidate_row, amount_fields):
            valid_candidate_rows.append(candidate_row)
        else:
            print_rejected_candidate(standard_account_name, candidate_row, "amount was missing or invalid")

    return valid_candidate_rows


def build_match_context(corp_name, report_code, fs_div):
    """Build a short context string for fallback diagnostics."""
    context_parts = []

    if corp_name:
        context_parts.append(str(corp_name))

    if report_code:
        context_parts.append(str(report_code))

    if fs_div:
        context_parts.append(str(fs_div))

    return " | ".join(context_parts)


def find_best_matching_account_row(
    dart_rows,
    standard_account_name,
    account_settings,
    amount_fields,
    corp_name="",
    report_code="",
    fs_div="",
):
    """Find one account row using account_id first, then exact account_nm fallback."""
    account_ids = account_settings.get("account_ids", [])
    candidate_names = account_settings["account_names"]
    sj_names = account_settings["sj_names"]

    for sj_name in sj_names:
        print(f'Trying "{standard_account_name}" in statement section "{sj_name}".')

        for account_id in account_ids:
            candidate_rows = find_rows_by_account_id_and_section(
                dart_rows,
                account_id,
                [sj_name],
                standard_account_name,
            )
            valid_candidate_rows = get_valid_candidate_rows(candidate_rows, standard_account_name, amount_fields)

            if valid_candidate_rows:
                if len(valid_candidate_rows) > 1:
                    print_candidate_warning(
                        standard_account_name,
                        f'account_id "{account_id}"',
                        valid_candidate_rows,
                        amount_fields,
                    )

                return choose_best_candidate_row(valid_candidate_rows, amount_fields)

        print(f'No valid account_id amount found for "{standard_account_name}" in "{sj_name}".')

    for sj_name in sj_names:
        print(f'Trying exact account_nm fallback for "{standard_account_name}" in statement section "{sj_name}".')

        for candidate_name in candidate_names:
            candidate_rows = find_rows_by_account_name_and_section(
                dart_rows,
                candidate_name,
                [sj_name],
                standard_account_name,
            )
            valid_candidate_rows = get_valid_candidate_rows(candidate_rows, standard_account_name, amount_fields)

            if valid_candidate_rows:
                if len(valid_candidate_rows) > 1:
                    print_candidate_warning(
                        standard_account_name,
                        f'raw account "{candidate_name}"',
                        valid_candidate_rows,
                        amount_fields,
                    )

                selected_row = choose_best_candidate_row(valid_candidate_rows, amount_fields)
                context = build_match_context(corp_name, report_code, fs_div)
                print(
                    f'[ACCOUNT FALLBACK] {context} | {standard_account_name} | '
                    f'matched by account_nm="{selected_row.get("account_nm", "")}"'
                )
                return selected_row

        print(f'No valid fallback amount found for "{standard_account_name}" in "{sj_name}".')

    print(f'No valid amount found for "{standard_account_name}".')
    return None


def build_rows_from_selected_row(selected_row, standard_account_name, corp_name, corp_code, report_code, fs_div, amount_fields):
    """Build output rows from the selected DART row."""
    output_rows = []

    for amount_field, years_ago in amount_fields:
        output_row = build_row_from_dart_row(
            selected_row,
            standard_account_name,
            corp_name,
            corp_code,
            report_code,
            fs_div,
            amount_field,
            years_ago,
        )

        if output_row is not None:
            output_rows.append(output_row)
            print(
                f'Matched "{standard_account_name}" | '
                f'raw_account="{selected_row.get("account_nm", "")}" | '
                f'sj_nm="{selected_row.get("sj_nm", "")}" | '
                f'selected_amount={output_row["amount"]}'
            )

    return output_rows


def find_first_valid_account_rows(dart_rows, standard_account_name, account_settings, corp_name, corp_code, report_code, fs_div, amount_fields):
    """Find one valid account row and build output rows."""
    selected_row = find_best_matching_account_row(
        dart_rows,
        standard_account_name,
        account_settings,
        amount_fields,
        corp_name=corp_name,
        report_code=report_code,
        fs_div=fs_div,
    )

    if selected_row is None:
        return []

    return build_rows_from_selected_row(
        selected_row,
        standard_account_name,
        corp_name,
        corp_code,
        report_code,
        fs_div,
        amount_fields,
    )


def build_output_rows(response_data, corp_name, corp_code, report_code, fs_div, current_period_only=False):
    """Build generic financial statement rows from the DART JSON response."""
    output_rows = []
    dart_rows = response_data.get("list", [])
    amount_fields = AMOUNT_FIELDS

    if current_period_only:
        amount_fields = CURRENT_PERIOD_AMOUNT_FIELDS

    for standard_account_name, account_settings in ACCOUNT_MAPPING.items():
        account_rows = find_first_valid_account_rows(
            dart_rows,
            standard_account_name,
            account_settings,
            corp_name,
            corp_code,
            report_code,
            fs_div,
            amount_fields,
        )
        output_rows.extend(account_rows)

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


def extract_accounts(json_path, corp_name, corp_code, report_code, fs_div, current_period_only=False):
    """Extract selected accounts from a saved DART JSON file."""
    try:
        print(f"Reading JSON file: {json_path}")
        response_data = read_json_file(json_path)

        print("Extracting selected financial statement accounts...")
        new_rows = build_output_rows(
            response_data,
            corp_name,
            corp_code,
            report_code,
            fs_div,
            current_period_only=current_period_only,
        )

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
