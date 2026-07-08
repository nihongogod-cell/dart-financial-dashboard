from pathlib import Path

import pandas as pd
import streamlit as st


BASE_DIR = Path(__file__).resolve().parent
COMPANY_LIST_CSV_PATH = BASE_DIR / "data" / "processed" / "company_list.csv"
COMPANY_MASTER_CSV_PATH = BASE_DIR / "data" / "processed" / "company_master_sample.csv"
FINANCIAL_STATEMENT_CSV_PATH = BASE_DIR / "data" / "processed" / "financial_statement.csv"
FIXED_REPORT_CODE = "11011"
FIXED_FS_DIV = "CFS"
COMPANY_COLUMNS = [
    "corp_code",
    "corp_name",
    "stock_code",
    "ceo_nm",
    "induty_code",
    "adres",
    "hm_url",
    "est_dt",
    "acc_mt",
]
FINANCIAL_STATEMENT_COLUMNS = [
    "corp_code",
    "corp_name",
    "year",
    "report_code",
    "fs_div",
    "account_nm",
    "amount",
]


def choose_company_csv_path():
    """Use the enriched company master file if it exists."""
    if COMPANY_MASTER_CSV_PATH.exists():
        return COMPANY_MASTER_CSV_PATH

    return COMPANY_LIST_CSV_PATH


def load_company_data(csv_path):
    """Load company data from a CSV file."""
    company_data = pd.read_csv(csv_path, dtype=str, keep_default_na=False)

    for column in COMPANY_COLUMNS:
        if column not in company_data.columns:
            company_data[column] = ""

    return company_data


def load_financial_statement_data(csv_path):
    """Load generic financial statement data from a CSV file."""
    return pd.read_csv(
        csv_path,
        dtype={
            "corp_code": str,
            "report_code": str,
            "fs_div": str,
            "account_nm": str,
        },
    )


def filter_companies(company_list, keyword):
    """Find companies where corp_name contains the search keyword."""
    if not keyword:
        return pd.DataFrame(columns=company_list.columns)

    contains_keyword = company_list["corp_name"].str.contains(keyword, case=False, na=False)
    return company_list[contains_keyword]


def get_display_value(company, field_name):
    """Return a display value, or 정보 없음 when the field is empty."""
    value = company.get(field_name, "")

    if not value or value == "-":
        return "정보 없음"

    return value


def format_company_option(company):
    """Create readable text for one radio option."""
    corp_name = get_display_value(company, "corp_name")
    stock_code = get_display_value(company, "stock_code")
    ceo_name = get_display_value(company, "ceo_nm")
    industry_code = get_display_value(company, "induty_code")

    return (
        f"{corp_name} ({stock_code})\n"
        f"대표이사: {ceo_name}\n"
        f"업종코드: {industry_code}"
    )


def show_company_card(company):
    """Display selected company information."""
    st.subheader("선택한 회사 정보")

    with st.container(border=True):
        st.write(f"회사명: {get_display_value(company, 'corp_name')}")
        st.write(f"종목코드: {get_display_value(company, 'stock_code')}")
        st.write(f"대표이사: {get_display_value(company, 'ceo_nm')}")
        st.write(f"업종코드: {get_display_value(company, 'induty_code')}")
        st.write(f"주소: {get_display_value(company, 'adres')}")
        st.write(f"홈페이지: {get_display_value(company, 'hm_url')}")
        st.write(f"설립일: {get_display_value(company, 'est_dt')}")
        st.write(f"결산월: {get_display_value(company, 'acc_mt')}")


def show_company_search(company_list):
    """Show company search input, radio selector, and selected company."""
    st.header("회사 검색")

    keyword = st.text_input("회사명 검색")
    filtered_companies = filter_companies(company_list, keyword)

    if keyword and filtered_companies.empty:
        st.info("검색 결과가 없습니다.")
        return None

    if filtered_companies.empty:
        st.info("회사명을 입력하면 검색 결과가 표시됩니다.")
        return None

    company_options = filtered_companies.to_dict("records")
    selected_company = st.radio(
        "회사 선택",
        company_options,
        format_func=format_company_option,
        index=0,
    )

    show_company_card(selected_company)
    return selected_company


def filter_financial_statement_data(financial_statement_data, corp_code):
    """Filter financial statement data for one company and fixed report settings."""
    is_selected_company = financial_statement_data["corp_code"] == corp_code
    is_annual_report = financial_statement_data["report_code"] == FIXED_REPORT_CODE
    is_consolidated = financial_statement_data["fs_div"] == FIXED_FS_DIV

    return financial_statement_data[is_selected_company & is_annual_report & is_consolidated]


def prepare_chart_data(account_data):
    """Sort account data by year so the chart is easy to read."""
    chart_data = account_data.sort_values("year")
    return chart_data.set_index("year")


def show_financial_statement_chart(financial_statement_data, selected_company):
    """Show account selector, table, and chart for the selected company."""
    st.header("재무데이터")

    if selected_company is None:
        st.info("회사를 선택하면 재무데이터가 표시됩니다.")
        return

    corp_code = selected_company["corp_code"]
    company_data = filter_financial_statement_data(financial_statement_data, corp_code)

    if company_data.empty:
        st.info("아직 수집된 재무데이터가 없습니다.")
        return

    account_names = sorted(company_data["account_nm"].dropna().unique())
    selected_account = st.selectbox("계정 선택", account_names)
    chart_type = st.selectbox("그래프 종류", ["Line chart", "Bar chart"])

    account_data = company_data[company_data["account_nm"] == selected_account]
    account_data = account_data.sort_values("year")

    st.dataframe(account_data[FINANCIAL_STATEMENT_COLUMNS], use_container_width=True)

    chart_data = prepare_chart_data(account_data)

    if chart_type == "Line chart":
        st.line_chart(chart_data["amount"])
    else:
        st.bar_chart(chart_data["amount"])


def main():
    st.title("DART 재무데이터 대시보드")

    company_csv_path = choose_company_csv_path()

    if not company_csv_path.exists():
        st.error(f"CSV file was not found: {company_csv_path}")
        return

    if not FINANCIAL_STATEMENT_CSV_PATH.exists():
        st.error(f"CSV file was not found: {FINANCIAL_STATEMENT_CSV_PATH}")
        return

    company_list = load_company_data(company_csv_path)
    selected_company = show_company_search(company_list)

    st.divider()
    financial_statement_data = load_financial_statement_data(FINANCIAL_STATEMENT_CSV_PATH)
    show_financial_statement_chart(financial_statement_data, selected_company)


if __name__ == "__main__":
    main()
