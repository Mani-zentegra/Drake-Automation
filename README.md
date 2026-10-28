# Drake-Automation

Automated Drake Tax 2025 extraction and injection tool for:
1. **Excel Personal Tax Organizer**:
   - Demographics & Name/Address (Screen 1)
   - Dependents (Screen 2 with Item Detail)
2. **PDF Tax Packet**:
   - W-2 Wages
   - 1099-R (Retirement distributions)
   - SSA-1099 (Social Security benefits)
   - 1099-INT, 1099-DIV, 1098, 5498, and 1099-B

## Features
- **Fast Windows UIA & COM Automation**: Uses direct `ValuePattern.SetValue` and PID-filtered window traversal.
- **Two-Way Split Screen UI**: Side-by-side interactive document inspection and form review.
- **Packet History Management**: Instant switching between analyzed tax packets.
- **Safe Alert Dismissal**: Automatically bypasses non-critical e-file warnings without interrupting entry.

## Running the Application
```powershell
cd Tax_Extraction_Tool
python app.py
```
Open your browser to: [http://127.0.0.1:5050](http://127.0.0.1:5050)
