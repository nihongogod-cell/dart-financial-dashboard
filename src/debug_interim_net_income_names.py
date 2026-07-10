import json
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from fetch_financial_statement import COMPANY_LIST_PATH, build_request_url, find_corp_code, load_api_key


COMPANY_NAME = "삼성전자"
FS_DIVS = ["CFS", "OFS"]
REPORT_CODES = ["11013", "11012", "11014"]
REPORT_LABELS = {
    "11013": "1분기보고서",
    "11012": "반기보고서",
    "11014": "3분기보고서",
}
NET_INCOME_ACCOUNT_ID = "ifrs-full_ProfitLoss"
BLANK_TEXT = "<blank>"


def print_section(title):
    """Print a clear terminal section header."""
    print(f"\n=== {title} ===")


def show(value):
    """Show blank values explicitly."""
    if value is None or value == "":
        return BLANK_TEXT

    return str(value)


def amount_text(row, field_name):
    """Return an amount field as display text."""
    return show(row.get(field_name, ""))


def amount_tuple(row):
    """Return the amount fields used to compare duplicate rows."""
    return (
        row.get("thstrm_amount", ""),
        row.get("thstrm_add_amount", ""),
        row.get("frmtrm_add_amount", ""),
    )


def fetch_report(api_key, corp_code, bsns_year, report_code, fs_div):
    """Fetch one OpenDART report in memory only."""
    request_url = build_request_url(api_key, corp_code, bsns_year, report_code, fs_div)

    with urlopen(request_url) as response:
        response_text = response.read().decode("utf-8")

    return json.loads(response_text)


def safe_fetch_report(api_key, corp_code, bsns_year, report_code, fs_div):
    """Fetch one report safely without writing any file."""
    try:
        return fetch_report(api_key, corp_code, bsns_year, report_code, fs_div)
    except json.JSONDecodeError as error:
        print(f"{bsns_year} {report_code} {fs_div}: JSON error - {error}")
    except HTTPError as error:
        print(f"{bsns_year} {report_code} {fs_div}: HTTP error - {error.code}")
    except URLError as error:
        print(f"{bsns_year} {report_code} {fs_div}: network error - {error.reason}")
    except OSError as error:
        print(f"{bsns_year} {report_code} {fs_div}: connection error - {error}")

    return {"status": "", "message": "", "list": []}


def get_rows(response_data):
    """Return DART rows safely."""
    rows = response_data.get("list", [])

    if rows is None:
        return []

    return rows


def is_valid_report(response_data):
    """Return True for a usable DART report response."""
    return response_data.get("status") == "000" and bool(get_rows(response_data))


def print_availability(bsns_year, report_code, fs_div, response_data):
    """Print one report availability check."""
    print(
        " | ".join(
            [
                f"bsns_year={bsns_year}",
                f"report_code={report_code}",
                f"report_label={REPORT_LABELS.get(report_code, report_code)}",
                f"fs_div={fs_div}",
                f"status={show(response_data.get('status', ''))}",
                f"message={show(response_data.get('message', ''))}",
                f"row_count={len(get_rows(response_data))}",
            ]
        )
    )


def find_latest_valid_report(api_key, corp_code, report_code, fs_div):
    """Search backward from the current year until one valid report is found."""
    current_year = datetime.now().year

    for year in range(current_year, current_year - 8, -1):
        bsns_year = str(year)
        response_data = safe_fetch_report(api_key, corp_code, bsns_year, report_code, fs_div)
        print_availability(bsns_year, report_code, fs_div, response_data)

        if is_valid_report(response_data):
            return bsns_year, response_data

    return None, None


def find_profit_loss_rows(response_data):
    """Find rows where account_id is ifrs-full_ProfitLoss."""
    matching_rows = []

    for row in get_rows(response_data):
        if row.get("account_id", "") == NET_INCOME_ACCOUNT_ID:
            matching_rows.append(row)

    return matching_rows


def print_profit_loss_row(bsns_year, report_code, fs_div, row):
    """Print one ifrs-full_ProfitLoss row."""
    print(
        " | ".join(
            [
                f"bsns_year={bsns_year}",
                f"report_code={report_code}",
                f"report_label={REPORT_LABELS.get(report_code, report_code)}",
                f"fs_div={fs_div}",
                f"sj_nm={show(row.get('sj_nm', ''))}",
                f"account_nm={show(row.get('account_nm', ''))}",
                f"account_id={show(row.get('account_id', ''))}",
                f"thstrm_amount={amount_text(row, 'thstrm_amount')}",
                f"thstrm_add_amount={amount_text(row, 'thstrm_add_amount')}",
                f"frmtrm_add_amount={amount_text(row, 'frmtrm_add_amount')}",
                f"ord={show(row.get('ord', ''))}",
            ]
        )
    )


def print_duplicate_diagnostic(rows):
    """Print whether ProfitLoss appears in both income statement sections."""
    statement_names = sorted(set(row.get("sj_nm", "") for row in rows))
    appears_in_both = "손익계산서" in statement_names and "포괄손익계산서" in statement_names
    identical_amounts = len(set(amount_tuple(row) for row in rows)) <= 1 if rows else False

    print(f"appears in both 손익계산서 and 포괄손익계산서: {'yes' if appears_in_both else 'no'}")

    if len(rows) > 1:
        print(f"duplicate rows have identical amount fields: {'yes' if identical_amounts else 'no'}")


def inspect_report(api_key, corp_code, report_code, fs_div):
    """Inspect one report type and fs_div."""
    print_section(f"{REPORT_LABELS.get(report_code, report_code)} {fs_div}")
    bsns_year, response_data = find_latest_valid_report(api_key, corp_code, report_code, fs_div)

    if response_data is None:
        print("No valid report found.")
        return []

    rows = find_profit_loss_rows(response_data)
    print(f"ifrs-full_ProfitLoss rows found: {len(rows)}")

    for row in rows:
        print_profit_loss_row(bsns_year, report_code, fs_div, row)

    print_duplicate_diagnostic(rows)
    return rows


def raw_net_income_name(rows):
    """Return raw account names for final conclusion."""
    names = sorted(set(row.get("account_nm", "") for row in rows if row.get("account_nm", "")))

    if not names:
        return BLANK_TEXT

    return ", ".join(names)


def safe_account_names_to_add(results):
    """Return raw names found through ifrs-full_ProfitLoss evidence."""
    names = []

    for rows in results.values():
        for row in rows:
            account_name = row.get("account_nm", "")

            if account_name:
                names.append(account_name)

    unique_names = sorted(set(names))

    if not unique_names:
        return BLANK_TEXT

    return ", ".join(unique_names)


def print_final_conclusion(results):
    """Print the required final conclusion."""
    print("\n=== Final Conclusion ===\n")

    for report_code in REPORT_CODES:
        report_label = REPORT_LABELS[report_code]

        for fs_div in FS_DIVS:
            rows = results.get((report_code, fs_div), [])
            print(f"{report_label} {fs_div} raw net income name: {raw_net_income_name(rows)}")

        print()

    print(f"Safe account names to add to 당기순이익 ACCOUNT_MAPPING: {safe_account_names_to_add(results)}")
    blocking_issue = any(not rows for rows in results.values())
    print(f"Blocking issue remains: {'yes' if blocking_issue else 'no'}")


def main():
    print_section("Setup")
    api_key = load_api_key()

    if not api_key:
        print("Failure: DART_API_KEY was not found in the project root .env file.")
        return

    corp_code = find_corp_code(COMPANY_LIST_PATH, COMPANY_NAME)

    if not corp_code:
        print(f'Failure: Could not find corp_name "{COMPANY_NAME}" in company_list.csv.')
        return

    print(f"company={COMPANY_NAME}")
    print(f"corp_code={corp_code}")

    results = {}

    for report_code in REPORT_CODES:
        for fs_div in FS_DIVS:
            results[(report_code, fs_div)] = inspect_report(api_key, corp_code, report_code, fs_div)

    print_final_conclusion(results)


if __name__ == "__main__":
    main()
