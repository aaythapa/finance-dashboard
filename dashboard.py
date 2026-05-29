#!/usr/bin/env python3
"""
Finance Dashboard Server
========================
Serves the dashboard at http://localhost:8765 and opens it in your browser.
Also provides a simple REST API so the dashboard can read/write data.

Usage:
    python3 dashboard.py
    python3 dashboard.py --port 9000
"""

import sys
import os
import json
import argparse
import webbrowser
import threading
import time
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
TRANSACTIONS_FILE = DATA_DIR / "transactions.json"
CATEGORIES_FILE = DATA_DIR / "categories.json"
DASHBOARD_HTML = SCRIPT_DIR / "dashboard.html"

DEFAULT_CATEGORIES = [
    "Restaurant", "Groceries", "Investment", "Income",
    "Friends", "Family", "Myself", "Girlfriend",
    "Retail Therapy", "Self Improvement", "Transport",
    "Subscriptions", "Utilities", "Transfer", "Uncategorized"
]


def load_json(path, default):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress server logs

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, content):
        body = content.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            if DASHBOARD_HTML.exists():
                self.send_html(DASHBOARD_HTML.read_text())
            else:
                self.send_json({"error": "dashboard.html not found"}, 404)

        elif path == "/api/transactions":
            db = load_json(TRANSACTIONS_FILE, {})
            self.send_json(list(db.values()))

        elif path == "/api/categories":
            cats = load_json(CATEGORIES_FILE, DEFAULT_CATEGORIES)
            self.send_json(cats)

        else:
            self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if path == "/api/transactions/categorize":
            # Bulk categorize: { updates: [{id, category, notes?}] }
            db = load_json(TRANSACTIONS_FILE, {})
            updated = 0
            for upd in body.get("updates", []):
                tx_id = upd.get("id")
                if tx_id and tx_id in db:
                    db[tx_id]["category"] = upd.get("category")
                    if "notes" in upd:
                        db[tx_id]["notes"] = upd["notes"]
                    updated += 1
            save_json(TRANSACTIONS_FILE, db)
            self.send_json({"updated": updated})

        elif path == "/api/categories":
            # Add a new category
            name = body.get("name", "").strip()
            if not name:
                self.send_json({"error": "name required"}, 400)
                return
            cats = load_json(CATEGORIES_FILE, DEFAULT_CATEGORIES)
            if name not in cats:
                cats.append(name)
                save_json(CATEGORIES_FILE, cats)
            self.send_json(cats)

        elif path == "/api/categories/delete":
            name = body.get("name", "").strip()
            cats = load_json(CATEGORIES_FILE, DEFAULT_CATEGORIES)
            cats = [c for c in cats if c != name]
            save_json(CATEGORIES_FILE, cats)
            self.send_json(cats)

        elif path == "/api/transactions/flag_transfer":
            # Manually flag a transaction as transfer
            db = load_json(TRANSACTIONS_FILE, {})
            tx_id = body.get("id")
            if tx_id and tx_id in db:
                db[tx_id]["is_transfer"] = body.get("is_transfer", True)
                save_json(TRANSACTIONS_FILE, db)
                self.send_json({"ok": True})
            else:
                self.send_json({"error": "not found"}, 404)

        else:
            self.send_json({"error": "Not found"}, 404)


def open_browser(port, delay=1.0):
    time.sleep(delay)
    webbrowser.open(f"http://localhost:{port}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    # Ensure data dir exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CATEGORIES_FILE.exists():
        save_json(CATEGORIES_FILE, DEFAULT_CATEGORIES)
    if not TRANSACTIONS_FILE.exists():
        save_json(TRANSACTIONS_FILE, {})

    if not DASHBOARD_HTML.exists():
        print(f"✗ dashboard.html not found at {DASHBOARD_HTML}")
        print("  Make sure all files are in the same directory.")
        sys.exit(1)

    server = HTTPServer(("localhost", args.port), DashboardHandler)

    if not args.no_browser:
        t = threading.Thread(target=open_browser, args=(args.port,), daemon=True)
        t.start()

    print(f"\n{'─'*45}")
    print(f"  💰 Finance Dashboard")
    print(f"{'─'*45}")
    print(f"  URL:  http://localhost:{args.port}")
    print(f"  Data: {DATA_DIR}")
    print(f"{'─'*45}")
    print(f"  Press Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\nServer stopped.")


if __name__ == "__main__":
    main()
