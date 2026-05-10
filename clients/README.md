# Client Workspaces

Each paying client gets an isolated runtime folder created by `client_manager.py`.

```powershell
.venv/Scripts/python.exe 04-coding/scripts/client_manager.py create "Client Name"
.venv/Scripts/python.exe 04-coding/scripts/client_manager.py demo
.venv/Scripts/python.exe 04-coding/scripts/client_manager.py status "Client Name"
.venv/Scripts/python.exe 04-coding/scripts/client_manager.py run "Client Name"
.venv/Scripts/python.exe 04-coding/scripts/client_manager.py reply "Client Name" --body "Interested, tell me more" --company "Example Co"
.venv/Scripts/python.exe 04-coding/scripts/client_manager.py report "Client Name"
```

Client folders are ignored by Git because they can contain secrets, prospect data, generated messages, reports, and SQLite state.

Required per-client structure:

```text
clients/client-name/
  config.json
  database.sqlite
  .env
  prospects.csv
  generated-outreach.csv
  replies.csv
  weekly-kpi-data.csv
  reports/
```

Use isolated sending domains, API keys, Notion/Airtable destinations, and suppression lists per client unless the signed scope says otherwise.

`demo` creates `clients/demo-client/` with fake prospects, replies, KPI data, and a report for Loom walkthroughs, sales calls, and landing page visuals.