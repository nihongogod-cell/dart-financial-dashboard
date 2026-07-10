import json
from collections import defaultdict
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from extract_accounts import ACCOUNT_MAPPING, NET_INCOME_EXCLUDED_TEXTS
from fetch_financial_statement import COMPANY_LIST_PATH, build_request_url, find_corp_code, load_api_key


COMPANY_NAMES = ["삼성전자", "LG전자", "대한항공"]
FS_DIVS = ["CFS", "OFS"]
REPORT_CODE = "11011"
REPORT_LABEL = "사업보고서"
VALID_REPORT_COUNT = 5
STANDARD_ACCOUNTS = [
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
EXPECTED_ACCOUNT_IDS = {
    "자산총계": "ifrs-full_Assets",
    "부채총계": "ifrs-full_Liabilities",
    "자본총계": "ifrs-full_Equity",
    "매출액": "ifrs-full_Revenue",
    "매출원가": "ifrs-full_CostOfSales",
    "매출총이익": "ifrs-full_GrossProfit",
    "영업이익": "dart_OperatingIncomeLoss",
    "당기순이익": "ifrs-full_ProfitLoss",
    "영업활동현금흐름": "ifrs-full_CashFlowsFromUsedInOperatingActivities",
    "투자활동현금흐름": "ifrs-full_CashFlowsFromUsedInInvestingActivities",
    "재무활동현금흐름": "ifrs-full_CashFlowsFromUsedInFinancingActivities",
}
KOREAN_AIR_REVENUE_TERMS = ["매출", "수익", "영업수익", "운송수익"]
KOREAN_AIR_REVENUE_ID_TERMS = ["Revenue", "Sales", "OperatingRevenue"]
BLANK_TEXT = "<blank>"


def print_section(title):
    """Print a clear terminal section header."""
    print(f"\n=== {title} ===")


def show(value):
    """Show blank values explicitly."""
    if value is None or value == "":
        return BLANK_TEXT

    return str(value)


def amount_to_int(amount_text):
    """Convert an amount field to int, or return None."""
    if amount_text is None:
        return None

    cleaned_amount = str(amount_text).replace(",", "").strip()

    if not cleaned_amount:
        return None

    try:
        return int(cleaned_amount)
    except ValueError:
        return None


def fetch_report(api_key, corp_code, bsns_year, fs_div):
    """Fetch one annual report in memory only."""
    request_url = build_request_url(api_key, corp_code, bsns_year, REPORT_CODE, fs_div)

    with urlopen(request_url) as response:
        response_text = response.read().decode("utf-8")

    return json.loads(response_text)


def safe_fetch_report(api_key, corp_code, bsns_year, fs_div):
    """Fetch one report safely and continue after errors."""
    try:
        return fetch_report(api_key, corp_code, bsns_year, fs_div)
    except json.JSONDecodeError as error:
        print(f"{bsns_year} {fs_div}: JSON error - {error}")
    except HTTPError as error:
        print(f"{bsns_year} {fs_div}: HTTP error - {error.code}")
    except URLError as error:
        print(f"{bsns_year} {fs_div}: network error - {error.reason}")
    except OSError as error:
        print(f"{bsns_year} {fs_div}: connection error - {error}")

    return {"status": "", "message": "", "list": []}


def get_rows(response_data):
    """Return report rows safely."""
    rows = response_data.get("list", [])

    if rows is None:
        return []

    return rows


def is_valid_report(response_data):
    """Return True when a DART response has usable rows."""
    return response_data.get("status") == "000" and bool(get_rows(response_data))


def print_availability(company_name, year, fs_div, response_data):
    """Print one compact availability check."""
    print(
        " | ".join(
            [
                f"company={company_name}",
                f"bsns_year={year}",
                f"report_code={REPORT_CODE}",
                f"report_label={REPORT_LABEL}",
                f"fs_div={fs_div}",
                f"status={show(response_data.get('status', ''))}",
                f"message={show(response_data.get('message', ''))}",
                f"row_count={len(get_rows(response_data))}",
            ]
        )
    )


def find_recent_valid_reports(api_key, company_name, corp_code, fs_div):
    """Find recent 5 valid annual reports for one company and fs_div."""
    print_section(f"Availability: {company_name} {fs_div}")
    current_year = datetime.now().year
    reports = []

    for year in range(current_year, current_year - 12, -1):
        response_data = safe_fetch_report(api_key, corp_code, str(year), fs_div)
        print_availability(company_name, year, fs_div, response_data)

        if is_valid_report(response_data):
            reports.append(
                {
                    "company": company_name,
                    "corp_code": corp_code,
                    "year": str(year),
                    "fs_div": fs_div,
                    "response": response_data,
                }
            )

        if len(reports) == VALID_REPORT_COUNT:
            break

    return reports


def excluded_by_net_income_rule(standard_account, row):
    """Apply the current net-income exclusion keyword behavior."""
    if standard_account != "당기순이익":
        return False

    account_name = row.get("account_nm", "")

    for excluded_text in NET_INCOME_EXCLUDED_TEXTS:
        if excluded_text in account_name:
            return True

    return False


def valid_amount_rows(rows):
    """Keep rows with numeric thstrm_amount."""
    return [row for row in rows if amount_to_int(row.get("thstrm_amount", "")) is not None]


def prefer_non_zero(rows):
    """Prefer rows with non-zero amount, otherwise the first valid row."""
    valid_rows = valid_amount_rows(rows)

    if not valid_rows:
        return None

    for row in valid_rows:
        if amount_to_int(row.get("thstrm_amount", "")) != 0:
            return row

    return valid_rows[0]


def find_name_based_row(rows, standard_account):
    """Simulate current ACCOUNT_MAPPING name-based matching."""
    mapping = ACCOUNT_MAPPING[standard_account]

    for sj_name in mapping["sj_names"]:
        for account_name in mapping["account_names"]:
            candidates = []

            for row in rows:
                if row.get("account_nm", "") != account_name:
                    continue

                if row.get("sj_nm", "") != sj_name:
                    continue

                if excluded_by_net_income_rule(standard_account, row):
                    continue

                candidates.append(row)

            selected_row = prefer_non_zero(candidates)

            if selected_row is not None:
                return selected_row, candidates

    return None, []


def find_account_id_rows(rows, standard_account):
    """Find rows by expected account_id and allowed statement sections."""
    expected_account_id = EXPECTED_ACCOUNT_IDS[standard_account]
    mapping = ACCOUNT_MAPPING[standard_account]

    for sj_name in mapping["sj_names"]:
        candidates = []

        for row in rows:
            if row.get("account_id", "") != expected_account_id:
                continue

            if row.get("sj_nm", "") != sj_name:
                continue

            if excluded_by_net_income_rule(standard_account, row):
                continue

            candidates.append(row)

        if candidates:
            selected_row = prefer_non_zero(candidates)
            return selected_row, candidates

    return None, []


def same_economic_amount(name_row, account_id_row):
    """Check whether two rows have the same numeric amount."""
    if name_row is None or account_id_row is None:
        return False

    return amount_to_int(name_row.get("thstrm_amount", "")) == amount_to_int(account_id_row.get("thstrm_amount", ""))


def same_row(name_row, account_id_row):
    """Check whether two selected rows appear to be the same raw row."""
    if name_row is None or account_id_row is None:
        return False

    return (
        name_row.get("sj_nm", ""),
        name_row.get("account_nm", ""),
        name_row.get("account_id", ""),
        name_row.get("ord", ""),
    ) == (
        account_id_row.get("sj_nm", ""),
        account_id_row.get("account_nm", ""),
        account_id_row.get("account_id", ""),
        account_id_row.get("ord", ""),
    )


def candidate_amount_status(candidates):
    """Classify multiple account_id candidates by amount equality."""
    if len(candidates) <= 1:
        return ""

    amounts = [amount_to_int(row.get("thstrm_amount", "")) for row in candidates]
    amounts = [amount for amount in amounts if amount is not None]

    if len(set(amounts)) <= 1:
        return "multiple account_id candidates with same amount"

    return "multiple account_id candidates with different amounts"


def classify_result(name_row, account_id_row, account_id_candidates):
    """Classify one account/report comparison."""
    multiple_status = candidate_amount_status(account_id_candidates)

    if multiple_status:
        return multiple_status

    if name_row is not None and account_id_row is not None:
        if same_row(name_row, account_id_row):
            return "both match same row"

        if same_economic_amount(name_row, account_id_row):
            return "both match same economic amount but different row"

        return "multiple account_id candidates with different amounts"

    if account_id_row is not None and name_row is None:
        return "account_id match succeeds, name match fails"

    if name_row is not None and account_id_row is None:
        return "name match succeeds, account_id match fails"

    return "both fail"


def row_value(row, field_name):
    """Return a display value from a possibly missing row."""
    if row is None:
        return BLANK_TEXT

    return show(row.get(field_name, ""))


def print_match_result(report, standard_account, name_row, account_id_row, classification):
    """Print one exact matched-row comparison."""
    print(
        " | ".join(
            [
                f"company={report['company']}",
                f"corp_code={report['corp_code']}",
                f"year={report['year']}",
                f"fs_div={report['fs_div']}",
                f"standardized_account={standard_account}",
                f"current name-based match={'yes' if name_row is not None else 'no'}",
                f"current matched account_nm={row_value(name_row, 'account_nm')}",
                f"current matched account_id={row_value(name_row, 'account_id')}",
                f"account_id-based match={'yes' if account_id_row is not None else 'no'}",
                f"account_id matched account_nm={row_value(account_id_row, 'account_nm')}",
                f"account_id matched account_id={row_value(account_id_row, 'account_id')}",
                f"sj_nm={row_value(account_id_row or name_row, 'sj_nm')}",
                f"thstrm_amount={row_value(account_id_row or name_row, 'thstrm_amount')}",
                f"ord={row_value(account_id_row or name_row, 'ord')}",
                f"classification={classification}",
            ]
        )
    )


def update_observed_summary(summary, report, standard_account, name_row, account_id_row, classification):
    """Collect observed account_id stats."""
    observed_row = account_id_row or name_row

    if observed_row is not None:
        account_id = observed_row.get("account_id", "")

        if account_id:
            summary[standard_account]["observed_ids"][account_id]["companies"].add(report["company"])
            summary[standard_account]["observed_ids"][account_id]["years"].add(report["year"])

    if name_row is None:
        summary[standard_account]["name_failures"] += 1

    if account_id_row is None:
        summary[standard_account]["account_id_failures"] += 1

    summary[standard_account]["classifications"].append(classification)


def inspect_report_accounts(report, summary):
    """Inspect all standardized accounts for one report."""
    rows = get_rows(report["response"])

    for standard_account in STANDARD_ACCOUNTS:
        name_row, _name_candidates = find_name_based_row(rows, standard_account)
        account_id_row, account_id_candidates = find_account_id_rows(rows, standard_account)
        classification = classify_result(name_row, account_id_row, account_id_candidates)
        print_match_result(report, standard_account, name_row, account_id_row, classification)
        update_observed_summary(summary, report, standard_account, name_row, account_id_row, classification)


def revenue_row_matches(row):
    """Find 대한항공 revenue-related rows."""
    account_name = row.get("account_nm", "")
    account_id = row.get("account_id", "")
    name_matches = any(term in account_name for term in KOREAN_AIR_REVENUE_TERMS)
    id_matches = any(term in account_id for term in KOREAN_AIR_REVENUE_ID_TERMS)
    return name_matches or id_matches


def print_korean_air_revenue_focus(all_reports):
    """Print focused revenue diagnostics for 대한항공."""
    print_section("대한항공 매출액 Focus")
    causes = []

    for report in all_reports:
        if report["company"] != "대한항공":
            continue

        rows = get_rows(report["response"])
        print(f"\n대한항공 {report['year']} {report['fs_div']}")

        for row in rows:
            if not revenue_row_matches(row):
                continue

            print(
                " | ".join(
                    [
                        f"year={report['year']}",
                        f"fs_div={report['fs_div']}",
                        f"sj_nm={show(row.get('sj_nm', ''))}",
                        f"account_nm={show(row.get('account_nm', ''))}",
                        f"account_id={show(row.get('account_id', ''))}",
                        f"thstrm_amount={show(row.get('thstrm_amount', ''))}",
                        f"ord={show(row.get('ord', ''))}",
                    ]
                )
            )

        name_row, _ = find_name_based_row(rows, "매출액")
        account_id_row, _ = find_account_id_rows(rows, "매출액")

        if name_row is None and account_id_row is not None:
            causes.append("some years have ifrs-full_Revenue but Korean account name does not match current candidates")
        elif name_row is not None and account_id_row is None:
            causes.append("some years use another standard or company-specific revenue account_id")
        elif name_row is None and account_id_row is None:
            causes.append("some years need further revenue account investigation")

    if not causes:
        print("\n대한항공 root cause: current name and expected account_id matching both cover inspected revenue rows.")
    else:
        print(f"\n대한항공 root cause: {'; '.join(sorted(set(causes)))}")

    return "; ".join(sorted(set(causes))) if causes else "no blocking revenue mismatch found"


def format_observed_ids(observed_ids):
    """Format observed account_ids."""
    if not observed_ids:
        return BLANK_TEXT

    return ", ".join(sorted(observed_ids.keys()))


def format_id_usage(observed_ids, field_name):
    """Format companies or years by observed account_id."""
    if not observed_ids:
        return BLANK_TEXT

    parts = []

    for account_id, usage in sorted(observed_ids.items()):
        parts.append(f"{account_id}: {', '.join(sorted(usage[field_name]))}")

    return " | ".join(parts)


def safe_for_account_id_first(account_summary):
    """Decide whether account_id-first looks safe in this diagnostic."""
    classifications = account_summary["classifications"]
    has_account_id_success = any(
        classification in [
            "both match same row",
            "both match same economic amount but different row",
            "account_id match succeeds, name match fails",
            "multiple account_id candidates with same amount",
        ]
        for classification in classifications
    )
    has_different_amounts = "multiple account_id candidates with different amounts" in classifications
    return has_account_id_success and not has_different_amounts


def fallback_needed(account_summary):
    """Decide whether name fallback is still needed."""
    return account_summary["account_id_failures"] > 0


def recommended_strategy(account_summary):
    """Recommend a migration strategy for one account."""
    account_id_safe = safe_for_account_id_first(account_summary)
    needs_fallback = fallback_needed(account_summary)

    if account_id_safe and needs_fallback:
        return "A. account_id primary, account_nm fallback"

    if account_id_safe and not needs_fallback:
        return "C. account_id only"

    if not account_id_safe and account_summary["name_failures"] == 0:
        return "B. account_nm primary, account_id secondary"

    return "D. unresolved, more investigation required"


def blocking_issue(account_summary):
    """Return blocking issue text for one account."""
    classifications = set(account_summary["classifications"])

    if "multiple account_id candidates with different amounts" in classifications:
        return "multiple account_id candidates with different amounts"

    if "both fail" in classifications:
        return "both matching approaches fail in at least one report"

    return "none"


def print_summary_table(summary):
    """Print observed account_id summary table."""
    print_section("Observed Account ID Summary")

    for account in STANDARD_ACCOUNTS:
        account_summary = summary[account]
        observed_ids = account_summary["observed_ids"]
        account_id_safe = safe_for_account_id_first(account_summary)
        needs_fallback = fallback_needed(account_summary)

        print(
            " | ".join(
                [
                    f"standardized_account={account}",
                    f"expected_account_id={EXPECTED_ACCOUNT_IDS[account]}",
                    f"observed_account_ids={format_observed_ids(observed_ids)}",
                    f"companies_using_each_id={format_id_usage(observed_ids, 'companies')}",
                    f"years_using_each_id={format_id_usage(observed_ids, 'years')}",
                    f"name-based failures={account_summary['name_failures']}",
                    f"account_id-based failures={account_summary['account_id_failures']}",
                    f"safe_for_primary_account_id_matching={'yes' if account_id_safe else 'no'}",
                    f"fallback_name_matching_still_needed={'yes' if needs_fallback else 'no'}",
                ]
            )
        )


def print_final_conclusion(summary, korean_air_root_cause):
    """Print the requested final conclusion."""
    print("\n=== Final Conclusion ===\n")
    accounts_requiring_fallback = []
    blocking_accounts = []

    for account in STANDARD_ACCOUNTS:
        account_summary = summary[account]
        strategy = recommended_strategy(account_summary)
        needs_fallback = fallback_needed(account_summary)
        issue = blocking_issue(account_summary)

        if needs_fallback:
            accounts_requiring_fallback.append(account)

        if issue != "none":
            blocking_accounts.append(account)

        print(f"{account}:")
        print(f"recommended strategy: {strategy}")
        print(f"primary account_id: {EXPECTED_ACCOUNT_IDS[account]}")

        if account == "매출액":
            observed_ids = set(account_summary["observed_ids"].keys())
            alternate_ids = sorted(observed_ids - {EXPECTED_ACCOUNT_IDS[account]})
            print(f"observed alternate account_ids: {', '.join(alternate_ids) if alternate_ids else BLANK_TEXT}")
            print(f"fallback required: {'yes' if needs_fallback else 'no'}")
            print(f"대한항공 root cause: {korean_air_root_cause}")
        else:
            print(f"fallback required: {'yes' if needs_fallback else 'no'}")

        print(f"blocking issue: {issue}")
        print()

    overall_strategy = "account_id primary, account_nm fallback where diagnostics show account_id gaps"
    safe_now = not blocking_accounts
    print(f"Overall recommended extraction strategy: {overall_strategy}")
    print(f"Safe to implement account_id-first matching now: {'yes' if safe_now else 'no'}")
    print(
        "Accounts requiring extra fallback rules: "
        f"{', '.join(accounts_requiring_fallback) if accounts_requiring_fallback else BLANK_TEXT}"
    )
    print(f"Blocking issue remains: {'yes' if blocking_accounts else 'no'}")


def create_summary():
    """Create nested summary state."""
    summary = {}

    for account in STANDARD_ACCOUNTS:
        summary[account] = {
            "observed_ids": defaultdict(lambda: {"companies": set(), "years": set()}),
            "name_failures": 0,
            "account_id_failures": 0,
            "classifications": [],
        }

    return summary


def main():
    print_section("Setup")
    api_key = load_api_key()

    if not api_key:
        print("Failure: DART_API_KEY was not found in the project root .env file.")
        return

    summary = create_summary()
    all_reports = []

    for company_name in COMPANY_NAMES:
        corp_code = find_corp_code(COMPANY_LIST_PATH, company_name)

        if not corp_code:
            print(f"Could not find corp_code for {company_name}")
            continue

        for fs_div in FS_DIVS:
            reports = find_recent_valid_reports(api_key, company_name, corp_code, fs_div)
            all_reports.extend(reports)

    print_section("Account Matching Results")

    for report in all_reports:
        inspect_report_accounts(report, summary)

    korean_air_root_cause = print_korean_air_revenue_focus(all_reports)
    print_summary_table(summary)
    print_final_conclusion(summary, korean_air_root_cause)


if __name__ == "__main__":
    main()
