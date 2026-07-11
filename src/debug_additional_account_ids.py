import json
from collections import defaultdict
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from fetch_financial_statement import (
    COMPANY_LIST_PATH,
    build_request_url,
    find_corp_code,
    load_api_key,
)


TEST_COMPANIES = ["삼성전자", "LG전자", "대한항공"]
FS_DIVS = ["CFS", "OFS"]
REPORT_CODE = "11011"
VALID_REPORT_COUNT = 5
BLANK_TEXT = "<blank>"

ADDITIONAL_ACCOUNTS = [
    {
        "name": "유동자산",
        "account_ids": ["ifrs-full_CurrentAssets"],
        "keywords": ["유동자산"],
        "sj_names": ["재무상태표"],
    },
    {
        "name": "비유동자산",
        "account_ids": ["ifrs-full_NoncurrentAssets"],
        "keywords": ["비유동자산"],
        "sj_names": ["재무상태표"],
    },
    {
        "name": "현금및현금성자산",
        "account_ids": ["ifrs-full_CashAndCashEquivalents"],
        "keywords": ["현금및현금성자산", "현금 및 현금성자산"],
        "sj_names": ["재무상태표"],
    },
    {
        "name": "매출채권",
        "account_ids": [
            "ifrs-full_TradeReceivables",
            "ifrs-full_TradeAndOtherCurrentReceivables",
        ],
        "keywords": ["매출채권", "매출채권및기타채권", "매출채권 및 기타채권", "매출채권과기타채권"],
        "sj_names": ["재무상태표"],
    },
    {
        "name": "재고자산",
        "account_ids": ["ifrs-full_Inventories"],
        "keywords": ["재고자산", "재고자산합계"],
        "sj_names": ["재무상태표"],
    },
    {
        "name": "유형자산",
        "account_ids": ["ifrs-full_PropertyPlantAndEquipment"],
        "keywords": ["유형자산"],
        "sj_names": ["재무상태표"],
    },
    {
        "name": "무형자산",
        "account_ids": [
            "ifrs-full_IntangibleAssetsOtherThanGoodwill",
            "ifrs-full_IntangibleAssetsAndGoodwill",
        ],
        "keywords": ["무형자산", "영업권및무형자산", "영업권 및 무형자산"],
        "sj_names": ["재무상태표"],
    },
    {
        "name": "유동부채",
        "account_ids": ["ifrs-full_CurrentLiabilities"],
        "keywords": ["유동부채"],
        "sj_names": ["재무상태표"],
    },
    {
        "name": "비유동부채",
        "account_ids": ["ifrs-full_NoncurrentLiabilities"],
        "keywords": ["비유동부채"],
        "sj_names": ["재무상태표"],
    },
    {
        "name": "이익잉여금",
        "account_ids": ["ifrs-full_RetainedEarnings"],
        "keywords": ["이익잉여금", "이익잉여금(결손금)", "결손금"],
        "sj_names": ["재무상태표"],
    },
    {
        "name": "판매비와 관리비",
        "account_ids": [
            "dart_TotalSellingGeneralAdministrativeExpenses",
            "dart_SellingGeneralAdministrativeExpenses",
        ],
        "keywords": ["판매비와관리비", "판매비와 관리비", "판매관리비", "판매비및관리비", "판매비 및 관리비", "판관비"],
        "sj_names": ["손익계산서", "포괄손익계산서"],
    },
]


def display_value(value):
    """Return a printable value, replacing blanks with <blank>."""
    if value is None:
        return BLANK_TEXT

    value_text = str(value)

    if not value_text:
        return BLANK_TEXT

    return value_text


def print_section(title):
    """Print a clear terminal section header."""
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def fetch_dart_response(api_key, corp_code, bsns_year, fs_div):
    """Fetch one annual DART response in memory without saving it."""
    request_url = build_request_url(api_key, corp_code, str(bsns_year), REPORT_CODE, fs_div)

    with urlopen(request_url) as response:
        response_text = response.read().decode("utf-8")

    return json.loads(response_text)


def response_has_valid_rows(response_data):
    """Return True when the DART response contains usable financial rows."""
    return response_data.get("status") == "000" and bool(response_data.get("list", []))


def collect_recent_valid_reports(api_key, company_name, corp_code, fs_div):
    """Collect recent valid annual reports for one company and statement type."""
    valid_reports = []
    current_year = datetime.now().year

    for year in range(current_year, current_year - 10, -1):
        if len(valid_reports) >= VALID_REPORT_COUNT:
            break

        try:
            response_data = fetch_dart_response(api_key, corp_code, year, fs_div)
            status = response_data.get("status", "")
            message = response_data.get("message", "")
            row_count = len(response_data.get("list", []))
            print(f"{company_name} {fs_div} {year}: status={status}, rows={row_count}, message={message}")

            if response_has_valid_rows(response_data):
                valid_reports.append(
                    {
                        "company": company_name,
                        "corp_code": corp_code,
                        "year": str(year),
                        "fs_div": fs_div,
                        "response": response_data,
                    }
                )
        except HTTPError as error:
            print(f"{company_name} {fs_div} {year}: HTTP error {error.code}")
        except URLError as error:
            print(f"{company_name} {fs_div} {year}: URL error {error.reason}")
        except json.JSONDecodeError as error:
            print(f"{company_name} {fs_div} {year}: JSON decode error {error}")
        except OSError as error:
            print(f"{company_name} {fs_div} {year}: OS error {error}")

    return valid_reports


def row_has_keyword(account_name, keywords):
    """Check whether account_nm contains any candidate keyword."""
    for keyword in keywords:
        if keyword in account_name:
            return True

    return False


def row_matches_account(row, account_config):
    """Find candidate rows by hypothesized account_id or Korean account_nm keyword."""
    account_id = row.get("account_id", "")
    account_name = row.get("account_nm", "")
    section_name = row.get("sj_nm", "")

    if section_name not in account_config["sj_names"]:
        return False

    if account_id in account_config["account_ids"]:
        return True

    if row_has_keyword(account_name, account_config["keywords"]):
        return True

    return False


def classify_semantic_scope(standardized_account, row):
    """Classify obvious total/component or combined-account semantic cases."""
    account_id = row.get("account_id", "")
    account_name = row.get("account_nm", "")

    if standardized_account == "매출채권":
        if account_id == "ifrs-full_TradeReceivables" or account_name == "매출채권":
            return "pure trade receivables"
        if "Other" in account_id or "기타" in account_name:
            return "combined trade and other receivables"
        return "receivable candidate, scope needs review"

    if standardized_account == "무형자산":
        if account_id == "ifrs-full_IntangibleAssetsOtherThanGoodwill":
            return "intangible assets excluding goodwill"
        if "Goodwill" in account_id or "영업권" in account_name:
            return "goodwill plus intangible assets"
        return "intangible candidate, scope needs review"

    if standardized_account == "판매비와 관리비":
        if account_id in [
            "dart_TotalSellingGeneralAdministrativeExpenses",
            "dart_SellingGeneralAdministrativeExpenses",
        ]:
            return "total SG&A"
        if row_has_keyword(account_name, ["판매비와관리비", "판매비와 관리비", "판매관리비", "판매비및관리비", "판매비 및 관리비", "판관비"]):
            return "SG&A name candidate, total needs review"
        return "component risk"

    if standardized_account == "이익잉여금":
        if row_has_keyword(account_name, ["미처분", "처분", "적립금"]):
            return "retained earnings sub-component risk"
        return "retained earnings total candidate"

    return "total candidate"


def make_case_key(report):
    """Build a compact key for a company/year/fs_div report case."""
    return f"{report['company']} {report['year']} {report['fs_div']}"


def print_candidate_row(report, account_config, row):
    """Print one exact candidate row."""
    print(
        " | ".join(
            [
                f"company={display_value(report['company'])}",
                f"corp_code={display_value(report['corp_code'])}",
                f"year={display_value(report['year'])}",
                f"fs_div={display_value(report['fs_div'])}",
                f"standardized_account={display_value(account_config['name'])}",
                f"sj_nm={display_value(row.get('sj_nm', ''))}",
                f"account_nm={display_value(row.get('account_nm', ''))}",
                f"account_id={display_value(row.get('account_id', ''))}",
                f"thstrm_amount={display_value(row.get('thstrm_amount', ''))}",
                f"ord={display_value(row.get('ord', ''))}",
                f"semantic_scope={classify_semantic_scope(account_config['name'], row)}",
            ]
        )
    )


def inspect_reports(valid_reports):
    """Inspect all reports and aggregate observed account_id mapping evidence."""
    results = {}

    for account_config in ADDITIONAL_ACCOUNTS:
        account_name = account_config["name"]
        results[account_name] = {
            "config": account_config,
            "rows": [],
            "missing_cases": [],
        }

    print_section("Exact Candidate Rows")

    for report in valid_reports:
        rows = report["response"].get("list", [])

        for account_config in ADDITIONAL_ACCOUNTS:
            matching_rows = []

            for row in rows:
                if row_matches_account(row, account_config):
                    matching_rows.append(row)

            if not matching_rows:
                results[account_config["name"]]["missing_cases"].append(make_case_key(report))
                continue

            for row in matching_rows:
                result_row = {
                    "company": report["company"],
                    "corp_code": report["corp_code"],
                    "year": report["year"],
                    "fs_div": report["fs_div"],
                    "row": row,
                    "semantic_scope": classify_semantic_scope(account_config["name"], row),
                }
                results[account_config["name"]]["rows"].append(result_row)
                print_candidate_row(report, account_config, row)

    return results


def unique_sorted(values):
    """Return unique non-empty values in sorted order."""
    clean_values = []

    for value in values:
        value_text = str(value).strip()

        if value_text:
            clean_values.append(value_text)

    return sorted(set(clean_values))


def summarize_account(account_name, result):
    """Build a compact mapping summary for one standardized account."""
    config = result["config"]
    rows = result["rows"]
    observed_ids = unique_sorted(row_data["row"].get("account_id", "") for row_data in rows)
    observed_names = unique_sorted(row_data["row"].get("account_nm", "") for row_data in rows)
    company_usage = defaultdict(set)
    year_usage = defaultdict(set)
    fs_div_usage = defaultdict(set)
    semantic_scopes = unique_sorted(row_data["semantic_scope"] for row_data in rows)

    for row_data in rows:
        account_id = row_data["row"].get("account_id", "")
        company_usage[account_id].add(row_data["company"])
        year_usage[account_id].add(row_data["year"])
        fs_div_usage[account_id].add(row_data["fs_div"])

    primary_ids = [account_id for account_id in config["account_ids"] if account_id in observed_ids]
    alternate_ids = [account_id for account_id in observed_ids if account_id not in primary_ids]
    company_extension_ids = [
        account_id
        for account_id in observed_ids
        if account_id not in config["account_ids"] and account_id != "-표준계정코드 미사용-"
    ]
    has_unmapped_code = "-표준계정코드 미사용-" in observed_ids
    has_missing_cases = bool(result["missing_cases"])
    has_semantic_ambiguity = any(
        scope not in ["total candidate", "total SG&A", "retained earnings total candidate"]
        for scope in semantic_scopes
    )
    safe_to_add_now = bool(primary_ids) and not has_missing_cases and not has_semantic_ambiguity

    return {
        "standardized_account": account_name,
        "recommended_primary_account_ids": primary_ids,
        "observed_alternate_account_ids": alternate_ids,
        "safe_account_nm_fallback_candidates": observed_names,
        "name_variations": observed_names,
        "missing_cases": result["missing_cases"],
        "semantic_ambiguity": semantic_scopes,
        "safe_to_add_now": "yes" if safe_to_add_now else "no",
        "company_extension_ids": company_extension_ids,
        "has_unmapped_code": has_unmapped_code,
        "company_usage": company_usage,
        "year_usage": year_usage,
        "fs_div_usage": fs_div_usage,
    }


def print_summary_table(results):
    """Print summary evidence for all accounts."""
    summaries = {}
    print_section("Summary Table")
    print(
        "standardized_account | recommended_primary_account_ids | observed_alternate_account_ids | "
        "safe_account_nm_fallback_candidates | name_variations | missing_cases | "
        "semantic_ambiguity | safe_to_add_now"
    )

    for account_name, result in results.items():
        summary = summarize_account(account_name, result)
        summaries[account_name] = summary
        print(
            " | ".join(
                [
                    summary["standardized_account"],
                    ", ".join(summary["recommended_primary_account_ids"]) or BLANK_TEXT,
                    ", ".join(summary["observed_alternate_account_ids"]) or BLANK_TEXT,
                    ", ".join(summary["safe_account_nm_fallback_candidates"]) or BLANK_TEXT,
                    ", ".join(summary["name_variations"]) or BLANK_TEXT,
                    "; ".join(summary["missing_cases"]) or BLANK_TEXT,
                    ", ".join(summary["semantic_ambiguity"]) or BLANK_TEXT,
                    summary["safe_to_add_now"],
                ]
            )
        )

    return summaries


def print_account_id_stability(summaries):
    """Print companies, years, CFS/OFS usage, extensions, and unmapped-code cases."""
    print_section("Account ID Stability Details")

    for account_name, summary in summaries.items():
        print(f"\n[{account_name}]")

        all_ids = summary["recommended_primary_account_ids"] + summary["observed_alternate_account_ids"]

        if not all_ids:
            print("No observed account_id values.")
            continue

        for account_id in all_ids:
            companies = ", ".join(sorted(summary["company_usage"][account_id])) or BLANK_TEXT
            years = ", ".join(sorted(summary["year_usage"][account_id])) or BLANK_TEXT
            fs_divs = ", ".join(sorted(summary["fs_div_usage"][account_id])) or BLANK_TEXT
            print(f"{account_id}: companies={companies}; years={years}; fs_divs={fs_divs}")

        if summary["company_extension_ids"]:
            print(f"company-extension IDs: {', '.join(summary['company_extension_ids'])}")

        print(f'uses "-표준계정코드 미사용-": {"yes" if summary["has_unmapped_code"] else "no"}')


def print_focus_sections(results):
    """Print dedicated semantic-review sections for ambiguous account families."""
    focus_accounts = ["매출채권", "무형자산", "판매비와 관리비"]

    for account_name in focus_accounts:
        print_section(f"Focus Section: {account_name}")
        rows = results[account_name]["rows"]

        if not rows:
            print("No candidate rows found.")
            continue

        grouped_rows = defaultdict(list)

        for row_data in rows:
            grouped_rows[row_data["semantic_scope"]].append(row_data)

        for semantic_scope, scoped_rows in grouped_rows.items():
            print(f"\n{semantic_scope}")

            for row_data in scoped_rows:
                row = row_data["row"]
                print(
                    f"{row_data['company']} {row_data['year']} {row_data['fs_div']} | "
                    f"sj_nm={display_value(row.get('sj_nm', ''))} | "
                    f"account_nm={display_value(row.get('account_nm', ''))} | "
                    f"account_id={display_value(row.get('account_id', ''))} | "
                    f"amount={display_value(row.get('thstrm_amount', ''))}"
                )


def print_recommended_production_mapping(summaries):
    """Print a recommended mapping block without modifying production code."""
    print_section("Recommended Production Mapping")

    for account_name, summary in summaries.items():
        print(f"\n{account_name}:")
        print(f"  account_ids: {summary['recommended_primary_account_ids'] or []}")
        print(f"  account_names fallback: {summary['safe_account_nm_fallback_candidates'] or []}")

        if account_name == "판매비와 관리비":
            print("  sj_names: ['손익계산서', '포괄손익계산서']")
        else:
            print("  sj_names: ['재무상태표']")

        print("  special exclusion logic required: no")

        if account_name == "매출채권" and "combined trade and other receivables" in summary["semantic_ambiguity"]:
            print("  display label review: consider 매출채권및기타채권 if only combined concepts are stable")
        elif account_name == "무형자산" and "goodwill plus intangible assets" in summary["semantic_ambiguity"]:
            print("  display label review: consider 영업권및무형자산 if combined concepts are stable")
        else:
            print("  display label review: current label likely acceptable if safe_to_add_now is yes")


def format_final_list(values):
    """Format final conclusion list values."""
    if not values:
        return BLANK_TEXT

    return ", ".join(values)


def print_final_conclusion(summaries):
    """Print the exact requested final conclusion template."""
    safe_accounts = []
    scope_adjustment_accounts = []
    more_investigation_accounts = []

    for account_name, summary in summaries.items():
        if summary["safe_to_add_now"] == "yes":
            safe_accounts.append(account_name)
        elif summary["semantic_ambiguity"]:
            scope_adjustment_accounts.append(account_name)
        else:
            more_investigation_accounts.append(account_name)

    print()
    print("=== Final Conclusion ===")

    for account_name in [
        "유동자산",
        "비유동자산",
        "현금및현금성자산",
        "매출채권",
        "재고자산",
        "유형자산",
        "무형자산",
        "유동부채",
        "비유동부채",
        "이익잉여금",
        "판매비와 관리비",
    ]:
        summary = summaries[account_name]
        print()
        print(f"{account_name}:")
        print(f"primary account_ids: {format_final_list(summary['recommended_primary_account_ids'])}")
        print(f"fallback account_names: {format_final_list(summary['safe_account_nm_fallback_candidates'])}")

        if account_name in ["매출채권", "무형자산"]:
            print(f"semantic scope: {format_final_list(summary['semantic_ambiguity'])}")

        print(f"safe to implement: {summary['safe_to_add_now']}")

        blocking_issues = []

        if summary["missing_cases"]:
            blocking_issues.append("missing cases")

        if summary["semantic_ambiguity"]:
            blocking_issues.append("semantic ambiguity")

        if not summary["recommended_primary_account_ids"]:
            blocking_issues.append("no confirmed primary account_id")

        print(f"blocking issue: {', '.join(blocking_issues) if blocking_issues else 'none'}")

    print()
    print(f"Accounts safe to add immediately: {format_final_list(safe_accounts)}")
    print(f"Accounts requiring naming or scope adjustment: {format_final_list(scope_adjustment_accounts)}")
    print(f"Accounts requiring more investigation: {format_final_list(more_investigation_accounts)}")
    print(f"Safe to proceed with UI category redesign: {'yes' if not more_investigation_accounts else 'no'}")
    print(f"Blocking issue remains: {'yes' if scope_adjustment_accounts or more_investigation_accounts else 'no'}")


def main():
    print_section("Read-Only Diagnostic: Additional XBRL Account IDs")
    print("This script makes API GET requests only and does not write CSV, JSON, or application files.")

    api_key = load_api_key()

    if not api_key:
        print("Failure: DART_API_KEY was not found in the project root .env file.")
        return

    all_reports = []

    print_section("Collect Recent 5 Valid Annual Reports")

    for company_name in TEST_COMPANIES:
        corp_code = find_corp_code(COMPANY_LIST_PATH, company_name)

        if not corp_code:
            print(f'Could not find corp_code for "{company_name}". Continuing.')
            continue

        for fs_div in FS_DIVS:
            reports = collect_recent_valid_reports(api_key, company_name, corp_code, fs_div)
            all_reports.extend(reports)

    if not all_reports:
        print("No valid reports were collected. Stopping diagnostic.")
        return

    results = inspect_reports(all_reports)
    summaries = print_summary_table(results)
    print_account_id_stability(summaries)
    print_focus_sections(results)
    print_recommended_production_mapping(summaries)
    print_final_conclusion(summaries)


if __name__ == "__main__":
    main()
