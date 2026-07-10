import json
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from extract_accounts import ACCOUNT_MAPPING, NET_INCOME_EXCLUDED_TEXTS
from fetch_financial_statement import COMPANY_LIST_PATH, build_request_url, find_corp_code, load_api_key


COMPANY_NAME = "삼성전자"
FS_DIVS = ["CFS", "OFS"]
REPORT_LABELS = {
    "11011": "사업보고서",
    "11013": "1분기보고서",
    "11012": "반기보고서",
    "11014": "3분기보고서",
}
INTERIM_REPORT_CODES = ["11014", "11012", "11013"]
INCOME_ACCOUNTS = ["매출액", "매출원가", "매출총이익", "영업이익", "당기순이익"]
NET_INCOME_KEYWORDS = [
    "당기",
    "분기",
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
    """Convert a DART amount string to an integer."""
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


def safe_fetch_report(api_key, corp_code, bsns_year, report_code, fs_div, issues):
    """Fetch a report without stopping the whole diagnostic on one failure."""
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


def get_rows(response_data):
    """Return DART list rows safely."""
    rows = response_data.get("list", [])

    if rows is None:
        return []

    return rows


def is_valid_response(response_data):
    """A valid report must have status 000 and non-empty list rows."""
    return response_data.get("status") == "000" and bool(get_rows(response_data))


def print_availability(bsns_year, report_code, fs_div, response_data):
    """Print one availability check in the requested format."""
    rows = get_rows(response_data)
    print(
        " | ".join(
            [
                f"bsns_year={bsns_year}",
                f"report_code={report_code}",
                f"report_label={REPORT_LABELS.get(report_code, report_code)}",
                f"fs_div={fs_div}",
                f"status={show(response_data.get('status', ''))}",
                f"message={show(response_data.get('message', ''))}",
                f"row_count={len(rows)}",
            ]
        )
    )


def print_raw_row(bsns_year, report_code, fs_div, row):
    """Print raw row fields needed for LTM source selection."""
    fields = [
        ("bsns_year", bsns_year),
        ("report_code", report_code),
        ("report_label", REPORT_LABELS.get(report_code, report_code)),
        ("fs_div", fs_div),
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


def is_excluded_net_income_row(row):
    """Mirror current extraction's attribution-row exclusion for 당기순이익."""
    account_name = row.get("account_nm", "")

    for excluded_text in NET_INCOME_EXCLUDED_TEXTS:
        if excluded_text in account_name:
            return True

    return False


def find_account_candidates(rows, standard_account_name):
    """Find rows using current ACCOUNT_MAPPING account names and statement sections."""
    mapping = ACCOUNT_MAPPING[standard_account_name]
    candidates = []
    wrong_section_rows = []

    for sj_name in mapping["sj_names"]:
        for raw_account_name in mapping["account_names"]:
            for row in rows:
                account_matches = row.get("account_nm", "") == raw_account_name
                section_matches = row.get("sj_nm", "") == sj_name

                if not account_matches:
                    continue

                if not section_matches:
                    wrong_section_rows.append(row)
                    continue

                if standard_account_name == "당기순이익" and is_excluded_net_income_row(row):
                    continue

                candidates.append(row)

    return candidates, wrong_section_rows


def candidate_amounts(candidate_rows, field_name):
    """Return numeric amount values for ambiguity checks."""
    amounts = []

    for row in candidate_rows:
        amount = amount_to_int(row.get(field_name, ""))

        if amount is not None:
            amounts.append(amount)

    return amounts


def amounts_are_identical(candidate_rows, field_name):
    """Check whether all candidate numeric amounts are identical."""
    amounts = candidate_amounts(candidate_rows, field_name)

    if not amounts:
        return False

    return len(set(amounts)) == 1


def select_current_extraction_candidate(candidate_rows):
    """Select the first candidate, matching current extraction's mapping priority for diagnostics."""
    if not candidate_rows:
        return None

    return candidate_rows[0]


def inspect_standard_accounts(bsns_year, report_code, fs_div, response_data, issues):
    """Inspect standardized income statement account source rows."""
    print_section(f"Standard Account Source Rows: {bsns_year} {REPORT_LABELS.get(report_code, report_code)} {fs_div}")
    rows = get_rows(response_data)
    matches_by_account = {}

    for account_name in INCOME_ACCOUNTS:
        candidates, wrong_section_rows = find_account_candidates(rows, account_name)
        matches_by_account[account_name] = candidates
        print(f"\n{account_name}: {len(candidates)} matched row(s)")

        if not candidates:
            issues.append(f"{bsns_year} {report_code} {fs_div} {account_name}: unmatched account name")

            if wrong_section_rows:
                issues.append(f"{bsns_year} {report_code} {fs_div} {account_name}: statement-name mismatch")

            continue

        for row in candidates:
            print_raw_row(bsns_year, report_code, fs_div, row)

        if len(candidates) > 1:
            identical = amounts_are_identical(candidates, "thstrm_amount")
            print(f"multiple candidates: amounts identical={yes_no(identical)}")
            print("current extraction priority would select 손익계산서 first when both statements are present")

            if not identical:
                issues.append(f"{bsns_year} {report_code} {fs_div} {account_name}: multiple candidates with different amounts")

    return matches_by_account


def classify_net_income_candidate(row):
    """Classify a possible net income row."""
    account_name = row.get("account_nm", "")

    if "계속영업" in account_name:
        return "continuing-operations component"

    if "중단영업" in account_name:
        return "discontinued-operations component"

    if "비지배" in account_name:
        return "non-controlling interest attribution"

    if "지배기업" in account_name or "소유주" in account_name or "귀속" in account_name:
        return "parent-owner attribution"

    total_names = ACCOUNT_MAPPING["당기순이익"]["account_names"]

    if account_name in total_names:
        return "total net income"

    return "unclear"


def print_net_income_diagnostic(bsns_year, report_code, fs_div, response_data):
    """Print net income candidate rows from the selected latest interim report."""
    print_section(f"Net Income Candidate Diagnostic: {bsns_year} {REPORT_LABELS.get(report_code, report_code)} {fs_div}")
    rows = get_rows(response_data)
    found_any = False
    safe_candidates = []

    for row in rows:
        sj_nm = row.get("sj_nm", "")
        account_name = row.get("account_nm", "")

        if sj_nm not in ["손익계산서", "포괄손익계산서"]:
            continue

        if not any(keyword in account_name for keyword in NET_INCOME_KEYWORDS):
            continue

        found_any = True
        classification = classify_net_income_candidate(row)
        print(f"classification={classification}")
        print_raw_row(bsns_year, report_code, fs_div, row)

        if classification == "total net income":
            safe_candidates.append(row)

    if not found_any:
        print("No net income candidate rows found.")

    return safe_candidates


def find_latest_annual(api_key, corp_code, start_year, fs_div, issues):
    """Find latest valid annual report, starting from current calendar year."""
    print_section(f"Annual Report Search: {fs_div}")

    for year in range(start_year, start_year - 8, -1):
        bsns_year = str(year)
        report_code = "11011"
        response_data = safe_fetch_report(api_key, corp_code, bsns_year, report_code, fs_div, issues)
        print_availability(bsns_year, report_code, fs_div, response_data)

        if is_valid_response(response_data):
            print(f"Selected annual report: year={bsns_year} | fs_div={fs_div} | row_count={len(get_rows(response_data))}")
            return {
                "year": bsns_year,
                "report_code": report_code,
                "response": response_data,
            }

    issues.append(f"{fs_div}: no latest annual report found")
    return None


def find_latest_interim(api_key, corp_code, start_year, fs_div, issues):
    """Find latest valid interim report by year and report-code priority."""
    print_section(f"Interim Report Search: {fs_div}")

    for year in range(start_year, start_year - 8, -1):
        bsns_year = str(year)

        for report_code in INTERIM_REPORT_CODES:
            response_data = safe_fetch_report(api_key, corp_code, bsns_year, report_code, fs_div, issues)
            print_availability(bsns_year, report_code, fs_div, response_data)

            if is_valid_response(response_data):
                print("\nSelected latest interim report:")
                print(f"year={bsns_year}")
                print(f"report_code={report_code}")
                print(f"report_label={REPORT_LABELS.get(report_code, report_code)}")
                print(f"fs_div={fs_div}")
                return {
                    "year": bsns_year,
                    "report_code": report_code,
                    "response": response_data,
                }

    issues.append(f"{fs_div}: no latest interim report found")
    return None


def get_selected_row(matches_by_account, account_name):
    """Return selected diagnostic row for an account."""
    return select_current_extraction_candidate(matches_by_account.get(account_name, []))


def validate_ltm_sources(annual_report, interim_report, annual_matches, interim_matches, fs_div, issues):
    """Validate and calculate LTM source values for all income accounts."""
    print_section(f"Candidate LTM Calculations: {fs_div}")
    account_results = {}

    for account_name in INCOME_ACCOUNTS:
        annual_row = get_selected_row(annual_matches, account_name)
        interim_row = get_selected_row(interim_matches, account_name)

        if annual_row is None or interim_row is None:
            issues.append(f"{fs_div} {account_name}: missing source row")
            account_results[account_name] = False
            print(f"\n{account_name}: cannot calculate because a source row is missing")
            continue

        annual_amount = amount_to_int(annual_row.get("thstrm_amount", ""))
        current_interim_cumulative = amount_to_int(interim_row.get("thstrm_add_amount", ""))
        previous_same_period_cumulative = amount_to_int(interim_row.get("frmtrm_add_amount", ""))

        if annual_amount is None:
            issues.append(f"{fs_div} {account_name}: invalid numeric amount in annual thstrm_amount")

        if current_interim_cumulative is None:
            issues.append(f"{fs_div} {account_name}: missing thstrm_add_amount")

        if previous_same_period_cumulative is None:
            issues.append(f"{fs_div} {account_name}: missing frmtrm_add_amount")

        print(f"\n{account_name}:")
        print(f"annual_amount: {show(annual_amount)}")
        print(f"current_interim_cumulative: {show(current_interim_cumulative)}")
        print(f"previous_same_period_cumulative: {show(previous_same_period_cumulative)}")

        if annual_amount is None or current_interim_cumulative is None or previous_same_period_cumulative is None:
            print("ltm_amount: cannot calculate")
            account_results[account_name] = False
            continue

        ltm_amount = annual_amount + current_interim_cumulative - previous_same_period_cumulative
        print(f"ltm_amount: {ltm_amount}")
        account_results[account_name] = True

        annual_year = int(annual_report["year"])
        interim_year = int(interim_report["year"])

        if annual_year not in [interim_year - 1, interim_year]:
            issues.append(f"{fs_div} {account_name}: annual year inconsistent with interim comparison period")

    return account_results


def yes_no(value):
    """Return yes/no text."""
    return "yes" if value else "no"


def print_issues(issues):
    """Print all flagged issues."""
    print_section("Sanity Check Issues")

    if not issues:
        print("No issues flagged.")
        return

    for issue in issues:
        print(f"- {issue}")


def final_report_text(report):
    """Format selected report details for the final conclusion."""
    if report is None:
        return "not found"

    return f"year={report['year']} | report_code={report['report_code']} | report_label={REPORT_LABELS.get(report['report_code'], report['report_code'])}"


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

    current_year = datetime.now().year
    issues = []
    annual_reports = {}
    interim_reports = {}
    account_results = {}
    net_income_candidates = {}
    fs_ready = {}
    interim_search_selected_correctly = {}

    for fs_div in FS_DIVS:
        annual_reports[fs_div] = find_latest_annual(api_key, corp_code, current_year, fs_div, issues)
        interim_reports[fs_div] = find_latest_interim(api_key, corp_code, current_year, fs_div, issues)
        interim_search_selected_correctly[fs_div] = interim_reports[fs_div] is not None

        if annual_reports[fs_div] is None or interim_reports[fs_div] is None:
            account_results[fs_div] = {}
            net_income_candidates[fs_div] = []
            fs_ready[fs_div] = False
            continue

        annual_report = annual_reports[fs_div]
        interim_report = interim_reports[fs_div]

        annual_matches = inspect_standard_accounts(
            annual_report["year"],
            annual_report["report_code"],
            fs_div,
            annual_report["response"],
            issues,
        )
        interim_matches = inspect_standard_accounts(
            interim_report["year"],
            interim_report["report_code"],
            fs_div,
            interim_report["response"],
            issues,
        )
        net_income_candidates[fs_div] = print_net_income_diagnostic(
            interim_report["year"],
            interim_report["report_code"],
            fs_div,
            interim_report["response"],
        )
        account_results[fs_div] = validate_ltm_sources(
            annual_report,
            interim_report,
            annual_matches,
            interim_matches,
            fs_div,
            issues,
        )

        net_income_row = get_selected_row(interim_matches, "당기순이익")

        if net_income_row is None:
            issues.append(f"{fs_div}: total net income unavailable")
        else:
            classification = classify_net_income_candidate(net_income_row)

            if classification == "parent-owner attribution":
                issues.append(f"{fs_div}: attribution-only net income selected")
            elif classification in ["continuing-operations component", "discontinued-operations component"]:
                issues.append(f"{fs_div}: continuing or discontinued operations component selected as total")

        fs_ready[fs_div] = all(account_results[fs_div].get(account_name, False) for account_name in INCOME_ACCOUNTS)

    if annual_reports.get("CFS") and annual_reports.get("OFS"):
        cfs_interim = final_report_text(interim_reports.get("CFS"))
        ofs_interim = final_report_text(interim_reports.get("OFS"))

        if cfs_interim != ofs_interim:
            issues.append("CFS/OFS availability difference")

    print_issues(issues)
    print_final_conclusion(
        annual_reports,
        interim_reports,
        interim_search_selected_correctly,
        account_results,
        net_income_candidates,
        fs_ready,
        issues,
    )


def safe_net_income_name(candidates_by_fs_div):
    """Return a safe net income account name when one is consistently found."""
    safe_names = []

    for candidates in candidates_by_fs_div.values():
        for row in candidates:
            if classify_net_income_candidate(row) == "total net income":
                safe_names.append(row.get("account_nm", ""))

    unique_names = sorted(set(name for name in safe_names if name))

    if not unique_names:
        return BLANK_TEXT

    return ", ".join(unique_names)


def raw_net_income_name(candidates_by_fs_div, fs_div):
    """Return raw total net income account names for final conclusion."""
    names = []

    for row in candidates_by_fs_div.get(fs_div, []):
        if classify_net_income_candidate(row) == "total net income":
            names.append(row.get("account_nm", ""))

    unique_names = sorted(set(name for name in names if name))

    if not unique_names:
        return BLANK_TEXT

    return ", ".join(unique_names)


def account_mapping_change_required(candidates_by_fs_div):
    """Check whether a safe total net income candidate is absent from current ACCOUNT_MAPPING."""
    current_names = set(ACCOUNT_MAPPING["당기순이익"]["account_names"])

    for candidates in candidates_by_fs_div.values():
        for row in candidates:
            raw_name = row.get("account_nm", "")

            if classify_net_income_candidate(row) == "total net income" and raw_name not in current_names:
                return True

    return False


def print_final_conclusion(annual_reports, interim_reports, interim_search_selected_correctly, account_results, net_income_candidates, fs_ready, issues):
    """Print the required final conclusion structure."""
    print("\n=== Final Conclusion ===\n")
    print(f"CFS latest annual report: {final_report_text(annual_reports.get('CFS'))}")
    print(f"CFS latest interim report: {final_report_text(interim_reports.get('CFS'))}")
    print(f"CFS interim search selected correctly: {yes_no(interim_search_selected_correctly.get('CFS', False))}")
    print()
    print(f"OFS latest annual report: {final_report_text(annual_reports.get('OFS'))}")
    print(f"OFS latest interim report: {final_report_text(interim_reports.get('OFS'))}")
    print(f"OFS interim search selected correctly: {yes_no(interim_search_selected_correctly.get('OFS', False))}")
    print()
    print("Annual source field: thstrm_amount")
    print("Current interim cumulative source field: thstrm_add_amount")
    print("Previous-year same-period cumulative source field: frmtrm_add_amount")
    print()

    for account_name in INCOME_ACCOUNTS:
        validated = any(results.get(account_name, False) for results in account_results.values())
        print(f"LTM formula validated for {account_name}: {yes_no(validated)}")

    print()
    print(f"CFS total net income raw account: {raw_net_income_name(net_income_candidates, 'CFS')}")
    print(f"OFS total net income raw account: {raw_net_income_name(net_income_candidates, 'OFS')}")
    print(f"Safe net income candidate to add: {safe_net_income_name(net_income_candidates)}")
    print(f"ACCOUNT_MAPPING change required: {yes_no(account_mapping_change_required(net_income_candidates))}")
    print()
    print(f"CFS ready for LTM implementation: {yes_no(fs_ready.get('CFS', False))}")
    print(f"OFS ready for LTM implementation: {yes_no(fs_ready.get('OFS', False))}")
    print(f"Blocking issue remains: {yes_no(bool(issues))}")


if __name__ == "__main__":
    main()
