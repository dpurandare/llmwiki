# How the Wind Industry Abbreviations Were Found

This document explains the exact steps taken to search for common wind industry abbreviations
using the `llmwiki-research` local MCP server and the research workspace at
`/home/deepak/Jade/research`. It is intended to help others understand both the intended
workflow and the fallback process that was actually used.

---

## Step 1 — Confirm What MCP Servers Are Configured

Before doing any searching, we checked which local MCP servers exist and what tools they expose.

**What was checked:**
```
~/.claude/settings.json
```

**What was found:**
One server named `llmwiki-research` configured to run:
```
/home/deepak/Jade/llmwiki/llmwiki mcp /home/deepak/Jade/research
```

This is the local stdio MCP server for the research workspace. In a working setup, Claude
connects to it at session startup and gains access to tools like `guide`, `search`, `read`,
`write`, `delete`, `lint`, and `ping`.

---

## Step 2 — Check Whether the MCP Tools Were Available in the Session

The MCP server's tools (`guide`, `search`, `read`, etc.) are injected into the Claude session
at startup if the server starts successfully. We used `ToolSearch` to check whether they were
present — they were not.

**Why:** The tools from a local MCP server appear in the session's tool list only when the
server process starts cleanly on session launch. If the server crashes or fails to start, its
tools are simply absent — there is no error message in the conversation.

---

## Step 3 — Diagnose Why the MCP Server Was Not Running

We sent a test JSON-RPC message to the server binary directly via the shell:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | \
  timeout 5 /home/deepak/Jade/llmwiki/llmwiki mcp /home/deepak/Jade/research
```

**Result — crash on startup:**
```
ModuleNotFoundError: No module named 'aioboto3'
```

**Root cause:** The MCP server (`mcp/local_server.py`) imports Python packages (`aioboto3`,
`mcp`, `aiosqlite`, etc.) listed in `mcp/requirements.txt`. There is no Python virtual
environment (`venv`) inside the `mcp/` directory, and these packages are not installed in the
system Python. So the server fails to start every time.

---

## Step 4 — Understand the Workspace Structure

Since the MCP server was unavailable, we fell back to accessing the research workspace
directly. We listed the workspace directory to understand what was there:

```
/home/deepak/Jade/research/
├── DNV_availability_definitions_white_paper_2017.pdf
├── Lee_Fields_2021_loss_waterfall_taxonomy.pdf
├── SECI_Standard_PPA_Wind_template.pdf
├── IEA_Task43_WRA_data_standard/          ← directory of markdown/JSON files
├── wiki/                                   ← llmwiki-generated wiki pages
└── .llmwiki/
    └── index.db                            ← SQLite index of all documents
```

The workspace contains three PDF source documents and a large directory of markdown and JSON
files from the IEA Task 43 Wind Resource Assessment data standard.

---

## Step 5 — Query the SQLite Index Directly

The llmwiki system maintains a SQLite database at `.llmwiki/index.db` that indexes all
documents in the workspace. Even without the MCP server, this database can be queried
directly with the `sqlite3` CLI tool.

**List all indexed documents:**
```bash
sqlite3 /home/deepak/Jade/research/.llmwiki/index.db \
  "SELECT filename, title, relative_path FROM documents ORDER BY document_number;"
```

This confirmed that three PDFs and hundreds of IEA Task 43 files were indexed.

**Search the indexed text content for abbreviation-related documents:**
```bash
sqlite3 /home/deepak/Jade/research/.llmwiki/index.db \
  "SELECT title, relative_path FROM documents
   WHERE lower(content) LIKE '%abbreviat%'
      OR lower(content) LIKE '%acronym%';"
```

**Result:** No matches. The SQLite index stores the plain-text content of text-based files
(markdown, JSON, CSV, etc.) but **not** the extracted text of PDFs — PDFs are stored as
binary blobs and their text content is not available in the database.

---

## Step 6 — Confirm That PDF Text Is Not in the Database

```bash
sqlite3 /home/deepak/Jade/research/.llmwiki/index.db \
  "SELECT title, substr(content,1,200) FROM documents WHERE file_type='pdf';"
```

**Result:** The `content` column is empty for all PDF documents. This is expected — llmwiki
indexes PDF metadata but does not extract or store the PDF text in SQLite by default. The MCP
server's `read` tool would normally handle PDF reading (with OCR or text extraction on the
fly), but since the server is down, we need another route.

---

## Step 7 — Extract PDF Text with `pdftotext`

The system has `pdftotext` (part of the `poppler-utils` package) available. This tool
extracts the raw text from a PDF file to stdout. We ran it against each of the three PDFs:

```bash
pdftotext /home/deepak/Jade/research/DNV_availability_definitions_white_paper_2017.pdf -
pdftotext /home/deepak/Jade/research/Lee_Fields_2021_loss_waterfall_taxonomy.pdf -
pdftotext /home/deepak/Jade/research/SECI_Standard_PPA_Wind_template.pdf -
```

The `-` argument tells `pdftotext` to write to stdout instead of a file.

---

## Step 8 — Locate Abbreviation Sections in Each PDF

### DNV GL Paper

The DNV GL white paper contains a formal **"List of abbreviations"** section near the
beginning (page 2). We located it by searching the extracted text for that heading and
slicing out the section:

```python
start = text.find('List of abbreviations')
section = text[start:start+800]
```

This yielded a clean two-column table (Abbreviation | Meaning) covering 12 entries.

### Lee & Fields 2021

This academic paper does not have a dedicated abbreviation section. Instead, abbreviations
are defined inline on first use — e.g. "wind resource assessment (WRA)". We used Python
regular expressions to find these inline definitions:

```python
# Pattern: lowercase phrase (ABBR)
re.findall(r'([a-z][a-z\s-]{4,55})\s*\(\s*([A-Z][A-Z0-9/-]{1,9})\s*\)', text)

# Pattern: ABBR (lowercase phrase)
re.findall(r'\b([A-Z][A-Z0-9]{1,8})\s*\(\s*([a-z][a-z\s-]{4,55})\s*\)', text)
```

We also searched for specific known wind industry terms directly:

```python
for abbr in ['AEP', 'WRA', 'EYA', 'TI', 'P50', 'P90', 'MCP', 'CFD', 'NWP', 'WAsP']:
    idx = text.find(abbr)
    # extract surrounding context to confirm the full-form definition
```

### SECI PPA Template

This legal/commercial document contains a **"Definitions"** section that enumerates every
abbreviation used in the agreement. We located it:

```python
idx = text.find('Definitions')
section = text[idx:idx+3000]
```

This section defines all commercial/regulatory abbreviations used in Indian wind power
purchase agreements.

---

## Step 9 — Compile and Deduplicate Results

Abbreviations extracted from all three PDFs were collected into a Python dictionary, with
the source document noted for each entry. Duplicates (e.g. `IEC` and `WRA` appear in
multiple documents) were deduplicated, keeping the clearest definition.

The final result was grouped by source document and presented as three tables covering:
- **Technical/operational** abbreviations (DNV GL paper)
- **Wind resource assessment** abbreviations (Lee & Fields 2021)
- **Commercial/regulatory** abbreviations (SECI PPA template)

---

## Summary: Intended vs. Actual Path

| | Intended Path | Actual Path |
|---|---|---|
| **Tool** | `llmwiki-research` MCP `search` tool | Direct SQLite query + `pdftotext` |
| **Why different** | MCP server failed to start (missing `aioboto3` venv) | Fallback to shell tools |
| **PDF text** | MCP `read` tool handles extraction | `pdftotext` CLI |
| **Search** | Semantic/full-text search via MCP | SQL `LIKE` + Python regex |

---

## How to Fix the MCP Server (So the Intended Path Works Next Time)

```bash
cd /home/deepak/Jade/llmwiki/mcp
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Then update `~/.claude/settings.json` to invoke Python from the venv:

```json
{
  "mcpServers": {
    "llmwiki-research": {
      "command": "/home/deepak/Jade/llmwiki/mcp/.venv/bin/python",
      "args": ["-m", "local_server", "--workspace", "/home/deepak/Jade/research"]
    }
  }
}
```

Once fixed, the search would use the `search` MCP tool instead:
```
search(query="wind industry abbreviations", kb="all")
```
