# 💰 Finance Dashboard

A personal finance tracker that imports your TD, AMEX, and WealthSimple statements into a local dashboard where you can visualize and categorize your spending. Everything runs on your computer — no accounts, no cloud, no subscriptions.

---

## Before You Start

You'll need to install a few things. Don't worry — each step has clear instructions and you only do this once.

---

## Step 1 — Install Python

Python is the programming language this tool runs on.

1. Go to **https://www.python.org/downloads/**
2. Click the yellow **Download Python** button
3. Open the downloaded file and follow the installer
4. ✅ On the first screen of the installer, make sure to check **"Add Python to PATH"** before clicking Install

To verify it worked, open **Terminal** (Mac) or **Command Prompt** (Windows) and type:
```
python3 --version
```
You should see something like `Python 3.12.0`. Any version 3.10 or higher is fine.

> **How to open Terminal on Mac:** Press `Command + Space`, type `Terminal`, hit Enter.

---

## Step 2 — Install Git

Git is used to download this project from GitHub.

**Mac:**
1. Open Terminal
2. Type `git --version` and press Enter
3. If Git isn't installed, a popup will appear asking you to install developer tools — click **Install** and follow the prompts

**Windows:**
1. Go to **https://git-scm.com/download/windows**
2. Download and run the installer, clicking Next through all the defaults

---

## Step 3 — Download This Project

Open Terminal and run these two commands one at a time:

```
git clone https://github.com/YOUR_USERNAME/finance-dashboard.git
```
```
cd finance-dashboard
```

This downloads all the files into a folder called `finance-dashboard` and moves you into it.

---

## Step 4 — Install Ollama (OPTIONAL - for auto-categorization)

Ollama lets the dashboard automatically categorize your transactions using AI running entirely on your computer.

1. Go to **https://ollama.com/download**
2. Download and install the version for your operating system
3. Open Terminal and run:
```
ollama pull mistral
```
This downloads the AI model (about 4GB — only needed once).

> **Note:** Ollama is optional. You can skip this step and categorize transactions manually in the dashboard instead.

---

## Step 5 — Download Your Bank Statements

Each month, download your statements as CSV files from each bank's website. Here's where to find them:

| Bank | Account | Instructions |
|---|---|---|
| **TD** | Chequing | Log into EasyWeb → My Accounts → select account → Download → CSV |
| **AMEX** | Cobalt | Log into amex.com → Statements & Activity → Download → CSV |
| **WealthSimple** | Chequing & Credit | Log into wealthsimple.com → Activity → Export CSV |

Save all the files somewhere easy to find, like a folder called `statements` in your Downloads.

---

## Every Month — Import & View

### 1. Import your statements

Open Terminal, navigate to the project folder, and run:

```
cd finance-dashboard
python3 import.py --dir ~/Downloads/statements
```

Replace `~/Downloads/statements` with wherever you saved your CSV files.

It's safe to run this multiple times — duplicate transactions are automatically skipped.

### 2. Auto-categorize (OPTIONAL - requires Ollama)

```
python3 import.py --categorize-only --model mistral
```

This uses AI to automatically tag your transactions with categories like Restaurant, Groceries, Transport, etc. You can then review and adjust them in the dashboard.

### 3. Open the dashboard

```
python3 dashboard.py
```

Your browser will open automatically at `http://localhost:8765`. Press `Ctrl+C` in Terminal when you're done to shut it down.

---

## Dashboard Features

### Overview
- Monthly totals for spending, income, and net savings
- Daily spending chart
- Spending breakdown by category
- Income vs spending across the last 6 months
- Recent transactions with uncategorized ones shown first

### Transactions
- Search and filter by month, account, category, or direction
- Click **+ tag** on any transaction to assign a category
- You can assign multiple categories to one transaction
- Toggle to hide internal transfers (credit card payments, e-transfers between your own accounts)

### Categories
- Add and remove categories at any time
- Spending breakdown chart by category for the current month

---

## Categories

The AI auto-categorizer will assign these categories based on the merchant name:

| Category | Examples |
|---|---|
| Restaurant | Tim Hortons, Uber Eats, DoorDash, any restaurant |
| Groceries | Loblaws, Metro, No Frills, Costco |
| Transport | Uber, TTC Presto, parking |
| Gas | Shell, Esso, Petro-Canada |
| Subscriptions | Netflix, Spotify, iCloud, Adobe |
| Shopping | Amazon, retail stores |
| Health & Pharmacy | Shoppers Drug Mart, gym memberships |
| Travel | WestJet, Air Canada, hotels, Airbnb |
| Utilities | Rogers, Bell, Hydro |
| Entertainment | Cineplex, events, concerts |

---

## Troubleshooting

**"python3: command not found"**
Python isn't installed or wasn't added to PATH. Redo Step 1 and make sure you check "Add Python to PATH" during installation.

**"Could not reach Ollama"**
Ollama isn't running. In a separate Terminal window, run:
```
ollama serve
```
Then try the categorize command again.

**"No such file or directory"**
The path to your statements folder is wrong. Make sure the folder exists and the path is correct. On Mac, you can drag a folder into Terminal to get its path automatically.

**Browser doesn't open automatically**
Manually open your browser and go to: `http://localhost:8765`

---

## File Structure

```
finance-dashboard/
├── import.py         ← import statements + auto-categorize
├── dashboard.py      ← launch the dashboard
├── dashboard.html    ← the dashboard interface (don't move this)
└── data/
    ├── transactions.json   ← all your transaction data
    └── categories.json     ← your category list
```

Your data lives entirely in the `data/` folder. Back it up by copying that folder somewhere safe.

---

## Resetting Your Data

To wipe everything and start fresh:
```
python3 import.py --reset
```