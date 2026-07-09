from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
FINANCIAL_STATEMENT_PATH = BASE_DIR / "data" / "processed" / "financial_statement.csv"


def reset_financial_statement():
    """Delete the processed financial statement CSV if it exists."""
    if FINANCIAL_STATEMENT_PATH.exists():
        FINANCIAL_STATEMENT_PATH.unlink()
        print(f"Deleted: {FINANCIAL_STATEMENT_PATH}")
        return

    print(f"Nothing to delete. File does not exist: {FINANCIAL_STATEMENT_PATH}")


if __name__ == "__main__":
    reset_financial_statement()
