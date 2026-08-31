from pathlib import Path
import pandas as pd

PROJECT_DIR = Path(
    "/Users/ishita/Desktop/Financial Engineering"
)

RATE_FILE = (
    PROJECT_DIR
    / "Swap curves.xlsx"
)

print("\n" + "=" * 80)
print("NEW SWAP CURVE FILE INSPECTION")
print("=" * 80)

print("\nFile:")
print(RATE_FILE)

if not RATE_FILE.exists():
    raise FileNotFoundError(f"File not found: {RATE_FILE}")

with pd.ExcelFile(RATE_FILE) as excel:

    print("\nSheets:")
    print(excel.sheet_names)

    for sheet in excel.sheet_names:

        print("\n" + "=" * 80)
        print("SHEET:", sheet)
        print("=" * 80)

        raw = pd.read_excel(
            excel,
            sheet_name=sheet,
            header=None
        )

        print("\nDimensions:")
        print(
            raw.shape[0],
            "rows x",
            raw.shape[1],
            "columns"
        )

        print("\nFirst 30 rows:")
        print(
            raw.head(30).to_string(
                index=True,
                header=True
            )
        )

        print("\nData types:")
        print(
            raw.dtypes.to_string()
        )

        print("\nNon-null observations by column:")
        print(
            raw.notna()
            .sum()
            .to_string()
        )

        print("\nLast 10 rows:")
        print(
            raw.tail(10).to_string(
                index=True,
                header=True
            )
        )

print("\n" + "=" * 80)
print("INSPECTION COMPLETED")
print("=" * 80)