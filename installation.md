# Folio Board Installation and Launch Guide

Folio Board is a local-first investment research workspace. The easiest setup path assumes you already use an AI coding agent such as Codex, Claude Code, or another LLM assistant that can operate on your local machine.

Korean users can also read [README.ko.md](README.ko.md).

There are two supported setup paths:

1. **AI Agent-assisted setup**: recommended for most users.
2. **Manual setup**: use when you prefer to run commands yourself or need to troubleshoot.

Already have Folio Board installed? Skip to [Updating To A New Version](#updating-to-a-new-version).

---

## Method 1. AI Agent-Assisted Setup

Give your AI Agent the repository link and the prompt below.

```text
Install and run Folio Board on my local PC.

Repository:
https://github.com/jh-folio/Folio-Board

Please:
1. Clone the repository.
2. Install the Python dependencies from requirements.txt.
3. Copy .env.example to .env if .env does not already exist.
4. Do not delete or overwrite data/, research-inbox/, config/, or any existing user files.
5. If an API key or local path is needed, ask me before editing .env.
6. Start Folio Board using the provided Windows or shell startup script.
7. Open the local app URL in my browser.
8. If startup fails, show me the relevant error and log location.
```

Recommended follow-up prompt after the first launch:

```text
Check whether Folio Board started correctly.
If it did not, diagnose the startup error without deleting any personal data.
```

### What The Agent Should Preserve

The Agent must not delete, reset, or overwrite:

- `.env`
- `data/`
- `research-inbox/`
- user-edited files in `config/`
- `workspace.json` at the app root, if present

These locations can contain personal API keys, generated reports, RSS archives, notes, and local research material. A single `data/` folder can reach hundreds of thousands of files and close to a gigabyte, so never assume it is disposable.

`workspace.json` is written only when you move your research data out of the app folder from **Settings > “자료 위치”** (data location). It records where the data went. Deleting it makes Folio Board fall back to the app folder and your existing work appears to be gone, even though the files are still on disk.

---

## Method 2. Manual Setup

### Requirements

- Python 3
- Git, if installing from the GitHub repository
- A modern browser

Optional but recommended:

- An installed and authenticated Codex, Claude Code, or Antigravity CLI for higher-quality generation
- `yfinance` and `polars` dependencies from `requirements.txt` for market data and dataframe operations

### Clone The Repository

```powershell
git clone https://github.com/jh-folio/Folio-Board.git
cd Folio-Board
```

If you downloaded a ZIP release instead, extract it and open a terminal in the extracted folder.

### Install Python Dependencies

Windows:

```powershell
py -3 -m pip install -r requirements.txt
```

macOS / Linux:

```bash
python3 -m pip install -r requirements.txt
```

### Create Local Settings

If `.env` does not exist, copy the template:

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS / Linux:

```bash
cp .env.example .env
```

Then edit `.env` only for the services you actually use. Data API keys are optional. AI features use a supported local CLI bridge. Configure the CLI in Settings, or turn AI off to use rule-based features.

Do not commit or share `.env`.

---

## Launch Folio Board

### Windows

Current launch path:

```text
start-archive.cmd
```

You can double-click this file from File Explorer.

PowerShell alternative:

```powershell
.\start.ps1
```

### macOS / Linux

```bash
bash start.sh
```

Direct Python fallback:

```bash
python3 app.py
```

### Open The App

**The startup scripts open your browser for you** once the server is actually answering. If it does not appear, open this address yourself:

```text
http://127.0.0.1:8787
```

Use `127.0.0.1` rather than `localhost`. The server listens on IPv4 only, and on some systems `localhost` resolves to IPv6 first and waits on every request before falling back.

The first launch on a large research archive can take a while — the search index is read at startup. Keep the terminal window open while using the app; closing it stops Folio Board.

### First Run

A short setup guide appears the first time you start Folio Board with an empty workspace. It asks two things — whether to use AI, and which markets to follow — and you can skip any step. **Folio Board works without an AI key**: collection, search, charts, and rule-based reports all run locally.

The guide does not appear if you already have research data, so updating never shows it again.

---

## Updating To A New Version

Releases unzip into a **version-named folder** such as `FolioBoard-v0.5.4/`. The new folder starts with an empty `data/`, so your reports and collected articles do not follow automatically unless you tell them to.

### If your data lives in the app folder (the default)

1. Unzip the new release next to the old one.
2. Copy `data/`, `research-inbox/`, `config/`, and `.env` from the old folder into the new one.
3. Start the new folder and confirm your reports are there.
4. Keep the old folder until you have confirmed it. Then delete it if you want the space back.

### If you moved your data (Settings > “자료 위치”)

Nothing to copy. Start the new folder and Folio Board finds `~/Documents/FolioBoard` on its own — or the older `~/Documents/FolioOS`, if that's still where your data is. Copy `.env` across if you use API keys.

Moving is a one-time choice that makes every later update a plain unzip. It **copies** your data and never deletes the original.

### Agent prompt for updating

```text
Update my existing Folio Board installation to the latest release.

Current installation folder:
<path to the folder you run today>

Please:
1. Download or pull the latest release into a NEW folder next to the current one.
2. Do NOT delete or modify anything in the current folder.
3. Copy .env from the old folder to the new one if it exists.
4. Check the old app root for workspace.json.
   - If it exists, my research data lives outside the app folder. Copy workspace.json
     to the new folder and copy nothing else.
   - If it does not exist, copy data/, research-inbox/, and config/ from the old folder
     to the new one. This can be a large copy; verify the file count afterwards.
5. Install Python dependencies from requirements.txt in the new folder.
6. Start the new installation and confirm my saved reports and settings are present.
7. Tell me the old folder path so I can delete it myself once I have verified the update.
```

---

## Important Folders

Do not delete these unless you intentionally want to remove local data:

- `data/`: generated reports, caches, databases, notes, jobs
- `research-inbox/`: articles, RSS items, reports, filings, links
- `config/`: user-adjustable company/ticker/source settings
- `.env`: local API keys and settings
- `workspace.json`: present only if you moved your data; it points to where the data went

These three data folders live inside the app folder by default. **Settings > “자료 위치”** (data location) shows the current location and size, opens the folder, and can move it to your Documents folder so future updates carry it automatically.

Development-only folders such as `web/`, `docs/`, and `plan/` are needed for source development, but are not required in a normal user runtime package if the built frontend under `public/` is current. Source/developer archives can still include them.

Maintainers can create a clean user package from reviewed tracked inputs with:

```powershell
py -3 scripts\package_release.py --version v0.5.4
py -3 scripts\verify_release.py --release-dir dist\FolioBoard-v0.5.4
```

The package includes the built React bundle, so normal users do not need Node.js. Deep Research remains local-first: its reports are stored under `data/topic-reports/`, Smart Collections under `data/smart-collections.json`, and Agent Work Log entries contain metadata only.

---

## Troubleshooting

### The Browser Does Not Open

Open the local URL manually:

```text
http://localhost:8787
```

### Python Command Not Found

On Windows, try:

```powershell
py -3 --version
```

On macOS / Linux, try:

```bash
python3 --version
```

### Dependencies Are Missing

Run the dependency install command again:

```powershell
py -3 -m pip install -r requirements.txt
```

or:

```bash
python3 -m pip install -r requirements.txt
```

### AI Features Do Not Work

Check:

- the selected LLM CLI is installed and authenticated, and
- AI Agent settings are enabled inside Folio Board.

Folio Board should still run with rule-based fallback behavior even when LLM features are unavailable.
