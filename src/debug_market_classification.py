import csv
import xml.etree.ElementTree as ET
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
CORPCODE_XML_PATH = BASE_DIR / "data" / "raw" / "CORPCODE.xml"
COMPANY_LIST_CSV_PATH = BASE_DIR / "data" / "processed" / "company_list.csv"
COMPANY_MASTER_CSV_PATH = BASE_DIR / "data" / "processed" / "company_master.csv"
KNOWN_COMPANIES = ["삼성전자", "카카오", "알테오젠", "툴젠"]
SEARCH_TERMS = [
    "market",
    "corp_cls",
    "corp_class",
    "시장",
    "유가",
    "코스닥",
    "코넥스",
    "KOSPI",
    "KOSDAQ",
    "KONEX",
]


def print_section(title):
    """Print a clear section header."""
    print(f"\n=== {title} ===")


def read_csv_rows(csv_path):
    """Read a CSV file without modifying it."""
    with csv_path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        return reader.fieldnames or [], list(reader)


def contains_search_term(text):
    """Check whether text contains a market-related search term."""
    lower_text = str(text).lower()

    for term in SEARCH_TERMS:
        if term.lower() in lower_text:
            return True

    return False


def row_has_search_term(row):
    """Check whether any field name or value in a row looks market-related."""
    for field_name, value in row.items():
        if contains_search_term(field_name) or contains_search_term(value):
            return True

    return False


def inspect_xml_structure(xml_path):
    """Inspect CORPCODE.xml structure and sample values."""
    print_section("CORPCODE.xml Structure")

    if not xml_path.exists():
        print(f"Missing file: {xml_path}")
        return [], False

    tree = ET.parse(xml_path)
    root = tree.getroot()
    company_elements = list(root)

    print(f"root tag: {root.tag}")

    if not company_elements:
        print("No company records found.")
        return [], False

    print(f"first company element tag: {company_elements[0].tag}")
    print("\nFirst 5 company records:")

    sample_rows = []

    for index, company_element in enumerate(company_elements[:5], start=1):
        row = {}
        print(f"\nRecord {index}")

        for child in company_element:
            value = child.text.strip() if child.text else ""
            row[child.tag] = value
            print(f"{child.tag}: {value}")

        sample_rows.append(row)

    found_market_field = any(row_has_search_term(row) for row in sample_rows)
    return sample_rows, found_market_field


def print_csv_preview(csv_name, csv_path):
    """Print CSV columns and the first 5 rows."""
    print_section(f"{csv_name} Columns And First 5 Rows")

    if not csv_path.exists():
        print(f"Missing file: {csv_path}")
        return [], [], False

    columns, rows = read_csv_rows(csv_path)
    print(f"columns: {', '.join(columns)}")
    print("\nFirst 5 rows:")

    for index, row in enumerate(rows[:5], start=1):
        print(f"\nRow {index}")

        for column in columns:
            print(f"{column}: {row.get(column, '')}")

    sample_rows = rows[:5]
    found_market_field = any(contains_search_term(column) for column in columns)
    found_market_value = any(row_has_search_term(row) for row in sample_rows)
    return columns, rows, found_market_field or found_market_value


def print_search_matches(source_name, columns, rows):
    """Print market-related matches in column names and sample values."""
    print_section(f"{source_name} Market Term Search")
    matched_anything = False

    for column in columns:
        if contains_search_term(column):
            print(f"column match: {column}")
            matched_anything = True

    for row_index, row in enumerate(rows[:20], start=1):
        for column, value in row.items():
            if contains_search_term(value):
                print(f"value match: row {row_index}, {column}: {value}")
                matched_anything = True

    if not matched_anything:
        print("No market-related terms found in column names or sampled values.")


def find_company_row(rows, company_name):
    """Find one company row by corp_name."""
    for row in rows:
        if row.get("corp_name", "") == company_name:
            return row

    return None


def print_known_company_values(company_list_rows, company_master_rows):
    """Print locally available values for selected known companies."""
    print_section("Known Company Local Values")

    for company_name in KNOWN_COMPANIES:
        print(f"\nCompany: {company_name}")

        company_list_row = find_company_row(company_list_rows, company_name)
        if company_list_row:
            print("company_list.csv:")
            print(company_list_row)
        else:
            print("company_list.csv: missing")

        company_master_row = find_company_row(company_master_rows, company_name)
        if company_master_row:
            print("company_master.csv:")
            print(company_master_row)
        else:
            print("company_master.csv: missing")


def print_conclusion(xml_found, company_list_found, company_master_found):
    """Print final market-field conclusion."""
    print_section("Conclusion")
    any_local_market_field = xml_found or company_list_found or company_master_found

    print(f"CORPCODE.xml market field: {'found' if xml_found else 'not found'}")
    print(f"company_list.csv market field: {'found' if company_list_found else 'not found'}")
    print(f"company_master.csv market field: {'found' if company_master_found else 'not found'}")
    print(f"Additional external data source required: {'no' if any_local_market_field else 'yes'}")


def main():
    xml_rows, xml_found = inspect_xml_structure(CORPCODE_XML_PATH)

    company_list_columns, company_list_rows, company_list_found = print_csv_preview(
        "company_list.csv",
        COMPANY_LIST_CSV_PATH,
    )
    company_master_columns, company_master_rows, company_master_found = print_csv_preview(
        "company_master.csv",
        COMPANY_MASTER_CSV_PATH,
    )

    print_search_matches("CORPCODE.xml", list(xml_rows[0].keys()) if xml_rows else [], xml_rows)
    print_search_matches("company_list.csv", company_list_columns, company_list_rows)
    print_search_matches("company_master.csv", company_master_columns, company_master_rows)
    print_known_company_values(company_list_rows, company_master_rows)
    print_conclusion(xml_found, company_list_found, company_master_found)


if __name__ == "__main__":
    main()
