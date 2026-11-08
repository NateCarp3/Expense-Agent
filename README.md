# Expense Agent

Upload bank and credit card statements (PDF, CSV, Excel); transactions are categorized,
stored in Postgres, and shown on a dashboard with budgets.

## Environment variables
| Name | Purpose |
|---|---|
| `APP_PASSWORD` | Password for the login page |
| `SECRET_KEY` | Random string for signing session cookies |
| `ANTHROPIC_API_KEY` | Used to read PDFs and categorize unknown merchants |
| `DATABASE_URL` | Postgres URL (defaults to local SQLite `expenses.db`) |

## Run locally
```
python -m venv .venv
.venv\Scripts\activate        # Windows  (source .venv/bin/activate on Mac/Linux)
pip install -r requirements.txt
set APP_PASSWORD=choose-one    # PowerShell: $env:APP_PASSWORD="choose-one"
flask --app app run
```

## Render
Build: `pip install -r requirements.txt` · Start: `gunicorn app:app`
