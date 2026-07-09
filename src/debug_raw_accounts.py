import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
TARGET_FILE_KEYWORDS = ["LG전자_2023", "LG디스플레이_2024"]
SEARCH_KEYWORDS = ["당기", "순이익", "순손실", "손실", "이익", "지배", "비지배", "귀속"]


def find_target_raw_json_files(raw_dir):
    """Find raw JSON files for the selected companies and years."""
    target_files = []

    for json_path in raw_dir.glob("*.json"):
        file_name = json_path.name

        for target_keyword in TARGET_FILE_KEYWORDS:
            if target_keyword in file_name:
                target_files.append(json_path)
                break

    return sorted(target_files)


def read_json_file(json_path):
    """Read one raw JSON file."""
    with json_path.open("r", encoding="utf-8") as json_file:
        return json.load(json_file)


def account_matches_keywords(account_name):
    """Check whether account_nm contains one of the search keywords."""
    for keyword in SEARCH_KEYWORDS:
        if keyword in account_name:
            return True

    return False


def print_matching_rows(json_path):
    """Print matching account rows from one raw JSON file."""
    response_data = read_json_file(json_path)
    rows = response_data.get("list", [])

    print(f"\nFile: {json_path.name}")

    for row in rows:
        account_name = row.get("account_nm", "")

        if not account_matches_keywords(account_name):
            continue

        print(
            " | ".join(
                [
                    f"file_name={json_path.name}",
                    f"bsns_year={row.get('bsns_year', '')}",
                    f"sj_nm={row.get('sj_nm', '')}",
                    f"account_nm={account_name}",
                    f"thstrm_amount={row.get('thstrm_amount', '')}",
                    f"ord={row.get('ord', '')}",
                ]
            )
        )


def main():
    target_files = find_target_raw_json_files(RAW_DIR)

    if not target_files:
        print(f"No target raw JSON files found in {RAW_DIR}")
        return

    for json_path in target_files:
        print_matching_rows(json_path)


if __name__ == "__main__":
    main()
