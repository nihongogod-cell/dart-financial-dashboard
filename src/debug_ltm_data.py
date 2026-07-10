import json
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from extract_accounts import ACCOUNT_MAPPING, NET_INCOME_EXCLUDED_TEXTS
from fetch_financial_statement import COMPANY_LIST_PATH, build_request_url, find_corp_code, load_api_key


COMPANY_NAME = "삼성전자"
FS_DIVS = ["CFS", "OFS"]
INCOME_ACCOUNTS = ["매출액", "매출원가", "매출총이익", "영업이익", "당기순이익"]
LTM_TEST_ACCOUNTS = ["매출액", "영업이익", "당기순이익"]
REPORT_LABELS = {
    "11011": "사업보고서",
    "11013": "1분기보고서",
    "11012": "반기보고서",
    "11014": "3분기보고서",
}
INTERIM_REPORT_PRIORITY = ["11014", "11012", "11013"]
BLANK_TEXT = "<blank>"


def print_section(title):
    """Print a clear terminal section header."""
    print(f"\n=== {title} ===")


def display_value(value):
    """Show blank or missing values explicitly."""
    if value is None or value == "":
        return BLANK_TEXT

    return str(value)


def amount_to_int(amount_text):
    """Convert a DART amount field to int, or return None."""
    if amount_text is None:
        return None

    cleaned_amount = str(amount_text).replace(",", "").strip()

    if not cleaned_amount:
        return None

    try:
        return int(cleaned_amount)
    except ValueError:
        return None


def fetch_report(api_key, corp_code, bsns_year, report_code, fs_div):
    """Fetch one DART report in memory only."""
    request_url = build_request_url(api_key, corp_code, bsns_year, report_code, fs_div)

    with urlopen(request_url) as response:
        response_text = response.read().decode("utf-8")

    return json.loads(response_text)


def safe_fetch_report(api_key, corp_code, bsns_year, report_code, fs_div, issues):
    """Fetch a report and continue safely after an API or network error."""
    try:
        return fetch_report(api_key, corp_code, bsns_year, report_code, fs_div)
    except json.JSONDecodeError as error:
        issues.append(f"{bsns_year} {report_code} {fs_div}: JSON error - {error}")
    except HTTPError as error:
        issues.append(f"{bsns_year} {report_code} {fs_div}: HTTP error - {error.code}")
    except URLError as error:
        issues.append(f"{bsns_year} {report_code} {fs_div}: network error - {error.reason}")
    except OSError as error:
        issues.append(f"{bsns_year} {report_code} {fs_div}: connection error - {error}")

    return {"status": "", "message": "", "list": []}


def has_rows(response_data):
    """Return True when a DART response contains statement rows."""
    return bool(response_data.get("list", []))


def print_response_summary(bsns_year, report_code, fs_div, response_data):
    """Print report metadata."""
    rows = response_data.get("list", [])

    print(
        " | ".join(
            [
                f"bsns_year={bsns_year}",
                f"report_code={report_code}",
                f"report_label={REPORT_LABELS.get(report_code, report_code)}",
                f"fs_div={fs_div}",
                f"status={display_value(response_data.get('status', ''))}",
                f"message={display_value(response_data.get('message', ''))}",
                f"row_count={len(rows)}",
            ]
        )
    )


def is_excluded_net_income_row(standard_account_name, row):
    """Exclude owner/non-controlling-interest rows for net income."""
    if standard_account_name != "당기순이익":
        return False

    account_name = row.get("account_nm", "")

    for excluded_text in NET_INCOME_EXCLUDED_TEXTS:
        if excluded_text in account_name:
            return True

    return False


def find_rows_for_account(rows, standard_account_name):
    """Find rows matching current ACCOUNT_MAPPING by account name and statement section."""
    account_settings = ACCOUNT_MAPPING[standard_account_name]
    matched_rows = []
    account_name_matches_wrong_section = []

    for sj_name in account_settings["sj_names"]:
        for raw_account_name in account_settings["account_names"]:
            for row in rows:
                account_matches = row.get("account_nm", "") == raw_account_name
                section_matches = row.get("sj_nm", "") == sj_name

                if not account_matches:
                    continue

                if not section_matches:
                    account_name_matches_wrong_section.append(row)
                    continue

                if is_excluded_net_income_row(standard_account_name, row):
                    continue

                matched_rows.append(row)

    return matched_rows, account_name_matches_wrong_section


def print_matched_row(bsns_year, report_code, fs_div, row):
    """Print the raw DART row fields needed for LTM diagnosis."""
    fields = [
        ("bsns_year", bsns_year),
        ("report_code", report_code),
        ("report label", REPORT_LABELS.get(report_code, report_code)),
        ("fs_div", fs_div),
        ("sj_nm", row.get("sj_nm", "")),
        ("raw account_nm", row.get("account_nm", "")),
        ("account_id", row.get("account_id", "")),
        ("thstrm_nm", row.get("thstrm_nm", "")),
        ("thstrm_amount", row.get("thstrm_amount", "")),
        ("thstrm_add_amount", row.get("thstrm_add_amount", "")),
        ("frmtrm_nm", row.get("frmtrm_nm", "")),
        ("frmtrm_amount", row.get("frmtrm_amount", "")),
        ("frmtrm_add_amount", row.get("frmtrm_add_amount", "")),
        ("ord", row.get("ord", "")),
    ]
    print(" | ".join(f"{name}={display_value(value)}" for name, value in fields))


def inspect_income_rows(bsns_year, report_code, fs_div, response_data, issues):
    """Print all matched raw rows for standardized income accounts."""
    rows = response_data.get("list", [])
    matches_by_account = {}

    print_section(f"Matched Income Rows: {bsns_year} {REPORT_LABELS.get(report_code, report_code)} {fs_div}")

    for standard_account_name in INCOME_ACCOUNTS:
        matched_rows, wrong_section_rows = find_rows_for_account(rows, standard_account_name)
        matches_by_account[standard_account_name] = matched_rows

        if not matched_rows:
            issues.append(f"{bsns_year} {report_code} {fs_div} {standard_account_name}: unmatched account name")

            if wrong_section_rows:
                issues.append(f"{bsns_year} {report_code} {fs_div} {standard_account_name}: statement-name mismatch")

            print(f"{standard_account_name}: no matched rows")
            continue

        if len(matched_rows) > 1:
            issues.append(f"{bsns_year} {report_code} {fs_div} {standard_account_name}: multiple candidate rows")

        print(f"{standard_account_name}: {len(matched_rows)} matched row(s)")

        for row in matched_rows:
            print_matched_row(bsns_year, report_code, fs_div, row)

    return matches_by_account


def choose_first_row(matches_by_account, standard_account_name):
    """Choose the first matched row for diagnostic calculations."""
    rows = matches_by_account.get(standard_account_name, [])

    if not rows:
        return None

    return rows[0]


def get_cumulative_field(report_code, row, current_or_prior):
    """Pick the cumulative amount field based on raw interim field availability."""
    if report_code == "11013":
        if current_or_prior == "current":
            return "thstrm_add_amount" if row.get("thstrm_add_amount", "") else "thstrm_amount"

        return "frmtrm_add_amount" if row.get("frmtrm_add_amount", "") else "frmtrm_amount"

    if current_or_prior == "current":
        return "thstrm_add_amount"

    return "frmtrm_add_amount"


def print_field_meaning_example(report_code, current_row, previous_row, issues):
    """Print field interpretation based on raw field names and labels."""
    current_cumulative_field = get_cumulative_field(report_code, current_row, "current")
    prior_cumulative_field = get_cumulative_field(report_code, previous_row, "prior")

    print_section("Field Meaning Check")
    print(f"current quarter-only amount field: thstrm_amount ({display_value(current_row.get('thstrm_nm', ''))})")
    print(f"year-to-date cumulative amount field: {current_cumulative_field}")
    print(f"previous-year same-period amount field: frmtrm_amount ({display_value(current_row.get('frmtrm_nm', ''))})")
    print(f"previous-year same-period cumulative amount field: {prior_cumulative_field}")

    if not current_row.get(current_cumulative_field, ""):
        issues.append(f"{REPORT_LABELS.get(report_code, report_code)}: missing cumulative field {current_cumulative_field}")

    if not previous_row.get(prior_cumulative_field, ""):
        issues.append(f"previous year {REPORT_LABELS.get(report_code, report_code)}: missing cumulative field {prior_cumulative_field}")


def calculate_ltm(annual_row, current_interim_row, previous_interim_row, interim_report_code):
    """Calculate one diagnostic LTM value when all fields are available."""
    annual_amount = amount_to_int(annual_row.get("thstrm_amount", ""))
    current_field = get_cumulative_field(interim_report_code, current_interim_row, "current")
    previous_field = get_cumulative_field(interim_report_code, previous_interim_row, "prior")
    current_cumulative_amount = amount_to_int(current_interim_row.get(current_field, ""))
    previous_cumulative_amount = amount_to_int(previous_interim_row.get(previous_field, ""))

    if annual_amount is None or current_cumulative_amount is None or previous_cumulative_amount is None:
        return None, annual_amount, current_field, current_cumulative_amount, previous_field, previous_cumulative_amount

    ltm_amount = annual_amount + current_cumulative_amount - previous_cumulative_amount
    return ltm_amount, annual_amount, current_field, current_cumulative_amount, previous_field, previous_cumulative_amount


def find_latest_annual_report(api_key, corp_code, current_year, fs_div, report_cache, issues):
    """Find the latest annual report with rows."""
    for year in range(current_year - 1, current_year - 6, -1):
        cache_key = (str(year), "11011", fs_div)
        response_data = safe_fetch_report(api_key, corp_code, str(year), "11011", fs_div, issues)
        report_cache[cache_key] = response_data
        print_response_summary(str(year), "11011", fs_div, response_data)

        if has_rows(response_data):
            return str(year), response_data

    return None, None


def find_latest_interim_report(api_key, corp_code, current_year, fs_div, report_cache, issues):
    """Find latest available current-year interim report using DART responses."""
    for report_code in INTERIM_REPORT_PRIORITY:
        current_key = (str(current_year), report_code, fs_div)
        current_response = safe_fetch_report(api_key, corp_code, str(current_year), report_code, fs_div, issues)
        report_cache[current_key] = current_response
        print_response_summary(str(current_year), report_code, fs_div, current_response)

        if not has_rows(current_response):
            continue

        previous_year = str(current_year - 1)
        previous_key = (previous_year, report_code, fs_div)
        previous_response = safe_fetch_report(api_key, corp_code, previous_year, report_code, fs_div, issues)
        report_cache[previous_key] = previous_response
        print_response_summary(previous_year, report_code, fs_div, previous_response)

        return str(current_year), report_code, current_response, previous_year, previous_response

    return None, None, None, None, None


def print_ltm_examples(fs_div, annual_year, annual_matches, interim_year, interim_code, interim_matches, previous_year, previous_matches, issues):
    """Print candidate LTM calculations for selected accounts."""
    print_section(f"Candidate LTM Calculations: {fs_div}")
    account_results = {}

    for account_name in LTM_TEST_ACCOUNTS:
        annual_row = choose_first_row(annual_matches, account_name)
        interim_row = choose_first_row(interim_matches, account_name)
        previous_row = choose_first_row(previous_matches, account_name)

        if annual_row is None or interim_row is None or previous_row is None:
            issues.append(f"{fs_div} {account_name}: cannot calculate LTM because a source row is missing")
            account_results[account_name] = False
            print(f"{account_name}: cannot calculate LTM because a source row is missing")
            continue

        result = calculate_ltm(annual_row, interim_row, previous_row, interim_code)
        ltm_amount, annual_amount, current_field, current_cumulative, previous_field, previous_cumulative = result

        print(f"\n{account_name}")
        print(f"latest annual ({annual_year}) thstrm_amount: {display_value(annual_amount)}")
        print(f"current interim ({interim_year} {REPORT_LABELS.get(interim_code, interim_code)}) {current_field}: {display_value(current_cumulative)}")
        print(f"previous same interim ({previous_year} {REPORT_LABELS.get(interim_code, interim_code)}) {previous_field}: {display_value(previous_cumulative)}")

        if ltm_amount is None:
            issues.append(f"{fs_div} {account_name}: blank value prevents LTM calculation")
            account_results[account_name] = False
            print("candidate LTM: cannot calculate")
        else:
            account_results[account_name] = True
            print(f"candidate LTM: {ltm_amount}")

    return account_results


def print_issues(issues):
    """Print diagnostic issues."""
    print_section("Issues")

    if not issues:
        print("No blocking-looking issues found in inspected responses.")
        return

    for issue in issues:
        print(f"- {issue}")


def print_conclusion(latest_interims, annual_source_field, current_cumulative_fields, previous_cumulative_fields, account_results, fs_results, issues):
    """Print the requested concise conclusion."""
    print_section("Conclusion")

    latest_interim_text = ", ".join(
        f"{fs_div}={value}" for fs_div, value in latest_interims.items()
    ) or "none"
    current_field_text = ", ".join(
        f"{fs_div}={value}" for fs_div, value in current_cumulative_fields.items()
    ) or "none"
    previous_field_text = ", ".join(
        f"{fs_div}={value}" for fs_div, value in previous_cumulative_fields.items()
    ) or "none"

    print(f"Latest available interim report: {latest_interim_text}")
    print(f"Annual source field: {annual_source_field}")
    print(f"Current interim cumulative source field: {current_field_text}")
    print(f"Previous-year same-period cumulative source field: {previous_field_text}")

    for account_name in LTM_TEST_ACCOUNTS:
        is_valid = any(results.get(account_name, False) for results in account_results.values())
        print(f"LTM formula validated for {account_name}: {'yes' if is_valid else 'no'}")

    print(f"CFS validated: {'yes' if fs_results.get('CFS', False) else 'no'}")
    print(f"OFS validated: {'yes' if fs_results.get('OFS', False) else 'no'}")
    print(f"Blocking issue found: {'yes' if issues else 'no'}")


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

    print(f"company: {COMPANY_NAME}")
    print(f"corp_code: {corp_code}")

    current_year = datetime.now().year
    issues = []
    report_cache = {}
    latest_interims = {}
    current_cumulative_fields = {}
    previous_cumulative_fields = {}
    account_results = {}
    fs_results = {}

    for fs_div in FS_DIVS:
        print_section(f"Report Availability: {fs_div}")
        annual_year, annual_response = find_latest_annual_report(api_key, corp_code, current_year, fs_div, report_cache, issues)
        interim_year, interim_code, interim_response, previous_year, previous_response = find_latest_interim_report(
            api_key,
            corp_code,
            current_year,
            fs_div,
            report_cache,
            issues,
        )

        if annual_response is None or interim_response is None or previous_response is None:
            issues.append(f"{fs_div}: missing annual, current interim, or previous-year same interim response")
            latest_interims[fs_div] = "not found"
            account_results[fs_div] = {}
            fs_results[fs_div] = False
            continue

        latest_interims[fs_div] = f"{interim_year} {interim_code} {REPORT_LABELS.get(interim_code, interim_code)}"

        annual_matches = inspect_income_rows(annual_year, "11011", fs_div, annual_response, issues)
        interim_matches = inspect_income_rows(interim_year, interim_code, fs_div, interim_response, issues)
        previous_matches = inspect_income_rows(previous_year, interim_code, fs_div, previous_response, issues)

        example_current_row = choose_first_row(interim_matches, "매출액")
        example_previous_row = choose_first_row(previous_matches, "매출액")

        if example_current_row is not None and example_previous_row is not None:
            current_field = get_cumulative_field(interim_code, example_current_row, "current")
            previous_field = get_cumulative_field(interim_code, example_previous_row, "prior")
            current_cumulative_fields[fs_div] = current_field
            previous_cumulative_fields[fs_div] = previous_field
            print_field_meaning_example(interim_code, example_current_row, example_previous_row, issues)
        else:
            current_cumulative_fields[fs_div] = "not found"
            previous_cumulative_fields[fs_div] = "not found"

        account_results[fs_div] = print_ltm_examples(
            fs_div,
            annual_year,
            annual_matches,
            interim_year,
            interim_code,
            interim_matches,
            previous_year,
            previous_matches,
            issues,
        )
        fs_results[fs_div] = all(account_results[fs_div].get(account_name, False) for account_name in LTM_TEST_ACCOUNTS)

    cfs_interim = latest_interims.get("CFS")
    ofs_interim = latest_interims.get("OFS")

    if cfs_interim and ofs_interim and cfs_interim != ofs_interim:
        issues.append("CFS/OFS availability difference")

    print_issues(issues)
    print_conclusion(
        latest_interims,
        "thstrm_amount",
        current_cumulative_fields,
        previous_cumulative_fields,
        account_results,
        fs_results,
        issues,
    )


if __name__ == "__main__":
    main()
