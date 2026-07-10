import json
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from extract_accounts import ACCOUNT_MAPPING, NET_INCOME_EXCLUDED_TEXTS
from fetch_financial_statement import COMPANY_LIST_PATH, build_request_url, find_corp_code, load_api_key


COMPANY_NAME = "LG전자"
FS_DIVS = ["CFS", "OFS"]
ANNUAL_REPORT_CODE = "11011"
INTERIM_REPORT_CODES = ["11014", "11012", "11013"]
REPORT_LABELS = {
    "11011": "사업보고서",
    "11013": "1분기보고서",
    "11012": "반기보고서",
    "11014": "3분기보고서",
}
ANNUAL_KEYWORDS = ["당기", "분기", "반기", "순이익", "순손익", "순손실"]
INTERIM_KEYWORDS = [
    "당기",
    "분기",
    "반기",
    "순이익",
    "순손익",
    "순손실",
    "계속영업",
    "중단영업",
    "지배기업",
    "비지배",
    "소유주",
    "귀속",
]
NET_INCOME_ACCOUNT_ID = "ifrs-full_ProfitLoss"
INCOME_STATEMENT_NAMES = ["손익계산서", "포괄손익계산서"]
BLANK_TEXT = "<blank>"


def print_section(title):
    """Print a clear terminal section header."""
    print(f"\n=== {title} ===")


def show(value):
    """Print blank values explicitly."""
    if value is None or value == "":
        return BLANK_TEXT

    return str(value)


def amount_to_int(amount_text):
    """Convert a DART amount field to int."""
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
    """Fetch one OpenDART report in memory only."""
    request_url = build_request_url(api_key, corp_code, bsns_year, report_code, fs_div)

    with urlopen(request_url) as response:
        response_text = response.read().decode("utf-8")

    return json.loads(response_text)


def safe_fetch_report(api_key, corp_code, bsns_year, report_code, fs_div):
    """Fetch one report safely without saving raw JSON."""
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
    """Return DART response rows safely."""
    rows = response_data.get("list", [])

    if rows is None:
        return []

    return rows


def is_valid_report(response_data):
    """A valid report requires status 000 and a non-empty list."""
    return response_data.get("status") == "000" and bool(get_rows(response_data))


def report_metadata(bsns_year, report_code, fs_div, response_data):
    """Build report metadata text."""
    return (
        f"bsns_year={show(bsns_year)} | "
        f"report_code={show(report_code)} | "
        f"report_label={REPORT_LABELS.get(report_code, report_code)} | "
        f"fs_div={fs_div} | "
        f"status={show(response_data.get('status', ''))} | "
        f"message={show(response_data.get('message', ''))} | "
        f"row_count={len(get_rows(response_data))}"
    )


def print_report_metadata(title, report_info):
    """Print selected report metadata."""
    print_section(title)

    if report_info is None:
        print("not found")
        return

    print(
        report_metadata(
            report_info["year"],
            report_info["report_code"],
            report_info["fs_div"],
            report_info["response"],
        )
    )


def print_raw_row(report_info, row):
    """Print one diagnostic raw row."""
    fields = [
        ("fs_div", report_info["fs_div"]),
        ("sj_nm", row.get("sj_nm", "")),
        ("account_nm", row.get("account_nm", "")),
        ("account_id", row.get("account_id", "")),
        ("thstrm_nm", row.get("thstrm_nm", "")),
        ("thstrm_amount", row.get("thstrm_amount", "")),
        ("thstrm_add_amount", row.get("thstrm_add_amount", "")),
        ("frmtrm_nm", row.get("frmtrm_nm", "")),
        ("frmtrm_amount", row.get("frmtrm_amount", "")),
        ("frmtrm_add_amount", row.get("frmtrm_add_amount", "")),
        ("ord", row.get("ord", "")),
    ]
    print(" | ".join(f"{field_name}={show(value)}" for field_name, value in fields))


def find_latest_annual_report(api_key, corp_code, fs_div):
    """Find latest valid annual report for one fs_div."""
    current_year = datetime.now().year

    for year in range(current_year, current_year - 8, -1):
        response_data = safe_fetch_report(api_key, corp_code, str(year), ANNUAL_REPORT_CODE, fs_div)

        if is_valid_report(response_data):
            return {
                "year": str(year),
                "report_code": ANNUAL_REPORT_CODE,
                "fs_div": fs_div,
                "response": response_data,
            }

    return None


def find_latest_interim_report(api_key, corp_code, fs_div, annual_report):
    """Find latest valid interim report after the latest annual year."""
    if annual_report is None:
        return None

    current_year = datetime.now().year
    annual_year = int(annual_report["year"])

    for year in range(current_year, annual_year, -1):
        for report_code in INTERIM_REPORT_CODES:
            response_data = safe_fetch_report(api_key, corp_code, str(year), report_code, fs_div)

            if is_valid_report(response_data):
                return {
                    "year": str(year),
                    "report_code": report_code,
                    "fs_div": fs_div,
                    "response": response_data,
                }

    return None


def row_matches_keywords(row, keywords):
    """Check whether a row is relevant to net income diagnostics."""
    account_name = row.get("account_nm", "")
    account_id = row.get("account_id", "")

    return account_id == NET_INCOME_ACCOUNT_ID or any(keyword in account_name for keyword in keywords)


def print_matching_rows(report_info, keywords, title):
    """Print matching net-income-related rows in income statement sections."""
    print_section(title)

    if report_info is None:
        print("report not found")
        return

    found = False

    for row in get_rows(report_info["response"]):
        if row.get("sj_nm", "") not in INCOME_STATEMENT_NAMES:
            continue

        if not row_matches_keywords(row, keywords):
            continue

        found = True
        print_raw_row(report_info, row)

    if not found:
        print("no matching rows found")


def classify_net_income_row(row):
    """Classify whether a row is total net income or a component/attribution row."""
    account_name = row.get("account_nm", "")
    account_id = row.get("account_id", "")

    if account_id == NET_INCOME_ACCOUNT_ID:
        return "total net income"

    if "계속영업" in account_name:
        return "continuing operations component only"

    if "중단영업" in account_name:
        return "discontinued operations component only"

    if "비지배" in account_name:
        return "non-controlling interest attribution only"

    if "지배기업" in account_name or "소유주" in account_name or "귀속" in account_name:
        return "parent-owner attribution only"

    return "unclear"


def find_total_net_income_row(report_info):
    """Find the exact total net income row using account_id and statement context."""
    if report_info is None:
        return None

    candidates = []

    for row in get_rows(report_info["response"]):
        if row.get("sj_nm", "") not in INCOME_STATEMENT_NAMES:
            continue

        if row.get("account_id", "") == NET_INCOME_ACCOUNT_ID:
            candidates.append(row)

    if not candidates:
        return None

    for row in candidates:
        if row.get("sj_nm", "") == "손익계산서":
            return row

    return candidates[0]


def current_mapping_matches(row):
    """Test whether current 당기순이익 mapping matches the selected row."""
    if row is None:
        return False

    mapping = ACCOUNT_MAPPING["당기순이익"]
    account_matches = row.get("account_nm", "") in mapping["account_names"]
    section_matches = row.get("sj_nm", "") in mapping["sj_names"]
    return account_matches and section_matches


def exclusion_filter_removes(row):
    """Test whether current exclusion keywords would remove the row."""
    if row is None:
        return False

    account_name = row.get("account_nm", "")

    for excluded_text in NET_INCOME_EXCLUDED_TEXTS:
        if excluded_text in account_name:
            return True

    return False


def cumulative_fields_available(row):
    """Check whether interim cumulative source fields exist and are numeric."""
    if row is None:
        return False

    current_cumulative = amount_to_int(row.get("thstrm_add_amount", ""))
    previous_cumulative = amount_to_int(row.get("frmtrm_add_amount", ""))
    return current_cumulative is not None and previous_cumulative is not None


def calculate_ltm(annual_row, interim_row):
    """Calculate LTM from annual and interim source rows."""
    if annual_row is None or interim_row is None:
        return None

    annual_amount = amount_to_int(annual_row.get("thstrm_amount", ""))
    current_cumulative = amount_to_int(interim_row.get("thstrm_add_amount", ""))
    previous_cumulative = amount_to_int(interim_row.get("frmtrm_add_amount", ""))

    if annual_amount is None or current_cumulative is None or previous_cumulative is None:
        return None

    return {
        "annual_amount": annual_amount,
        "current_cumulative": current_cumulative,
        "previous_cumulative": previous_cumulative,
        "ltm_amount": annual_amount + current_cumulative - previous_cumulative,
    }


def print_mapping_test(report_info, total_row):
    """Print mapping and source-field diagnostics for the selected total net income row."""
    print_section(f"Mapping Test: {report_info['fs_div'] if report_info else BLANK_TEXT}")

    if total_row is None:
        print("total net income row: not found")
        return

    print(f"exact account_nm: {show(total_row.get('account_nm', ''))}")
    print(f"exact sj_nm: {show(total_row.get('sj_nm', ''))}")
    print(f"classification: {classify_net_income_row(total_row)}")
    print(f"current candidate matching succeeds: {'yes' if current_mapping_matches(total_row) else 'no'}")
    print(f"exclusion logic removes it: {'yes' if exclusion_filter_removes(total_row) else 'no'}")
    print(f"cumulative source fields are present: {'yes' if cumulative_fields_available(total_row) else 'no'}")


def print_ltm_calculation(fs_div, annual_row, interim_row):
    """Print LTM source values and result if possible."""
    print_section(f"LTM Calculation: {fs_div}")
    ltm_data = calculate_ltm(annual_row, interim_row)

    if ltm_data is None:
        print("LTM calculation is not possible.")
        return

    print(f"latest annual thstrm_amount: {ltm_data['annual_amount']}")
    print(f"latest interim thstrm_add_amount: {ltm_data['current_cumulative']}")
    print(f"latest interim frmtrm_add_amount: {ltm_data['previous_cumulative']}")
    print(f"LTM: {ltm_data['ltm_amount']}")


def report_summary(report_info):
    """Return compact selected report text for final conclusion."""
    if report_info is None:
        return "not found"

    return (
        f"bsns_year={report_info['year']} | "
        f"report_code={report_info['report_code']} | "
        f"report_label={REPORT_LABELS[report_info['report_code']]}"
    )


def yes_no(value):
    """Return yes/no text."""
    return "yes" if value else "no"


def root_cause_for_result(result):
    """Infer a concise root cause from one fs_div diagnostic result."""
    total_row = result["interim_total_row"]

    if total_row is None:
        return "total net income row not found"

    if not current_mapping_matches(total_row):
        return f'account name mismatch: "{total_row.get("account_nm", "")}" is not matched by current 당기순이익 mapping'

    if exclusion_filter_removes(total_row):
        return "current exclusion filter removes the total net income row"

    if not cumulative_fields_available(total_row):
        return "cumulative LTM source fields are missing or invalid"

    return "no blocking root cause found"


def smallest_fix_for_result(result):
    """Suggest the smallest safe fix from the diagnostic evidence."""
    total_row = result["interim_total_row"]

    if total_row is None:
        return "inspect account_id ifrs-full_ProfitLoss rows for the selected interim report"

    if not current_mapping_matches(total_row):
        return f'add "{total_row.get("account_nm", "")}" to 당기순이익 account_names if confirmed across CFS/OFS'

    if exclusion_filter_removes(total_row):
        return "narrow the exclusion rule so it does not remove total ifrs-full_ProfitLoss rows"

    if not cumulative_fields_available(total_row):
        return "do not calculate LTM until thstrm_add_amount and frmtrm_add_amount are available"

    return "no fix required"


def inspect_fs_div(api_key, corp_code, fs_div):
    """Run all diagnostics for one fs_div."""
    annual_report = find_latest_annual_report(api_key, corp_code, fs_div)
    interim_report = find_latest_interim_report(api_key, corp_code, fs_div, annual_report)

    print_report_metadata(f"Selected Annual Report: {fs_div}", annual_report)
    print_report_metadata(f"Selected Interim Report: {fs_div}", interim_report)

    print_matching_rows(
        annual_report,
        ANNUAL_KEYWORDS,
        f"Annual Net-Income-Related Rows: {fs_div}",
    )
    print_matching_rows(
        interim_report,
        INTERIM_KEYWORDS,
        f"Interim Net-Income-Related Rows: {fs_div}",
    )

    annual_total_row = find_total_net_income_row(annual_report)
    interim_total_row = find_total_net_income_row(interim_report)
    print_mapping_test(interim_report, interim_total_row)
    print_ltm_calculation(fs_div, annual_total_row, interim_total_row)

    return {
        "annual_report": annual_report,
        "interim_report": interim_report,
        "annual_total_row": annual_total_row,
        "interim_total_row": interim_total_row,
    }


def print_mapping_configuration():
    """Print current 당기순이익 mapping configuration."""
    print_section("Current 당기순이익 Mapping")
    mapping = ACCOUNT_MAPPING["당기순이익"]
    print(f"account_names: {mapping['account_names']}")
    print(f"sj_names: {mapping['sj_names']}")
    print(f"exclusion keywords: {NET_INCOME_EXCLUDED_TEXTS}")
    print("exclusion behavior: rows are removed when account_nm contains any exclusion keyword")


def print_final_conclusion(results):
    """Print the exact requested final conclusion shape."""
    print("\n=== Final Conclusion ===\n")

    for fs_div in FS_DIVS:
        result = results.get(fs_div, {})
        annual_report = result.get("annual_report")
        interim_report = result.get("interim_report")
        total_row = result.get("interim_total_row")
        mapping_match = current_mapping_matches(total_row)
        exclusion_removed = exclusion_filter_removes(total_row)
        cumulative_available = cumulative_fields_available(total_row)
        ltm_possible = calculate_ltm(result.get("annual_total_row"), total_row) is not None

        print(f"{fs_div} latest annual report: {report_summary(annual_report)}")
        print(f"{fs_div} latest interim report: {report_summary(interim_report)}")
        print(f"{fs_div} total net income raw account: {show(total_row.get('account_nm', '') if total_row else '')}")
        print(f"{fs_div} current mapping match: {yes_no(mapping_match)}")
        print(f"{fs_div} exclusion filter result: {'removed' if exclusion_removed else 'not removed'}")
        print(f"{fs_div} cumulative fields available: {yes_no(cumulative_available)}")
        print(f"{fs_div} LTM calculation possible: {yes_no(ltm_possible)}")
        print()

    root_causes = sorted(set(root_cause_for_result(result) for result in results.values()))
    fixes = sorted(set(smallest_fix_for_result(result) for result in results.values()))
    blocking_issue = any(calculate_ltm(result.get("annual_total_row"), result.get("interim_total_row")) is None for result in results.values())

    print(f"Confirmed root cause: {'; '.join(root_causes)}")
    print(f"Smallest safe fix: {'; '.join(fixes)}")
    print(f"Blocking issue remains: {yes_no(blocking_issue)}")


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
    print_mapping_configuration()

    results = {}

    for fs_div in FS_DIVS:
        results[fs_div] = inspect_fs_div(api_key, corp_code, fs_div)

    print_final_conclusion(results)


if __name__ == "__main__":
    main()
