#!/usr/bin/env python3
"""
Finance CSV Importer
====================
Parses activity statements from TD, AMEX, and WealthSimple and stores
them in a local JSON database. Fully idempotent — safe to re-run.

Usage:
    python3 import.py <file1.csv> [file2.xls] [...]
    python3 import.py --dir ~/Downloads   # auto-detects all bank CSVs in a folder

The script auto-detects which institution each file belongs to.
"""

import sys
import os
import json
import hashlib
import argparse
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
TRANSACTIONS_FILE = DATA_DIR / "transactions.json"
CATEGORIES_FILE = DATA_DIR / "categories.json"

DEFAULT_CATEGORIES = [
    "Restaurant", "Groceries", "Investment", "Income", "Utilities", "Uncategorized", "Transport", "Retail"
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CATEGORIES_FILE.exists():
        save_json(CATEGORIES_FILE, DEFAULT_CATEGORIES)
        print(f"✓ Created categories file with {len(DEFAULT_CATEGORIES)} default categories.")
    if not TRANSACTIONS_FILE.exists():
        save_json(TRANSACTIONS_FILE, {})
        print(f"✓ Created transactions file.")

def load_json(path, default):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)

def make_id(source: str, date: str, description: str, amount: float) -> str:
    """Deterministic transaction ID for deduplication."""
    key = f"{source}|{date}|{description.strip()}|{amount:.2f}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]

def parse_amount(val) -> "float | None":
    """Parse amounts like '$1,234.56', '-$50.00', '1234.56'."""
    if val is None:
        return None
    s = str(val).replace(",", "").replace("$", "").strip()
    try:
        return round(float(s), 2)
    except ValueError:
        return None

def parse_date(val, fmt=None) -> "str | None":
    """Return ISO date string YYYY-MM-DD or None."""
    if not val or (isinstance(val, float)):
        return None
    s = str(val).strip()
    formats = [fmt] if fmt else []
    formats += [
        "%Y-%m-%d", "%d %b. %Y", "%d %b %Y",
        "%B %d, %Y", "%m/%d/%Y", "%d/%m/%Y",
    ]
    for f in formats:
        try:
            return datetime.strptime(s, f).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
    return None

def convert_xls_to_csv(xls_path: str) -> str:
    """Use LibreOffice to convert .xls to .csv, return path to csv."""
    tmp_dir = tempfile.mkdtemp()
    # Try soffice directly first (works on most systems with LibreOffice installed)
    result = subprocess.run(
        ["soffice", "--headless", "--convert-to", "csv",
         str(xls_path), "--outdir", tmp_dir],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Could not convert {xls_path} to CSV.\n"
            "Make sure LibreOffice is installed: https://www.libreoffice.org/download/\n"
            f"Details: {result.stderr}"
        )
    csv_name = Path(xls_path).stem + ".csv"
    return str(Path(tmp_dir) / csv_name)


# ── Institution Detectors ─────────────────────────────────────────────────────

def detect_institution(path: Path, lines: list[str]) -> "str | None":
    """Return 'amex', 'td', 'wealthsimple', or None."""
    name = path.name.lower()
    head = "\n".join(lines[:15]).lower()

    if "summary.xls" in name or "summary.csv" in name:
        if "american express" in head or "cobalt" in head or "amex" in head:
            return "amex"
    if "transaction details" in head and "american express" in head:
        return "amex"
    if "activities-export" in name or "transaction_date" in head and "account_type" in head:
        return "wealthsimple"
    if "accountactivity" in name:
        # Distinguish chequing (YYYY-MM-DD) from credit (MM/DD/YYYY) by date format
        first = lines[0] if lines else ""
        if re.match(r"\d{2}/\d{2}/\d{4}", first):
            return "td_credit"
        return "td_chequing"
    # Try content-based detection
    if "account_type" in head and "activity_type" in head:
        return "wealthsimple"
    if "american express" in head:
        return "amex"
    # TD chequing: headerless CSV, YYYY-MM-DD dates
    if re.match(r"\d{4}-\d{2}-\d{2}", lines[0] if lines else ""):
        parts = lines[0].split(",")
        if len(parts) == 5:
            return "td_chequing"
    # TD credit: headerless CSV, MM/DD/YYYY dates
    if re.match(r"\d{2}/\d{2}/\d{4}", lines[0] if lines else ""):
        parts = lines[0].split(",")
        if len(parts) == 5:
            return "td_credit"
    return None


# ── Parsers ───────────────────────────────────────────────────────────────────

def parse_amex(path: Path) -> list[dict]:
    """
    AMEX Cobalt XLS/CSV export.
    Header rows 0–10 are metadata; row 11 is the actual column header.
    Columns: Date, Date Processed, Description, Amount, ...
    Positive amount = charge, negative = credit/payment.
    """
    import csv

    csv_path = path
    tmp_csv = None
    if path.suffix.lower() == ".xls":
        tmp_csv = convert_xls_to_csv(str(path))
        csv_path = Path(tmp_csv)

    rows = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = list(csv.reader(f))

    # Find the header row (contains "Date" and "Description")
    header_idx = None
    for i, row in enumerate(reader):
        if row and row[0].strip().lower() == "date" and any("description" in c.lower() for c in row):
            header_idx = i
            break

    if header_idx is None:
        print(f"  ⚠ Could not find header row in {path.name}")
        return []

    header = [c.strip().lower().replace(" ", "_") for c in reader[header_idx]]
    transactions = []

    for row in reader[header_idx + 1:]:
        if not row or not row[0].strip():
            continue
        rec = dict(zip(header, row))
        date = parse_date(rec.get("date", "").strip())
        if not date:
            continue
        description = rec.get("description", "").strip()
        amount_raw = rec.get("amount", "").strip()
        amount = parse_amount(amount_raw)
        if amount is None:
            continue

        # Positive = charge (money out), negative = payment/credit (money in)
        is_debit = amount > 0
        is_transfer = "payment received" in description.lower()

        transactions.append({
            "id": make_id("amex", date, description, amount),
            "date": date,
            "description": description,
            "amount": abs(amount),
            "type": "credit" if is_debit else "debit",  # credit card: charge = outflow
            "direction": "debit" if is_debit else "credit",
            "account": "amex_cobalt",
            "institution": "AMEX",
            "is_transfer": is_transfer,
            "category": None,
            "notes": "",
        })

    if tmp_csv:
        os.unlink(tmp_csv)

    return transactions


def parse_td(path: Path) -> list[dict]:
    """
    TD Chequing account activity CSV.
    No headers. Columns: date, description, debit, credit, balance
    """
    import csv

    transactions = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 3:
                continue
            date = parse_date(row[0].strip())
            if not date:
                continue
            description = row[1].strip() if len(row) > 1 else ""
            debit = parse_amount(row[2]) if len(row) > 2 else None
            credit = parse_amount(row[3]) if len(row) > 3 else None

            # Determine transfer flags
            desc_lower = description.lower()
            is_transfer = any(kw in desc_lower for kw in [
                "amex", "td visa", "e-tfr", "e-transfer",
                "ws investments", "wealthsimple", "preauth pymt"
            ])
            is_investment = "ws investments" in desc_lower

            if debit:
                transactions.append({
                    "id": make_id("td_chequing", date, description, -debit),
                    "date": date,
                    "description": description,
                    "amount": debit,
                    "direction": "debit",
                    "account": "td_chequing",
                    "institution": "TD",
                    "is_transfer": is_transfer,
                    "is_investment": is_investment,
                    "category": None,
                    "notes": "",
                })
            if credit:
                # Detect income (payroll) and incoming e-transfers
                is_income = any(kw in desc_lower for kw in ["pay", "payroll", "amazon developm", "rit", "tax refund"])
                transactions.append({
                    "id": make_id("td_chequing", date, description, credit),
                    "date": date,
                    "description": description,
                    "amount": credit,
                    "direction": "credit",
                    "account": "td_chequing",
                    "institution": "TD",
                    "is_transfer": is_transfer and not is_income,
                    "is_investment": False,
                    "category": "Income" if is_income else None,
                    "notes": "",
                })

    return transactions

def parse_td_credit(path: Path) -> list[dict]:
    """
    TD Credit Card activity CSV.
    No headers. Columns: date (MM/DD/YYYY), description, charge, payment, balance
    Charge = money out (debit), payment = money in (credit).
    """
    import csv

    transactions = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 3:
                continue
            date = parse_date(row[0].strip(), fmt="%m/%d/%Y")
            if not date:
                continue
            description = row[1].strip() if len(row) > 1 else ""
            charge = parse_amount(row[2]) if len(row) > 2 else None
            payment = parse_amount(row[3]) if len(row) > 3 else None

            desc_lower = description.lower()
            is_transfer = any(kw in desc_lower for kw in [
                "preauthorized payment", "payment received", "online payment"
            ])

            if charge:
                transactions.append({
                    "id": make_id("td_credit", date, description, -charge),
                    "date": date,
                    "description": description,
                    "amount": charge,
                    "direction": "debit",
                    "account": "td_credit",
                    "institution": "TD",
                    "is_transfer": is_transfer,
                    "category": None,
                    "categories": [],
                    "notes": "",
                })
            if payment:
                transactions.append({
                    "id": make_id("td_credit", date, description, payment),
                    "date": date,
                    "description": description,
                    "amount": payment,
                    "direction": "credit",
                    "account": "td_credit",
                    "institution": "TD",
                    "is_transfer": is_transfer,
                    "category": None,
                    "categories": [],
                    "notes": "",
                })

    return transactions


def parse_wealthsimple(path: Path) -> list[dict]:
    """
    WealthSimple activity export CSV.
    Columns: transaction_date, settlement_date, account_id, account_type,
             activity_type, activity_sub_type, direction, symbol, name,
             currency, quantity, unit_price, commission, net_cash_amount

    We skip investment trades (buy/sell) and keep:
    - Chequing transactions (deposits, withdrawals, transfers)
    - Credit card charges
    - Interest
    """
    import csv

    SKIP_TYPES = {"buy", "sell", "dividend", "deposit_investment"}
    SKIP_SUBTYPES = {"buy", "sell"}

    transactions = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Skip malformed rows (e.g. footer "As of ...")
            date = parse_date(row.get("transaction_date", "").strip())
            if not date:
                continue

            activity = (row.get("activity_type") or "").strip().lower()
            sub_type = (row.get("activity_sub_type") or "").strip().lower()

            # Skip investment activity
            if activity in SKIP_TYPES or sub_type in SKIP_SUBTYPES:
                continue
            if row.get("symbol") and str(row.get("symbol")).strip():
                continue  # has a ticker symbol = investment

            amount = parse_amount(row.get("net_cash_amount"))
            if amount is None:
                continue

            account_type = (row.get("account_type") or "").strip()
            account_id = (row.get("account_id") or "").strip()
            description = activity.replace("_", " ").title()
            if row.get("name") and str(row.get("name")).strip() not in ("nan", ""):
                description = str(row["name"]).strip()

            direction = "credit" if amount > 0 else "debit"
            is_transfer = activity in {"transfer", "deposit", "withdrawal"}
            is_income = activity in {"payroll", "direct_deposit", "interest"}

            transactions.append({
                "id": make_id("wealthsimple", date, description, amount),
                "date": date,
                "description": description,
                "amount": abs(amount),
                "direction": direction,
                "account": f"ws_{account_type.lower().replace(' ', '_')}",
                "institution": "WealthSimple",
                "is_transfer": is_transfer,
                "category": "Income" if is_income else None,
                "notes": "",
            })

    return transactions


# ── Main Import Logic ─────────────────────────────────────────────────────────

PARSERS = {
    "amex": parse_amex,
    "td_chequing": parse_td,
    "td_credit": parse_td_credit,
    "wealthsimple": parse_wealthsimple,
}

INSTITUTION_LABELS = {
    "amex": "AMEX Cobalt",
    "td_chequing": "TD Chequing",
    "td_credit": "TD Credit",
    "wealthsimple": "WealthSimple",
}


def import_file(path: Path, db: dict) -> tuple[int, int]:
    """
    Import a single file. Returns (added, skipped) counts.
    """
    path = Path(path)
    if not path.exists():
        print(f"  ✗ File not found: {path}")
        return 0, 0

    # Read first few lines for detection
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            lines = [f.readline().strip() for _ in range(20)]
    except Exception:
        lines = []

    institution = detect_institution(path, lines)

    if institution is None:
        print(f"  ⚠ Could not detect institution for {path.name}. Skipping.")
        print("    Rename file to include: 'amex', 'td', or 'wealthsimple'")
        return 0, 0

    print(f"  → Detected: {INSTITUTION_LABELS.get(institution, institution)} ({path.name})")

    parser = PARSERS[institution]
    try:
        transactions = parser(path)
    except Exception as e:
        print(f"  ✗ Parse error: {e}")
        import traceback; traceback.print_exc()
        return 0, 0

    added = 0
    skipped = 0
    for tx in transactions:
        if tx["id"] in db:
            skipped += 1
        else:
            db[tx["id"]] = tx
            added += 1

    print(f"     Added {added} new transactions, skipped {skipped} duplicates.")
    return added, skipped



def auto_categorize(db: dict, model: str = "llama3", batch_size: int = 40, overwrite: bool = False):
    """
    Use a local Ollama model to auto-categorize uncategorized transactions.
    Sends transactions in batches to minimize model calls.
    """
    import urllib.request
    import urllib.error

    categories = DEFAULT_CATEGORIES

    to_tag = [
        tx for tx in db.values()
        if not tx.get("is_transfer")
        and tx.get("direction") == "debit"
        and (overwrite or not tx.get("categories"))
    ]

    if not to_tag:
        print("✓ No uncategorized transactions to process.")
        return

    print(f"\nAuto-categorizing {len(to_tag)} transactions using '{model}'...")
    print(f"  Categories: {', '.join(categories)}\n")

    system_prompt = f"""You are a personal finance categorizer.
Given a list of bank transactions, assign 1-3 categories to each one from this list:
{json.dumps(categories)}
Rules:
- Only use categories from the list above. Never invent new ones.
- Assign the most specific category that fits.
- You may assign multiple categories if genuinely appropriate.
- Respond ONLY with a JSON object mapping each transaction id to an array of category strings.
- No explanation, no markdown, no extra text. Pure JSON only.

Examples of correct categorizations:
{{
  "tx001": {{"description": "TIM HORTONS", "amount": 4.75, "categories": ["Restaurant"]}},
  "tx002": {{"description": "Amazon.ca _V", "amount": 87.23, "categories": ["Retail therapy"]}},
  "tx003": {{"description": "UBER* TRIP", "amount": 14.50, "categories": ["Transport"]}},
  "tx003": {{"description": "Presto", "amount": 14.50, "categories": ["Transport"]}},
  "tx005": {{"description": "Fit4less", "amount": 20.99, "categories": ["Self Improvement"]}},
  "tx008": {{"description": "SHOPPERS DRUG MART", "amount": 34.12, "categories": ["Retail Therapy"]}},
  "tx009": {{"description": "AZUL", "amount": 56.99, "categories": ["Restaurant"]}},
  "tx010": {{"description": "SSV TO: 17916240345", "amount": 45.00, "categories": ["Miscellaneous"]}},
  "tx011": {{"description": "E Transfer", "amount": 29.99, "categories": ["Family"]}}
}}
"""

    updated = 0
    failed = 0
    batches = [to_tag[i:i+batch_size] for i in range(0, len(to_tag), batch_size)]

    for i, batch in enumerate(batches):
        print(f"  Batch {i+1}/{len(batches)} ({len(batch)} transactions)...", end=" ", flush=True)

        tx_list = [{"id": tx["id"], "description": tx["description"], "amount": tx["amount"]} for tx in batch]
        user_prompt = f"Categorize these transactions:\n{json.dumps(tx_list, indent=2)}"

        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.1},
        }).encode()

        try:
            req = urllib.request.Request(
                "http://localhost:11434/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read())
            raw = result["message"]["content"].strip()

            # Strip markdown code fences if model wrapped the JSON
            if raw.startswith("```"):
                raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()

            assignments = json.loads(raw)

            batch_tagged = 0
            for tx in batch:
                if tx["id"] in assignments:
                    cats = assignments[tx["id"]]
                    if isinstance(cats, str):
                        cats = [cats]
                    cats = [c for c in cats if c in categories]
                    if cats:
                        db[tx["id"]]["categories"] = cats
                        db[tx["id"]]["category"] = cats[0]
                        updated += 1
                        batch_tagged += 1

            print(f"✓ tagged {batch_tagged}")

        except urllib.error.URLError:
            print(f"\n✗ Could not reach Ollama. Make sure it's running: ollama serve")
            failed += len(batch)
            break
        except json.JSONDecodeError as e:
            print(f"✗ Bad JSON from model — try a different model or reduce batch size")
            failed += len(batch)
            continue
        except Exception as e:
            print(f"✗ Error: {e}")
            failed += len(batch)
            continue

    print(f"\n{chr(9472)*40}")
    print(f"✓ Auto-categorized {updated} transactions.")
    if failed:
        print(f"⚠  {failed} transactions failed — try again or tag manually in the dashboard.")


def main():
    parser = argparse.ArgumentParser(
        description="Import bank CSV/XLS files into the finance dashboard database."
    )
    parser.add_argument("files", nargs="*", help="CSV or XLS files to import")
    parser.add_argument("--dir", "-d", type=str, help="Directory to scan for CSV/XLS files")
    parser.add_argument("--reset", action="store_true", help="Wipe the database before importing (dangerous!)")
    parser.add_argument("--categorize", action="store_true", help="Auto-categorize after importing using Ollama")
    parser.add_argument("--categorize-only", action="store_true", help="Skip import, just run auto-categorization")
    parser.add_argument("--model", type=str, default="llama3", help="Ollama model to use (default: llama3)")
    parser.add_argument("--overwrite", action="store_true", help="Re-categorize already-categorized transactions")
    args = parser.parse_args()

    ensure_data_dir()

    db = load_json(TRANSACTIONS_FILE, {})

    if args.reset:
        confirm = input("⚠ This will delete all transactions. Type 'yes' to confirm: ")
        if confirm.strip().lower() == "yes":
            db = {}
            print("Database cleared.")
        else:
            print("Aborted.")
            return

    # ── Import ──
    if not args.categorize_only:
        files = list(args.files or [])
        if args.dir:
            d = Path(args.dir)
            files += list(d.glob("*.csv")) + list(d.glob("*.xls")) + list(d.glob("*.xlsx"))

        if not files:
            print("No files provided. Usage:")
            print("  python3 import.py statement.csv [another.xls] ...")
            print("  python3 import.py --dir ~/Downloads")
            print("  python3 import.py --categorize-only --model llama3")
            return

        print(f"\nImporting {len(files)} file(s)...\n")
        total_added = 0
        total_skipped = 0
        for f in files:
            added, skipped = import_file(Path(f), db)
            total_added += added
            total_skipped += skipped

        save_json(TRANSACTIONS_FILE, db)
        print(f"\n{'─'*40}")
        print(f"✓ Done. {total_added} added, {total_skipped} skipped.")
        print(f"✓ Database: {len(db)} total transactions.")
        print(f"✓ Saved to {TRANSACTIONS_FILE}")

    # ── Auto-categorize ──
    if args.categorize or args.categorize_only:
        auto_categorize(db, model=args.model, overwrite=args.overwrite)
        save_json(TRANSACTIONS_FILE, db)
        print(f"✓ Saved to {TRANSACTIONS_FILE}")

    print(f"\nRun the dashboard:")
    print(f"  python3 {SCRIPT_DIR}/dashboard.py")


if __name__ == "__main__":
    main()