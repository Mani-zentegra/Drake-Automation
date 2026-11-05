"""
drake_import_generator.py
-------------------------
Automated Native Import (.7X5) Generator for Drake Tax 2025.

Generates official Drake Tax batch import files directly into C:\\DRAKE25\\IMPORT\\
matching the native Drake .7X5 specification (e.g., Form 8949 / Capital Gains / 1099-B).
"""

import os
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
import pandas as pd


DRAKE_IMPORT_DIR = r"C:\DRAKE25\IMPORT"


def clean_identifier(client_id: str) -> str:
    """Strip dashes, spaces, and formatting from SSN, EIN, or Client ID."""
    return re.sub(r"[^\w]", "", str(client_id)).strip()


def format_drake_date(val: Any) -> str:
    """Format dates to MMDDYYYY string as required by Drake, or preserve 'VARIOUS'."""
    if not val:
        return ""
    if isinstance(val, (datetime, pd.Timestamp)):
        return val.strftime("%m%d%Y")
    
    val_str = str(val).strip()
    if val_str.upper() in ["VARIOUS", "INHERITED"]:
        return val_str.upper()

    # Try common date formats
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d", "%m/%d/%y", "%Y%m%d", "%m%d%Y"):
        try:
            return datetime.strptime(val_str, fmt).strftime("%m%d%Y")
        except ValueError:
            pass
            
    # Remove slashes or dashes if already MMDDYYYY digits
    digits = re.sub(r"\D", "", val_str)
    if len(digits) == 8:
        return digits
    return val_str


class Drake8949ImportGenerator:
    """
    Builds native .7X5 Drake batch import files for Form 8949 (Capital Gains & Losses).
    """

    def __init__(self, ssn_or_client_id: str, import_mode: str = "Append", target_dir: str = DRAKE_IMPORT_DIR):
        """
        :param ssn_or_client_id: Client SSN or File ID (e.g. '500-00-1100' or '50000100')
        :param import_mode: 'Append' (add to existing) or 'Replace' (overwrite existing)
        :param target_dir: Path to Drake's IMPORT folder (default C:\\DRAKE25\\IMPORT)
        """
        self.client_id = clean_identifier(ssn_or_client_id)
        self.import_mode = "Replace" if import_mode.lower() == "replace" else "Append"
        self.target_dir = target_dir
        self.transactions: List[Dict[str, Any]] = []

    def add_transaction(
        self,
        description: str,
        date_acquired: Any,
        date_sold: Any,
        sales_price: float,
        cost_basis: float,
        owner: str = "T",  # 'T' for Taxpayer, 'S' for Spouse, 'J' for Joint
        adjustment_code: str = "",
        adjustment_amount: Optional[float] = None,
    ):
        """Add a single Form 8949 transaction."""
        self.transactions.append({
            "owner": owner.upper() if owner else "T",
            "description": str(description).strip(),
            "date_acquired": format_drake_date(date_acquired),
            "date_sold": format_drake_date(date_sold),
            "sales_price": round(float(sales_price), 2) if sales_price is not None else 0.0,
            "cost_basis": round(float(cost_basis), 2) if cost_basis is not None else 0.0,
            "adjustment_code": str(adjustment_code).strip() if adjustment_code else "",
            "adjustment_amount": round(float(adjustment_amount), 2) if adjustment_amount is not None else None,
        })

    def load_from_dataframe(self, df: pd.DataFrame, column_mapping: Optional[Dict[str, str]] = None):
        """
        Load transactions from a pandas DataFrame (e.g. read from Excel or CSV).
        
        Default expected columns:
          - description
          - date_acquired
          - date_sold
          - sales_price (or proceeds)
          - cost_basis
          - owner (optional, defaults to 'T')
        """
        mapping = {
            "description": "description",
            "date_acquired": "date_acquired",
            "date_sold": "date_sold",
            "sales_price": "sales_price",
            "proceeds": "sales_price",
            "cost_basis": "cost_basis",
            "basis": "cost_basis",
            "owner": "owner",
            "adjustment_code": "adjustment_code",
            "adjustment_amount": "adjustment_amount",
        }
        if column_mapping:
            mapping.update(column_mapping)

        # Normalize df column names to lowercase
        normalized_df = df.rename(columns={c: str(c).lower().strip() for c in df.columns})

        for _, row in normalized_df.iterrows():
            desc = row.get(mapping.get("description", "description"), "")
            if not desc or pd.isna(desc):
                continue

            acq = row.get(mapping.get("date_acquired", "date_acquired"), "")
            sold = row.get(mapping.get("date_sold", "date_sold"), "")
            price = row.get(mapping.get("sales_price", "sales_price"), 0)
            cost = row.get(mapping.get("cost_basis", "cost_basis"), 0)
            owner = row.get(mapping.get("owner", "owner"), "T")
            code = row.get(mapping.get("adjustment_code", "adjustment_code"), "")
            adj = row.get(mapping.get("adjustment_amount", "adjustment_amount"), None)

            self.add_transaction(
                description=desc,
                date_acquired=acq,
                date_sold=sold,
                sales_price=price,
                cost_basis=cost,
                owner=owner if pd.notna(owner) else "T",
                adjustment_code=code if pd.notna(code) else "",
                adjustment_amount=adj if pd.notna(adj) else None,
            )

    def load_from_excel(self, file_path: str, sheet_name: Any = 0, column_mapping: Optional[Dict[str, str]] = None):
        """Load transactions directly from an Excel sheet."""
        df = pd.read_excel(file_path, sheet_name=sheet_name)
        self.load_from_dataframe(df, column_mapping)

    def generate_content(self) -> str:
        """Render the complete .7X5 file content string."""
        lines = [
            "0,  , 0, 0, 0, 1040",
            "0,  , 0, 0, 0, Form 8949",
            f"0,  , 0, 0, 0, {self.import_mode}",
        ]

        # Field definitions for Drake Form 8949:
        # Field 1:  Owner ('T', 'S', 'J')
        # Field 6:  Description of property
        # Field 8:  Date acquired (MMDDYYYY)
        # Field 9:  Date sold (MMDDYYYY)
        # Field 12: Sales price / Proceeds
        # Field 13: Cost basis
        # Field 14: Adjustment code (e.g. 'W' for Wash Sale)
        # Field 15: Adjustment amount

        for idx, tx in enumerate(self.transactions, start=1):
            owner = tx["owner"]
            desc = tx["description"].replace('"', '""')
            acq = tx["date_acquired"]
            sold = tx["date_sold"]
            price = int(tx["sales_price"]) if tx["sales_price"].is_integer() else tx["sales_price"]
            cost = int(tx["cost_basis"]) if tx["cost_basis"].is_integer() else tx["cost_basis"]

            lines.append(f'8949,  ,{idx}, 1, 0, "{owner}"')
            lines.append(f'8949,  ,{idx}, 6, 0, "{desc}"')
            if acq:
                lines.append(f'8949,  ,{idx}, 8, 0, "{acq}"')
            if sold:
                lines.append(f'8949,  ,{idx}, 9, 0, "{sold}"')
            lines.append(f'8949,  ,{idx}, 12, 0, {price}')
            lines.append(f'8949,  ,{idx}, 13, 0, {cost}')

            if tx["adjustment_code"]:
                lines.append(f'8949,  ,{idx}, 14, 0, "{tx["adjustment_code"]}"')
            if tx["adjustment_amount"] is not None:
                adj = int(tx["adjustment_amount"]) if tx["adjustment_amount"].is_integer() else tx["adjustment_amount"]
                lines.append(f'8949,  ,{idx}, 15, 0, {adj}')

        return "\n".join(lines) + "\n"

    def write_import_file(self) -> str:
        """Write the .7X5 file directly to Drake's IMPORT directory."""
        if not os.path.exists(self.target_dir):
            os.makedirs(self.target_dir, exist_ok=True)

        filename = f"{self.client_id}.7X5"
        full_path = os.path.join(self.target_dir, filename)

        content = self.generate_content()
        with open(full_path, "w", encoding="ascii") as f:
            f.write(content)

        return full_path


if __name__ == "__main__":
    print("Testing Drake8949ImportGenerator...")
    gen = Drake8949ImportGenerator(ssn_or_client_id="500-00-1100", import_mode="Append")

    # Add sample transactions
    gen.add_transaction(
        description="100 sh Apple Inc (AAPL)",
        date_acquired="01/15/2024",
        date_sold="11/20/2025",
        sales_price=50000,
        cost_basis=35000,
        owner="T",
    )
    gen.add_transaction(
        description="50 sh Microsoft Corp (MSFT)",
        date_acquired="03/10/2024",
        date_sold="10/05/2025",
        sales_price=42000,
        cost_basis=30000,
        owner="T",
    )
    gen.add_transaction(
        description="1.5 Bitcoin (BTC)",
        date_acquired="05/12/2023",
        date_sold="09/14/2025",
        sales_price=75000,
        cost_basis=45000,
        owner="T",
    )

    output_file = gen.write_import_file()
    print(f"Generated file successfully: {output_file}")
    with open(output_file, "r") as f:
        print("\n--- File Content Preview ---")
        print(f.read())
