import re
from datetime import datetime, date

MONTH_NAME_MAP = {
    'jan': 1, 'january': 1,
    'feb': 2, 'february': 2,
    'mar': 3, 'march': 3,
    'apr': 4, 'april': 4,
    'may': 5,
    'jun': 6, 'june': 6,
    'jul': 7, 'july': 7,
    'aug': 8, 'august': 8,
    'sep': 9, 'september': 9,
    'oct': 10, 'october': 10,
    'nov': 11, 'november': 11,
    'dec': 12, 'december': 12
}

def format_to_drake_date(val):
    """
    Converts any incoming date format (e.g. Zoho Creator '05-Dec-1998', ISO '1998-12-05',
    '12/05/1998', 'December 5, 1998', '12051998', timestamps) into Drake Tax supported
    standard format: MM-DD-YYYY (e.g. '12-05-1998').
    
    Drake Tax rejects slashes ('/') with 'INVALID character for field type: Date'.
    Drake requires hyphens ('-') e.g. '12-05-1998'.
    """
    if val is None:
        return ""
    if isinstance(val, (datetime, date)):
        return val.strftime("%m-%d-%Y")

    s = str(val).strip()
    if not s or s.lower() in ("none", "null", "n/a", "undefined"):
        return ""

    # Strip time portions if present e.g. "05-Dec-1998 00:00:00" or "1998-12-05T00:00:00Z"
    s = re.sub(r'T\d{2}:\d{2}:\d{2}.*$', '', s)
    s = re.sub(r'\s+\d{1,2}:\d{2}(:\d{2})?(\s*[APap][Mm])?.*$', '', s).strip()

    result = None

    # Handle pure 8-digit strings like '12051998' or '19981205'
    if s.isdigit() and len(s) == 8:
        # Check if YYYYMMDD
        if int(s[:4]) >= 1900 and 1 <= int(s[4:6]) <= 12 and 1 <= int(s[6:]) <= 31:
            result = f"{s[4:6]}-{s[6:]}-{s[:4]}"
        else:
            # Assume MMDDYYYY
            m, d, y = int(s[:2]), int(s[2:4]), int(s[4:])
            if 1 <= m <= 12 and 1 <= d <= 31 and 1900 <= y <= 2100:
                result = f"{m:02d}-{d:02d}-{y:04d}"

    # Regex pattern for DD-Mon-YYYY e.g. '05-Dec-1998', '5-DEC-1998', '05/Dec/1998', '5 Dec 1998'
    if not result:
        m_alpha = re.match(r'^(\d{1,2})[-/\s]([A-Za-z]+)[-/\s](\d{2,4})$', s)
        if m_alpha:
            day_str, mon_str, year_str = m_alpha.groups()
            mon_lower = mon_str.lower()
            if mon_lower in MONTH_NAME_MAP:
                m = MONTH_NAME_MAP[mon_lower]
                d = int(day_str)
                y = int(year_str)
                if y < 100:
                    y += 1900 if y > 30 else 2000
                result = f"{m:02d}-{d:02d}-{y:04d}"

    # Regex pattern for Mon-DD-YYYY or "December 5, 1998"
    if not result:
        m_alpha2 = re.match(r'^([A-Za-z]+)[-/\s](\d{1,2}),?[-/\s](\d{2,4})$', s)
        if m_alpha2:
            mon_str, day_str, year_str = m_alpha2.groups()
            mon_lower = mon_str.lower()
            if mon_lower in MONTH_NAME_MAP:
                m = MONTH_NAME_MAP[mon_lower]
                d = int(day_str)
                y = int(year_str)
                if y < 100:
                    y += 1900 if y > 30 else 2000
                result = f"{m:02d}-{d:02d}-{y:04d}"

    # Common standard datetime formats
    if not result:
        formats = [
            '%d-%b-%Y', '%d-%B-%Y',
            '%d-%b-%y', '%d-%B-%y',
            '%Y-%m-%d',
            '%m/%d/%Y', '%m/%d/%y',
            '%m-%d-%Y', '%d-%m-%Y',
            '%B %d, %Y', '%b %d, %Y',
            '%B %d %Y', '%b %d %Y',
            '%d %b %Y', '%d %B %Y',
            '%Y/%m/%d'
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(s, fmt)
                result = dt.strftime("%m-%d-%Y")
                break
            except ValueError:
                pass
            try:
                dt = datetime.strptime(s.title(), fmt)
                result = dt.strftime("%m-%d-%Y")
                break
            except ValueError:
                pass

    # If date had slashes like 12/05/1998, replace with hyphens 12-05-1998
    if not result and "/" in s:
        parts = s.split("/")
        if len(parts) == 3:
            result = f"{parts[0].strip().zfill(2)}-{parts[1].strip().zfill(2)}-{parts[2].strip()}"

    final_val = result if result else s
    # Ensure any remaining slashes are replaced with hyphens for Drake compatibility
    return final_val.replace("/", "-")
