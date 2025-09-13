import csv
from io import StringIO
from decimal import Decimal
from datetime import datetime

REQUIRED_HEADERS = {
    "Date Added", "Item Name", "SKU", "Available", "On-Transit",
    "Total", "Reorder Point", "Price", "Total Value", "Last Changed"
}

# accept common date/time formats (minute precision preferred)
DATE_FORMATS = [
    "%Y/%m/%d %H:%M",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
]


def _parse_date(s):
    s = (s or "").strip()
    if not s:
        return None
    # try explicit formats
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # try ISO (supports "YYYY-MM-DDTHH:MM")
    try:
        return datetime.fromisoformat(s.replace("Z", ""))
    except Exception:
        return None


def parse_csv(file_storage):
    """
    Parses uploaded CSV (new header set) and returns:
      {"rows":[{name,sku,available,on_transit,reorder_point,price,date_added,last_changed},...], "errors":[...]}
    We recompute 'total'; we set on-hand = available (allocations assumed 0).
    """
    content = file_storage.stream.read().decode("utf-8")
    reader = csv.reader(StringIO(content))
    try:
        header = next(reader)
    except StopIteration:
        return {"rows": [], "errors": ["Empty file."]}

    header_map = {h.strip(): i for i, h in enumerate(header)}
    missing = [h for h in REQUIRED_HEADERS if h not in header_map]
    if missing:
        return {"rows": [], "errors": [f"Missing required columns: {missing}. Found: {header}"]}

    idx = header_map
    rows, errors, line_no = [], [], 1
    for raw in reader:
        line_no += 1
        try:
            name = raw[idx["Item Name"]].strip()
            sku = raw[idx["SKU"]].strip()
            available = int((raw[idx["Available"]] or "0").replace(",", ""))
            on_transit = int((raw[idx["On-Transit"]] or "0").replace(",", ""))
            reorder_point = int((raw[idx["Reorder Point"]] or "0").replace(",", ""))
            price = Decimal(str(raw[idx["Price"]] or "0").replace(",", ""))

            # Dates with times (kept naive-local; converted to UTC in app commit)
            date_added = _parse_date(raw[idx["Date Added"]])
            last_changed = _parse_date(raw[idx["Last Changed"]])

            # optional: verify total consistency; if mismatch, just note it
            try:
                total_in_file = int((raw[idx["Total"]] or "0").replace(",", ""))
            except Exception:
                total_in_file = available + on_transit
            if (available + on_transit) != total_in_file:
                errors.append(f"Line {line_no}: Total != Available + On-Transit; using recomputed value.")

            rows.append({
                "name": name,
                "sku": sku,
                "available": available,
                "on_transit": on_transit,
                "reorder_point": reorder_point,
                "price": price,
                "date_added": date_added,
                "last_changed": last_changed,
            })
        except Exception as e:
            errors.append(f"Line {line_no}: {e}")

    return {"rows": rows, "errors": errors}
