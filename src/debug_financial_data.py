from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent
FINANCIAL_STATEMENT_PATH = BASE_DIR / "data" / "processed" / "financial_statement.csv"
TARGET_CORP_NAME = "삼성전자"
YEARS_TO_CHECK = [2021, 2022, 2023, 2024, 2025]
DUPLICATE_COLUMNS = ["corp_code", "year", "report_code", "fs_div", "account_nm"]


def load_financial_statement(csv_path):
    """Read financial_statement.csv."""
    return pd.read_csv(
        csv_path,
        dtype={
            "corp_code": str,
            "corp_name": str,
            "report_code": str,
            "fs_div": str,
            "account_nm": str,
        },
    )


def print_samsung_rows(financial_statement):
    """Print all rows for 삼성전자."""
    samsung_rows = financial_statement[financial_statement["corp_name"] == TARGET_CORP_NAME]

    print(f"\nAll rows for {TARGET_CORP_NAME}:")
    print(samsung_rows.to_string(index=False))
    return samsung_rows


def print_accounts_by_year(samsung_rows):
    """Print available account names grouped by year."""
    print("\nAvailable account_nm values by year:")

    for year, year_rows in samsung_rows.groupby("year"):
        account_names = sorted(year_rows["account_nm"].dropna().unique())
        print(f"{year}: {', '.join(account_names)}")


def print_duplicate_counts(financial_statement):
    """Print duplicate counts by key columns."""
    duplicate_counts = (
        financial_statement.groupby(DUPLICATE_COLUMNS)
        .size()
        .reset_index(name="count")
    )
    duplicate_counts = duplicate_counts[duplicate_counts["count"] > 1]

    print("\nDuplicate counts by corp_code, year, report_code, fs_div, account_nm:")

    if duplicate_counts.empty:
        print("No duplicates found.")
        return

    print(duplicate_counts.to_string(index=False))


def print_year_coverage(samsung_rows):
    """Print whether selected years exist for 삼성전자."""
    existing_years = set(samsung_rows["year"].astype(int).tolist())

    print(f"\nYear coverage for {TARGET_CORP_NAME}:")

    for year in YEARS_TO_CHECK:
        exists = year in existing_years
        print(f"{year}: {exists}")


def main():
    if not FINANCIAL_STATEMENT_PATH.exists():
        print(f"financial_statement.csv was not found: {FINANCIAL_STATEMENT_PATH}")
        return

    financial_statement = load_financial_statement(FINANCIAL_STATEMENT_PATH)
    samsung_rows = print_samsung_rows(financial_statement)
    print_accounts_by_year(samsung_rows)
    print_duplicate_counts(financial_statement)
    print_year_coverage(samsung_rows)


if __name__ == "__main__":
    main()
