from pathlib import Path

import pandas as pd
import streamlit as st


BASE_DIR = Path(__file__).resolve().parent
ASSETS_CSV_PATH = BASE_DIR / "data" / "processed" / "samsung_assets.csv"


def load_assets_data(csv_path):
    """Load Samsung asset data from a CSV file."""
    return pd.read_csv(csv_path)


def prepare_chart_data(assets_data):
    """Sort the data by year so the line chart is easy to read."""
    chart_data = assets_data.sort_values("year")
    return chart_data.set_index("year")


def main():
    st.title("삼성전자 자산총계 추이")

    if not ASSETS_CSV_PATH.exists():
        st.error(f"CSV file was not found: {ASSETS_CSV_PATH}")
        return

    assets_data = load_assets_data(ASSETS_CSV_PATH)

    st.dataframe(assets_data, use_container_width=True)

    chart_data = prepare_chart_data(assets_data)
    st.line_chart(chart_data["amount"])


if __name__ == "__main__":
    main()
