import os
import csv
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen
from zipfile import BadZipFile, ZipFile
import xml.etree.ElementTree as ET

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
ZIP_PATH = RAW_DIR / "corp_code.zip"
XML_PATH = RAW_DIR / "CORPCODE.xml"
CSV_PATH = PROCESSED_DIR / "company_list.csv"
CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
CSV_COLUMNS = ["corp_code", "corp_name", "stock_code", "modify_date"]


def load_api_key():
    """Load DART_API_KEY from the project root .env file."""
    load_dotenv(ENV_PATH)
    return os.getenv("DART_API_KEY")


def build_download_url(api_key):
    """Build the DART corpCode.xml download URL."""
    query_string = urlencode({"crtfc_key": api_key})
    return f"{CORP_CODE_URL}?{query_string}"


def download_file(download_url, save_path):
    """Download a file from download_url and save it to save_path."""
    save_path.parent.mkdir(parents=True, exist_ok=True)

    with urlopen(download_url) as response:
        file_data = response.read()

    save_path.write_bytes(file_data)


def unzip_corp_code(zip_path, xml_path):
    """Unzip CORPCODE.xml from the downloaded zip file."""
    with ZipFile(zip_path, "r") as zip_file:
        zip_file.extract(xml_path.name, xml_path.parent)


def get_text(element, tag_name):
    """Get text from an XML tag, or return an empty string."""
    found_element = element.find(tag_name)

    if found_element is None or found_element.text is None:
        return ""

    return found_element.text.strip()


def parse_company_list(xml_path):
    """Read CORPCODE.xml and return companies with a stock code."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    companies = []

    for company in root.findall("list"):
        stock_code = get_text(company, "stock_code")

        if stock_code:
            companies.append(
                {
                    "corp_code": get_text(company, "corp_code"),
                    "corp_name": get_text(company, "corp_name"),
                    "stock_code": stock_code,
                    "modify_date": get_text(company, "modify_date"),
                }
            )

    return companies


def save_company_list(companies, csv_path):
    """Save the company list to a CSV file."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(companies)


def main():
    api_key = load_api_key()

    if not api_key:
        print("Failure: DART_API_KEY was not found in the project root .env file.")
        return

    download_url = build_download_url(api_key)

    try:
        print("Downloading DART company code zip file...")
        download_file(download_url, ZIP_PATH)
        print(f"Success: Downloaded corp code zip to {ZIP_PATH}")

        print("Unzipping CORPCODE.xml...")
        unzip_corp_code(ZIP_PATH, XML_PATH)
        print(f"Success: Extracted XML file to {XML_PATH}")

        print("Parsing listed companies from CORPCODE.xml...")
        companies = parse_company_list(XML_PATH)
        print(f"Success: Found {len(companies)} companies with stock codes.")

        print("Saving company list CSV...")
        save_company_list(companies, CSV_PATH)
        print(f"Success: Saved company list CSV to {CSV_PATH}")
    except HTTPError as error:
        print(f"Failure: DART API returned an HTTP error: {error.code}")
    except URLError as error:
        print(f"Failure: Could not connect to DART API: {error.reason}")
    except BadZipFile:
        print(f"Failure: The downloaded file is not a valid zip file: {ZIP_PATH}")
    except KeyError:
        print(f"Failure: CORPCODE.xml was not found inside the zip file: {ZIP_PATH}")
    except ET.ParseError as error:
        print(f"Failure: Could not parse CORPCODE.xml: {error}")
    except OSError as error:
        print(f"Failure: Could not read or write a file: {error}")


if __name__ == "__main__":
    main()
