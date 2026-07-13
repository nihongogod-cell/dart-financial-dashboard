import json
from pathlib import Path
from datetime import datetime
from html import escape
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import altair as alt
import pandas as pd
import streamlit as st

from src.extract_accounts import (
    ACCOUNT_MAPPING,
    extract_accounts,
    find_best_matching_account_row,
)
from src.fetch_financial_statement import (
    build_request_url,
    fetch_multiple_years,
    load_api_key,
)


st.set_page_config(page_title="상장사 재무분석 대시보드", layout="wide")


BASE_DIR = Path(__file__).resolve().parent
COMPANY_MASTER_CSV_PATH = BASE_DIR / "data" / "processed" / "company_master.csv"
FINANCIAL_STATEMENT_CSV_PATH = BASE_DIR / "data" / "processed" / "financial_statement.csv"
FIXED_REPORT_CODE = "11011"
YEAR_COUNT = 5
LTM_REPORT_CODE = "LTM"
LTM_ACCOUNTS = ["매출액", "매출원가", "매출총이익", "판매비와 관리비", "영업이익", "당기순이익"]
INTERIM_REPORT_PRIORITY = ["11014", "11012", "11013"]
REPORT_LABELS = {
    "11011": "사업보고서",
    "11013": "1분기보고서",
    "11012": "반기보고서",
    "11014": "3분기보고서",
}
FS_DIV_MAP = {
    "연결재무제표": "CFS",
    "별도재무제표": "OFS",
}
CORP_CLS_LABELS = {
    "Y": "유가증권시장",
    "K": "코스닥시장",
    "N": "코넥스시장",
    "E": "기타법인",
}
ACCOUNT_COLOR_PALETTE = [
    "#2563eb",
    "#dc2626",
    "#16a34a",
    "#9333ea",
    "#ea580c",
    "#0891b2",
    "#be123c",
    "#4f46e5",
    "#65a30d",
    "#ca8a04",
    "#0f766e",
    "#7c3aed",
    "#0284c7",
    "#b91c1c",
    "#15803d",
    "#6d28d9",
    "#c2410c",
    "#0e7490",
    "#9f1239",
    "#4338ca",
]
ACCOUNT_CATEGORIES = {
    "재무상태표": [
        "자산총계",
        "유동자산",
        "비유동자산",
        "현금및현금성자산",
        "재고자산",
        "유형자산",
        "부채총계",
        "유동부채",
        "비유동부채",
        "자본총계",
        "이익잉여금",
    ],
    "손익계산서": [
        "매출액",
        "매출원가",
        "매출총이익",
        "판매비와 관리비",
        "영업이익",
        "당기순이익",
    ],
    "현금흐름표": [
        "영업활동현금흐름",
        "투자활동현금흐름",
        "재무활동현금흐름",
    ],
}
ACCOUNT_DISPLAY_ORDER = []

for category_accounts in ACCOUNT_CATEGORIES.values():
    ACCOUNT_DISPLAY_ORDER.extend(category_accounts)

COMPANY_COLUMNS = [
    "corp_code",
    "corp_name",
    "stock_code",
    "corp_cls",
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
PAGE_WIDTH_CSS = """
<style>
    :root {
        --page-bg: #FFE9D6;
        --main-text: #3A2E27;
        --secondary-text: #7A6558;
        --surface: #FFF7F0;
        --surface-alt: #FBE2CF;
        --table-header: #F3D2BC;
        --border: #D9B79C;
        --divider: #D9B79C;
        --accent: #E98A5A;
        --active-accent: #F46D5B;
        --hover-accent: #D96E3D;
        --gridline: #E7C9B4;
        --placeholder: #9A7F6C;
        --radio-border: #B98F73;
    }

    html,
    body,
    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stHeader"] {
        background: var(--page-bg);
        color: var(--main-text);
    }

    .block-container {
        max-width: 95vw;
        padding-left: 1.5rem;
        padding-right: 1.5rem;
    }

    h1,
    h2,
    h3,
    h4,
    h5,
    h6,
    p,
    label,
    span,
    div {
        color: var(--main-text);
    }

    .dashboard-title {
        margin: 0;
        color: var(--main-text);
        font-size: 2.4rem;
        font-weight: 800;
        letter-spacing: 0;
    }

    .dashboard-subtitle {
        margin-top: 0.35rem;
        margin-bottom: 1.75rem;
        color: var(--secondary-text);
        font-size: 1.08rem;
        font-weight: 500;
    }

    .dashboard-footer {
        margin-top: 4rem;
        padding-bottom: 1.5rem;
        text-align: center;
        color: var(--secondary-text);
        font-size: 0.82rem;
    }

    .company-info-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(120, 80, 50, 0.08);
        padding: 0.35rem 1.25rem;
        margin-bottom: 1rem;
    }

    .company-info-row {
        display: grid;
        grid-template-columns: minmax(5.5rem, 8rem) minmax(0, 1fr);
        gap: 1rem;
        align-items: start;
        padding: 0.7rem 0;
    }

    .company-info-row:not(:last-child) {
        border-bottom: 1px solid var(--gridline);
    }

    .company-info-label {
        color: var(--secondary-text);
        font-weight: 700;
    }

    .company-info-value,
    .company-info-value a {
        color: var(--main-text);
        overflow-wrap: anywhere;
    }

    .company-info-value a {
        text-decoration-color: var(--accent);
    }

    .financial-table-wrap {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 12px;
        overflow: hidden;
        margin-bottom: 1rem;
    }

    .financial-table {
        width: 100%;
        border-collapse: collapse;
        background: var(--surface);
        color: var(--main-text);
        font-size: 0.92rem;
    }

    .financial-table thead th {
        background: var(--table-header);
        color: #4A3428;
        border-bottom: 1px solid var(--border);
        padding: 0.6rem 0.75rem;
        text-align: left;
        font-weight: 800;
    }

    .financial-table tbody td {
        background: var(--surface);
        color: var(--main-text);
        border-bottom: 1px solid var(--border);
        padding: 0.58rem 0.75rem;
    }

    .financial-table tbody tr:hover td {
        background: #FCE6D7;
    }

    .financial-table tbody tr:last-child td {
        border-bottom: none;
    }

    .financial-table .amount-cell {
        text-align: right;
        font-variant-numeric: tabular-nums;
    }

    [data-testid="stVerticalBlockBorderWrapper"],
    [data-testid="stDataFrame"],
    [data-testid="stTable"],
    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div,
    textarea,
    input {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 0.65rem;
        color: var(--main-text);
    }

    input::placeholder,
    textarea::placeholder {
        color: var(--placeholder);
        opacity: 1;
    }

    div[data-baseweb="input"]:focus-within > div,
    div[data-baseweb="select"]:focus-within > div,
    textarea:focus,
    input:focus {
        border-color: var(--accent);
        box-shadow: 0 0 0 1px var(--accent);
    }

    div[data-baseweb="popover"],
    ul[role="listbox"],
    div[role="listbox"] {
        background: var(--surface-alt);
        color: var(--main-text);
        border-color: var(--border);
    }

    [role="option"]:hover,
    [data-baseweb="menu"] li:hover {
        background: #FCE6D7;
    }

    [aria-selected="true"] {
        background: var(--surface-alt);
        color: var(--main-text);
    }

    [data-testid="stRadio"] label,
    [data-testid="stCheckbox"] label {
        color: var(--main-text);
    }

    [data-testid="stRadio"] [role="radiogroup"] label span:first-child,
    [data-testid="stCheckbox"] label span:first-child {
        background: var(--surface);
        border-color: var(--radio-border);
    }

    [data-testid="stCheckbox"] div[data-baseweb="checkbox"] > div:first-child,
    [data-testid="stRadio"] div[role="radio"] {
        background: var(--surface);
        border-color: var(--radio-border);
    }

    [data-testid="stCheckbox"] input:checked + div,
    [data-testid="stRadio"] input:checked + div,
    [data-testid="stCheckbox"] div[data-baseweb="checkbox"][aria-checked="true"] > div:first-child,
    [data-testid="stRadio"] div[aria-checked="true"] {
        background-color: var(--active-accent);
        border-color: var(--active-accent);
    }

    [data-testid="stCheckbox"] label:hover span:first-child,
    [data-testid="stRadio"] label:hover span:first-child {
        border-color: var(--accent);
    }

    [data-testid="stVerticalBlockBorderWrapper"] {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(120, 80, 50, 0.08);
        padding: 1.25rem;
    }

    .stButton > button {
        background: var(--accent);
        border-color: var(--accent);
        color: #FFFDFC;
    }

    .stButton > button:hover,
    .stButton > button:focus {
        background: var(--hover-accent);
        border-color: var(--hover-accent);
        color: #FFFDFC;
    }

    [data-testid="stAlert"] {
        border-color: var(--border);
        color: var(--main-text);
    }

    [data-testid="stAlert"] > div {
        color: var(--main-text);
    }

    [data-testid="stDataFrame"] {
        border: 1px solid var(--border);
        border-radius: 12px;
        overflow: hidden;
    }

    [data-testid="stDataFrame"] * {
        color: var(--main-text);
    }

    [data-testid="stDataFrame"] [role="columnheader"] {
        background: var(--table-header);
        color: #4A3428;
        border-color: var(--border);
    }

    [data-testid="stDataFrame"] [role="gridcell"] {
        background: var(--surface);
        border-color: var(--border);
    }

    [data-testid="stDataFrame"] [role="row"]:hover [role="gridcell"] {
        background: #FCE6D7;
    }

    [data-testid="stVegaLiteChart"] {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 12px;
        box-sizing: border-box;
        width: 100%;
        max-width: 100%;
        min-width: 0;
        overflow: hidden;
        padding: 0.75rem;
    }

    [data-testid="stVegaLiteChart"] > div {
        background: var(--surface);
        max-width: 100%;
        min-width: 0;
    }

    hr {
        border-color: var(--divider);
    }
</style>
"""
CHART_HEIGHT = 620
CHART_SURFACE_COLOR = "#FFF7F0"
CHART_TEXT_COLOR = "#3A2E27"
CHART_GRID_COLOR = "#E7C9B4"
CHART_AXIS_COLOR = "#D9B79C"


def load_company_master_data(csv_path):
    """Load the full company master data from a CSV file."""
    company_data = pd.read_csv(csv_path, dtype=str, keep_default_na=False)

    for column in COMPANY_COLUMNS:
        if column not in company_data.columns:
            company_data[column] = ""

    return company_data


def load_financial_statement_data(csv_path):
    """Load generic financial statement data from a CSV file."""
    if not csv_path.exists():
        return pd.DataFrame(columns=FINANCIAL_STATEMENT_COLUMNS)

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


def get_market_label(company):
    """Return the Korean market classification label."""
    corp_cls = company.get("corp_cls", "").strip()
    return CORP_CLS_LABELS.get(corp_cls, "시장구분 미확인")


def format_company_option(company):
    """Create readable text for one radio option."""
    corp_name = get_display_value(company, "corp_name")
    stock_code = get_display_value(company, "stock_code")
    market_label = get_market_label(company)

    return f"{corp_name} | {market_label} | {stock_code}"


def build_company_info_row(label, value, is_link=False):
    """Build one themed company-information row."""
    safe_label = escape(label)
    safe_value = escape(value)

    if is_link and value != "정보 없음":
        href = value

        if not href.startswith(("http://", "https://")):
            href = f"https://{href}"

        safe_href = escape(href)
        value_html = f'<a href="{safe_href}" target="_blank" rel="noopener noreferrer">{safe_value}</a>'
    else:
        value_html = safe_value

    return (
        '<div class="company-info-row">'
        f'<div class="company-info-label">{safe_label}</div>'
        f'<div class="company-info-value">{value_html}</div>'
        "</div>"
    )


def show_company_card(company):
    """Display selected company information."""
    st.subheader("선택한 회사 정보")
    company_rows = [
        build_company_info_row("회사명", get_display_value(company, "corp_name")),
        build_company_info_row("종목코드", get_display_value(company, "stock_code")),
        build_company_info_row("시장구분", get_market_label(company)),
        build_company_info_row("대표이사", get_display_value(company, "ceo_nm")),
        build_company_info_row("업종코드", get_display_value(company, "induty_code")),
        build_company_info_row("주소", get_display_value(company, "adres")),
        build_company_info_row("홈페이지", get_display_value(company, "hm_url"), is_link=True),
        build_company_info_row("설립일", get_display_value(company, "est_dt")),
        build_company_info_row("결산월", get_display_value(company, "acc_mt")),
    ]
    card_html = '<div class="company-info-card">' + "".join(company_rows) + "</div>"
    st.markdown(card_html, unsafe_allow_html=True)


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


def filter_financial_statement_data(financial_statement_data, corp_code, fs_div):
    """Filter financial statement data for one company and fixed report settings."""
    is_selected_company = financial_statement_data["corp_code"] == corp_code
    is_annual_report = financial_statement_data["report_code"] == FIXED_REPORT_CODE
    is_selected_statement_type = financial_statement_data["fs_div"] == fs_div

    return financial_statement_data[is_selected_company & is_annual_report & is_selected_statement_type]


def prepare_chart_data(account_data):
    """Prepare selected account data for Altair charts."""
    chart_data = account_data.copy()
    chart_data["period_label"] = chart_data["year"].astype(str)
    numeric_year = pd.to_numeric(chart_data["year"], errors="coerce")
    latest_annual_year = numeric_year.max()
    chart_data["period_order"] = numeric_year

    if pd.isna(latest_annual_year):
        latest_annual_year = 0

    chart_data.loc[chart_data["period_label"] == "LTM", "period_order"] = latest_annual_year + 1
    chart_data["amount"] = pd.to_numeric(chart_data["amount"], errors="coerce")
    chart_data = chart_data.dropna(subset=["period_order", "amount"])
    chart_data["period_order"] = chart_data["period_order"].astype(int)
    chart_data["amount"] = chart_data["amount"].astype("int64")
    chart_data["amount_formatted"] = chart_data["amount"].map(lambda value: f"{int(value):,}")
    return chart_data.sort_values(["period_order", "account_nm"])


def get_account_colors(account_names):
    """Assign stable colors to account names."""
    account_colors = {}
    ordered_account_names = []

    for account_name in ACCOUNT_DISPLAY_ORDER:
        if account_name in account_names:
            ordered_account_names.append(account_name)

    for account_name in account_names:
        if account_name not in ordered_account_names:
            ordered_account_names.append(account_name)

    for index, account_name in enumerate(ordered_account_names):
        color_index = index % len(ACCOUNT_COLOR_PALETTE)
        account_colors[account_name] = ACCOUNT_COLOR_PALETTE[color_index]

    return account_colors


def show_account_checkboxes(account_names, corp_code, fs_div):
    """Show available account names grouped by financial statement category."""
    selected_accounts = []
    available_accounts = set(account_names)
    first_available_account = None

    for account_name in ACCOUNT_DISPLAY_ORDER:
        if account_name in available_accounts:
            first_available_account = account_name
            break

    for category_name, category_accounts in ACCOUNT_CATEGORIES.items():
        st.markdown(f"**{category_name}**")
        checkbox_columns = st.columns(2)
        available_category_accounts = []

        for account_name in category_accounts:
            if account_name in available_accounts:
                available_category_accounts.append(account_name)

        for index, account_name in enumerate(available_category_accounts):
            checkbox_column = checkbox_columns[index % 2]

            checkbox_key = f"account_{corp_code}_{FIXED_REPORT_CODE}_{fs_div}_{account_name}"
            is_checked = checkbox_column.checkbox(
                account_name,
                value=account_name == first_available_account,
                key=checkbox_key,
            )

            if is_checked:
                selected_accounts.append(account_name)

    return selected_accounts


def build_tooltip():
    """Build Korean chart tooltips."""
    return [
        alt.Tooltip("period_label:N", title="기간"),
        alt.Tooltip("account_nm:N", title="계정명"),
        alt.Tooltip("amount_formatted:N", title="금액"),
    ]


def calculate_linear_trend_amount(years, amounts, year):
    """Calculate one linear trend amount using a simple least-squares fit."""
    observation_count = len(years)
    average_year = sum(years) / observation_count
    average_amount = sum(amounts) / observation_count
    numerator = 0
    denominator = 0

    for index, observed_year in enumerate(years):
        year_difference = observed_year - average_year
        amount_difference = amounts[index] - average_amount
        numerator += year_difference * amount_difference
        denominator += year_difference * year_difference

    if denominator == 0:
        return None

    slope = numerator / denominator
    intercept = average_amount - slope * average_year
    return slope * year + intercept


def build_trendline_data(account_data, selected_accounts):
    """Build trendline rows from annual business-report observations only."""
    trendline_rows = []

    for account_name in selected_accounts:
        account_rows = account_data[account_data["account_nm"] == account_name].copy()
        account_rows = account_rows[account_rows["report_code"] == FIXED_REPORT_CODE]
        account_rows["numeric_year"] = pd.to_numeric(account_rows["year"], errors="coerce")
        account_rows["numeric_amount"] = pd.to_numeric(account_rows["amount"], errors="coerce")
        account_rows = account_rows.dropna(subset=["numeric_year", "numeric_amount"])
        account_rows = account_rows.sort_values("numeric_year")

        if len(account_rows) < 2:
            continue

        years = account_rows["numeric_year"].astype(float).tolist()
        amounts = account_rows["numeric_amount"].astype(float).tolist()

        for year in years:
            trend_amount = calculate_linear_trend_amount(years, amounts, year)

            if trend_amount is None:
                continue

            trendline_rows.append(
                {
                    "period_label": str(int(year)),
                    "period_order": int(year),
                    "account_nm": account_name,
                    "trend_amount": trend_amount,
                }
            )

    return pd.DataFrame(trendline_rows)


def apply_chart_theme(chart):
    """Apply the dashboard light theme to an Altair chart."""
    return chart.properties(
        height=CHART_HEIGHT,
        background=CHART_SURFACE_COLOR,
    ).configure_view(
        fill=CHART_SURFACE_COLOR,
        stroke=CHART_GRID_COLOR,
    ).configure_axis(
        labelColor=CHART_TEXT_COLOR,
        tickColor=CHART_AXIS_COLOR,
        domainColor=CHART_AXIS_COLOR,
        gridColor=CHART_GRID_COLOR,
    )


def build_line_chart(chart_data, selected_accounts, selected_colors, show_trendline=False, trendline_data=None):
    """Build a multi-account line chart."""
    hover = alt.selection_point(
        nearest=True,
        on="pointerover",
        fields=["period_label", "account_nm"],
        empty=False,
    )
    color_scale = alt.Scale(domain=selected_accounts, range=selected_colors)
    period_sort = alt.SortField(field="period_order", order="ascending")
    base = alt.Chart(chart_data).encode(
        x=alt.X("period_label:N", title=None, sort=period_sort),
        y=alt.Y("amount:Q", title=None),
        color=alt.Color("account_nm:N", scale=color_scale, legend=None),
        detail=alt.Detail("account_nm:N"),
        tooltip=build_tooltip(),
    )
    lines = base.mark_line(strokeWidth=4)
    points = base.mark_circle().encode(
        size=alt.condition(hover, alt.value(240), alt.value(60)),
    ).add_params(hover)

    chart = lines + points

    if show_trendline and trendline_data is not None and not trendline_data.empty:
        trendlines = alt.Chart(trendline_data).mark_line(
            strokeWidth=2,
            strokeDash=[6, 4],
        ).encode(
            x=alt.X("period_label:N", title=None, sort=period_sort),
            y=alt.Y("trend_amount:Q", title=None),
            color=alt.Color("account_nm:N", scale=color_scale, legend=None),
            detail=alt.Detail("account_nm:N"),
        )
        chart = chart + trendlines

    return apply_chart_theme(chart)


def build_bar_chart(chart_data, selected_accounts, selected_colors):
    """Build a grouped multi-account bar chart."""
    color_scale = alt.Scale(domain=selected_accounts, range=selected_colors)
    period_sort = alt.SortField(field="period_order", order="ascending")

    chart = alt.Chart(chart_data).mark_bar().encode(
        x=alt.X("period_label:N", title=None, sort=period_sort),
        xOffset=alt.XOffset("account_nm:N"),
        y=alt.Y("amount:Q", title=None),
        color=alt.Color("account_nm:N", scale=color_scale, legend=None),
        tooltip=build_tooltip(),
    )

    return apply_chart_theme(chart)


def show_custom_legend(selected_accounts, account_colors):
    """Show a compact custom legend beside the chart."""
    legend_html = ""

    for account_name in selected_accounts:
        safe_account_name = escape(account_name)
        safe_color = escape(account_colors[account_name])
        legend_html += (
            '<div style="display:flex; align-items:center; justify-content:space-between; '
            'gap:10px; margin-bottom:8px; font-size:0.9rem; max-width:100%; min-width:0;">'
            f'<span style="min-width:0; overflow-wrap:anywhere;">{safe_account_name}</span>'
            f'<span style="display:inline-block; flex:0 0 32px; border-top:4px solid {safe_color};"></span>'
            "</div>"
        )

    st.markdown(legend_html, unsafe_allow_html=True)


def convert_amount_to_int(amount_text):
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


def fetch_dart_response(api_key, corp_code, bsns_year, report_code, fs_div):
    """Fetch one DART response in memory without saving raw JSON."""
    request_url = build_request_url(api_key, corp_code, bsns_year, report_code, fs_div)

    with urlopen(request_url) as response:
        response_text = response.read().decode("utf-8")

    return json.loads(response_text)


def safely_fetch_dart_response(api_key, corp_code, bsns_year, report_code, fs_div):
    """Fetch one DART response and return an empty response on failure."""
    try:
        return fetch_dart_response(api_key, corp_code, bsns_year, report_code, fs_div)
    except json.JSONDecodeError as error:
        print(f"Failure: Could not read DART JSON response for {bsns_year} {report_code} {fs_div}: {error}")
    except HTTPError as error:
        print(f"Failure: DART API HTTP error for {bsns_year} {report_code} {fs_div}: {error.code}")
    except URLError as error:
        print(f"Failure: Could not connect to DART API for {bsns_year} {report_code} {fs_div}: {error.reason}")
    except OSError as error:
        print(f"Failure: Could not fetch DART data for {bsns_year} {report_code} {fs_div}: {error}")

    return {"status": "", "message": "", "list": []}


def response_has_rows(response_data):
    """Return True when a DART response is valid and has rows."""
    rows = response_data.get("list", [])
    return response_data.get("status") == "000" and bool(rows)


def find_latest_annual_response(api_key, corp_code, fs_div):
    """Find the latest valid annual report response."""
    current_year = datetime.now().year

    for year in range(current_year, current_year - 8, -1):
        response_data = safely_fetch_dart_response(api_key, corp_code, str(year), FIXED_REPORT_CODE, fs_div)

        if response_has_rows(response_data):
            return str(year), response_data

    return None, None


def find_latest_interim_response(api_key, corp_code, fs_div, latest_annual_year):
    """Find the latest valid interim report after the latest annual report."""
    current_year = datetime.now().year
    annual_year_number = int(latest_annual_year)

    for year in range(current_year, annual_year_number, -1):
        for report_code in INTERIM_REPORT_PRIORITY:
            response_data = safely_fetch_dart_response(api_key, corp_code, str(year), report_code, fs_div)

            if response_has_rows(response_data):
                return str(year), report_code, response_data

    return None, None, None


def find_ltm_account_row(dart_rows, account_name, required_fields, corp_name="", report_code="", fs_div=""):
    """Find one mapped account row with valid source fields."""
    account_settings = ACCOUNT_MAPPING[account_name]
    amount_fields = []

    for field_name in required_fields:
        amount_fields.append((field_name, 0))

    return find_best_matching_account_row(
        dart_rows,
        account_name,
        account_settings,
        amount_fields,
        corp_name=corp_name,
        report_code=report_code,
        fs_div=fs_div,
    )


def build_ltm_session_key(corp_code, fs_div):
    """Build the session key used to store small LTM results."""
    return f"ltm_rows_{corp_code}_{fs_div}"


def calculate_ltm_rows(corp_name, corp_code, fs_div):
    """Calculate temporary LTM rows in memory for supported income accounts."""
    api_key = load_api_key()

    if not api_key:
        return {
            "rows": [],
            "message": "DART_API_KEY가 없어 LTM을 계산하지 못했습니다.",
            "interim_label": "",
        }

    latest_annual_year, annual_response = find_latest_annual_response(api_key, corp_code, fs_div)

    if annual_response is None:
        return {
            "rows": [],
            "message": "유효한 최신 사업보고서를 찾지 못해 LTM을 표시하지 않습니다.",
            "interim_label": "",
        }

    interim_year, interim_report_code, interim_response = find_latest_interim_response(
        api_key,
        corp_code,
        fs_div,
        latest_annual_year,
    )

    if interim_response is None:
        return {
            "rows": [],
            "message": "최신 사업보고서 이후의 유효한 분기·반기보고서가 없어 LTM을 표시하지 않습니다.",
            "interim_label": "",
        }

    annual_rows = annual_response.get("list", [])
    interim_rows = interim_response.get("list", [])
    ltm_rows = []

    for account_name in LTM_ACCOUNTS:
        annual_row = find_ltm_account_row(
            annual_rows,
            account_name,
            ["thstrm_amount"],
            corp_name=corp_name,
            report_code=FIXED_REPORT_CODE,
            fs_div=fs_div,
        )
        interim_row = find_ltm_account_row(
            interim_rows,
            account_name,
            ["thstrm_add_amount", "frmtrm_add_amount"],
            corp_name=corp_name,
            report_code=interim_report_code,
            fs_div=fs_div,
        )

        if annual_row is None or interim_row is None:
            continue

        annual_amount = convert_amount_to_int(annual_row.get("thstrm_amount", ""))
        current_interim_cumulative = convert_amount_to_int(interim_row.get("thstrm_add_amount", ""))
        previous_same_period_cumulative = convert_amount_to_int(interim_row.get("frmtrm_add_amount", ""))

        if annual_amount is None or current_interim_cumulative is None or previous_same_period_cumulative is None:
            continue

        ltm_amount = annual_amount + current_interim_cumulative - previous_same_period_cumulative
        ltm_rows.append(
            {
                "corp_code": corp_code,
                "corp_name": corp_name,
                "year": "LTM",
                "report_code": LTM_REPORT_CODE,
                "fs_div": fs_div,
                "account_nm": account_name,
                "amount": ltm_amount,
            }
        )

    interim_label = f"{interim_year}년 {REPORT_LABELS.get(interim_report_code, interim_report_code)}"

    if not ltm_rows:
        return {
            "rows": [],
            "message": "LTM 계산에 필요한 계정 값을 찾지 못해 LTM을 표시하지 않습니다.",
            "interim_label": interim_label,
        }

    return {
        "rows": ltm_rows,
        "message": f"LTM 기준: {interim_label}",
        "interim_label": interim_label,
    }


def store_ltm_rows(selected_company, fs_div):
    """Calculate and store small LTM result rows for one company/fs_div."""
    corp_code = selected_company["corp_code"]
    corp_name = selected_company["corp_name"]
    session_key = build_ltm_session_key(corp_code, fs_div)
    st.session_state[session_key] = calculate_ltm_rows(corp_name, corp_code, fs_div)


def get_ltm_rows_from_session(corp_code, fs_div):
    """Get stored LTM rows and metadata for chart rendering."""
    session_key = build_ltm_session_key(corp_code, fs_div)
    return st.session_state.get(session_key, {"rows": [], "message": "", "interim_label": ""})


def append_ltm_rows(company_data, ltm_data):
    """Append temporary LTM rows to annual company data for display only."""
    ltm_rows = ltm_data.get("rows", [])

    if not ltm_rows:
        return company_data

    ltm_data_frame = pd.DataFrame(ltm_rows, columns=FINANCIAL_STATEMENT_COLUMNS)
    return pd.concat([company_data, ltm_data_frame], ignore_index=True)


def sort_display_data(account_data):
    """Sort annual rows by year and keep LTM as the final period."""
    display_data = account_data.copy()
    numeric_year = pd.to_numeric(display_data["year"], errors="coerce")
    latest_annual_year = numeric_year.max()

    if pd.isna(latest_annual_year):
        latest_annual_year = 0

    display_data["_period_order"] = numeric_year
    display_data.loc[display_data["year"].astype(str) == "LTM", "_period_order"] = latest_annual_year + 1
    display_data["_period_order"] = display_data["_period_order"].fillna(0).astype(int)
    display_data = display_data.sort_values(["_period_order", "account_nm"])
    return display_data.drop(columns=["_period_order"])


def format_table_amount(amount):
    """Format one amount for display without changing the source data."""
    if pd.isna(amount):
        return ""

    try:
        return f"{int(amount):,}"
    except (TypeError, ValueError):
        return str(amount)


def build_financial_table_display_data(account_data):
    """Build a localized display-only financial data table."""
    table_data = account_data[["year", "account_nm", "amount"]].copy()
    table_data = table_data.rename(
        columns={
            "year": "연도",
            "account_nm": "계정명",
            "amount": "금액",
        }
    )
    table_data["금액"] = table_data["금액"].map(format_table_amount)
    return table_data


def render_financial_table(table_data):
    """Render a warm-themed display-only financial table."""
    header_cells = "".join(f"<th>{escape(column)}</th>" for column in table_data.columns)
    body_rows = []

    for row in table_data.to_dict("records"):
        year_value = escape(str(row.get("연도", "")))
        account_value = escape(str(row.get("계정명", "")))
        amount_value = escape(str(row.get("금액", "")))
        body_rows.append(
            "<tr>"
            f"<td>{year_value}</td>"
            f"<td>{account_value}</td>"
            f'<td class="amount-cell">{amount_value}</td>'
            "</tr>"
        )

    table_html = (
        '<div class="financial-table-wrap">'
        '<table class="financial-table">'
        f"<thead><tr>{header_cells}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table>"
        "</div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)


def get_latest_completed_years(year_count):
    """Return the latest completed business years."""
    latest_completed_year = datetime.now().year - 1
    years = []

    for offset in range(year_count):
        years.append(str(latest_completed_year - offset))

    return years


def fetch_and_extract_financial_data(selected_company):
    """Fetch DART data and update financial_statement.csv."""
    corp_name = selected_company["corp_name"]
    years = get_latest_completed_years(YEAR_COUNT)

    status_message = st.empty()
    status_message.info("데이터를 가져오는 중입니다.")
    all_fetch_results = []
    total_extracted_rows = 0

    for fs_div in FS_DIV_MAP.values():
        fetch_results = fetch_multiple_years(
            company_name=corp_name,
            years=years,
            report_code=FIXED_REPORT_CODE,
            fs_div=fs_div,
        )
        all_fetch_results.extend(fetch_results)

        for result in fetch_results:
            extracted_rows = extract_accounts(
                json_path=result["raw_json_path"],
                corp_name=result["corp_name"],
                corp_code=result["corp_code"],
                report_code=FIXED_REPORT_CODE,
                fs_div=fs_div,
                current_period_only=True,
            )
            total_extracted_rows += len(extracted_rows)

        store_ltm_rows(selected_company, fs_div)

    if not all_fetch_results:
        status_message.error("재무데이터를 가져오지 못했습니다.")
        return False

    if total_extracted_rows == 0:
        status_message.error("재무데이터에서 표시할 계정을 추출하지 못했습니다.")
        return False

    successful_report_count = len(all_fetch_results)
    status_message.success(f"데이터를 불러오는데 성공했습니다. 성공한 재무제표: {successful_report_count}건")
    return True


def show_financial_statement_chart(financial_statement_data, selected_company):
    """Show account selector, table, and chart for the selected company."""
    st.header("재무데이터")

    if selected_company is None:
        st.info("회사를 선택하면 재무데이터가 표시됩니다.")
        return

    corp_code = selected_company["corp_code"]
    financial_statement_type = st.selectbox(
        "재무제표 종류",
        ["연결재무제표", "별도재무제표"],
    )
    selected_fs_div = FS_DIV_MAP[financial_statement_type]
    company_data = filter_financial_statement_data(financial_statement_data, corp_code, selected_fs_div)
    ltm_data = get_ltm_rows_from_session(corp_code, selected_fs_div)

    if company_data.empty:
        st.info("선택한 재무제표 종류의 데이터가 없습니다. 먼저 재무데이터를 가져오거나 다른 재무제표 종류를 선택해 주세요.")
        return

    company_data = append_ltm_rows(company_data, ltm_data)

    available_account_names = set(company_data["account_nm"].dropna().unique())
    account_names = [account_name for account_name in ACCOUNT_DISPLAY_ORDER if account_name in available_account_names]

    if not account_names:
        st.info("표시할 수 있는 표준 계정 데이터가 없습니다.")
        return

    account_colors = get_account_colors(account_names)
    table_placeholder = st.empty()
    selector_column, chart_column = st.columns([1.1, 3.4], gap="large")

    with selector_column:
        st.markdown("#### 계정 선택")
        selected_accounts = show_account_checkboxes(account_names, corp_code, selected_fs_div)

    if not selected_accounts:
        table_placeholder.info("그래프에 표시할 계정을 하나 이상 선택해 주세요.")
        return

    account_data = company_data[company_data["account_nm"].isin(selected_accounts)]
    account_data = sort_display_data(account_data)

    table_data = build_financial_table_display_data(account_data)
    with table_placeholder.container():
        render_financial_table(table_data)

    with chart_column:
        chart_type = st.selectbox("그래프 종류", ["Line chart", "Bar chart"])
        show_trendline = False

        if chart_type == "Line chart":
            show_trendline = st.checkbox("추세선 표시", value=False)

        if ltm_data.get("message"):
            st.caption(ltm_data["message"])

        chart_data = prepare_chart_data(account_data)
        selected_colors = [account_colors[account_name] for account_name in selected_accounts]

        if chart_type == "Line chart":
            trendline_data = build_trendline_data(account_data, selected_accounts)
            chart = build_line_chart(
                chart_data,
                selected_accounts,
                selected_colors,
                show_trendline=show_trendline,
                trendline_data=trendline_data,
            )
        else:
            chart = build_bar_chart(chart_data, selected_accounts, selected_colors)

        chart_col, legend_col = st.columns([4.7, 1.3])

        with chart_col:
            st.altair_chart(chart, use_container_width=True)

        with legend_col:
            show_custom_legend(selected_accounts, account_colors)


def main():
    st.markdown(PAGE_WIDTH_CSS, unsafe_allow_html=True)
    st.markdown(
        """
        <h1 class="dashboard-title">상장사 재무분석 대시보드</h1>
        <p class="dashboard-subtitle">상장사의 5개년 재무 흐름과 LTM을 한눈에 분석하세요.</p>
        """,
        unsafe_allow_html=True,
    )

    if not COMPANY_MASTER_CSV_PATH.exists():
        st.error(
            "company_master.csv 파일이 없습니다. 먼저 src/build_company_master.py를 실행해서 "
            "data/processed/company_master.csv를 생성해 주세요."
        )
        return

    company_data = load_company_master_data(COMPANY_MASTER_CSV_PATH)
    selected_company = show_company_search(company_data)

    if selected_company is not None:
        if st.button("재무데이터 가져오기"):
            fetch_and_extract_financial_data(selected_company)

    st.divider()
    financial_statement_data = load_financial_statement_data(FINANCIAL_STATEMENT_CSV_PATH)
    show_financial_statement_chart(financial_statement_data, selected_company)
    st.markdown(
        '<div class="dashboard-footer">© 2026 Yoon Seowon. All rights reserved.</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
