# CompCoach

Shell-based conversational coach for teachers and learners. It interprets survey-based **digital (DigComp)** and **AI competence** profiles, supports coaching dialogue via an LLM, and recommends courses using **RAG** (ChromaDB).

This is a **research prototype** (not a pip package). Run from the project root with `python run.py`.

## Features

- **Login** — users and competence profiles in `data/users.json`
- **Main menu** — new / resume / profile / export / quit
- **Profile-aware chat** — system prompt built from `prompts/` + user survey scores
- **Course RAG** — chunk course summaries, embed in ChromaDB, `search_courses` tool for recommendations
- **SQLite** — save chats, resume with full colored history replay
- **Export** — JSON + Markdown per chat ID under `data/exports/`
- **Audit log** — JSONL per day under `data/audit/` (inputs, navigation, LLM latency, course searches, satisfaction)
- **Rich terminal UI** — panels, markdown, spinners while the model thinks

## Requirements

- Python **3.10+**
- OpenAI-compatible API key (or compatible endpoint via `OPENAI_BASE_URL`)

## Setup

```bash
cd CompCoach
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
# source .venv/bin/activate

python -m pip install -r requirements.txt

copy .env.example .env    # Windows
# cp .env.example .env    # macOS / Linux

# Edit .env — set OPENAI_API_KEY at minimum
```

## Build the course index

Required before first chat (also auto-built if missing when you run the app):

```bash
python build_index.py
```

Or:

```bash
python run.py build-index
```

This chunks each course `summary` (with title), embeds with Chroma’s default embedding model, and stores metadata (`domain`, `area`, `dimension`, `slug`, `url`) in `data/chroma/`.

## Run

```bash
python run.py
```

### Demo users

Password for both: `coach123`


| Username       | Display name |
| -------------- | ------------ |
| `student_x`    | Student X    |
| `teacher_anna` | Anna Teacher |


### Navigation

**Inside a chat** — only this command is handled by the app (not sent to the LLM):


| Command | Action                                    |
| ------- | ----------------------------------------- |
| `/menu` | Save chat and return to the **main menu** |


**Main menu** (shown after login, or after `/menu` from a chat):


| Key | Action                                     |
| --- | ------------------------------------------ |
| `n` | **New** chat (optional title)              |
| `r` | **Resume** — then enter **chat ID**        |
| `p` | View **competence profile** (color tables) |
| `e` | **Export** — then enter **chat ID**        |
| `q` | **Quit** CompCoach                         |


Typical flows from chat: `/menu` → `n` (new), `/menu` → `r` → ID (resume), `/menu` → `q` (quit).

When you leave a chat (via `/menu`), you are asked for **satisfaction** (1–5, or Enter to skip). Resuming a chat replays prior messages in color before you continue.

The coach is instructed via `prompts/navigation.md` to explain these steps if a student asks (without inventing commands like `q` in chat).

## Project layout

```
run.py                 # entry: chat CLI
build_index.py         # entry: build / rebuild Chroma index
.env.example           # environment template
requirements.txt
prompts/               # editable system prompt sections (see prompts/README.md)
  role.md
  navigation.md
  scope.md
  ...
data/
  users.json           # accounts + competence profiles (committed)
  courses.json         # course catalog (committed)
  chroma/              # ChromaDB (generated, gitignored)
  compcoach.db         # SQLite chats (generated, gitignored)
  audit/               # audit JSONL (generated, gitignored)
  exports/             # exported chats (generated, gitignored)
src/compcoach/
  cli.py               # Rich shell UI
  llm.py               # OpenAI client + RAG tool
  prompts_loader.py    # assembles prompts/
  audit.py             # audit logging
  export.py            # conversation export
  profile.py           # profile display + summary for prompt
  commands.py          # /menu detection in chat
  db.py                # SQLite
  auth.py
  rag/                 # chunking, indexing, retrieval
  config.py
```

## Environment variables


| Variable             | Default             | Description                                                            |
| -------------------- | ------------------- | ---------------------------------------------------------------------- |
| `OPENAI_API_KEY`     | —                   | **Required** for chat                                                  |
| `OPENAI_BASE_URL`    | (OpenAI default)    | Optional — Azure, Ollama, etc. Leave unset or set full `https://…` URL |
| `OPENAI_MODEL`       | `gpt-4o-mini`       | Chat model                                                             |
| `CHROMA_PERSIST_DIR` | `data/chroma`       | Chroma persistence                                                     |
| `DATABASE_PATH`      | `data/compcoach.db` | SQLite database                                                        |
| `AUDIT_LOG_DIR`      | `data/audit`        | Daily audit JSONL files                                                |


## Customising the coach

Edit markdown files under `[prompts/](prompts/)`. Changes apply on the next `python run.py` (no rebuild). Start with `prompts/navigation.md` for app commands and `prompts/role.md` for coaching behaviour.

## Audit logging

Each line in `data/audit/audit-YYYY-MM-DD.jsonl` is one JSON event: login, menu choices, chat messages, `/menu`, exports, saves, `session_id`, `turn_number`, `assistant_message` stats, `search_courses`, and `chat_satisfaction`. Passwords are never logged.

## How RAG works in chat

When the model should recommend courses, it calls `search_courses`. The backend queries ChromaDB with a natural-language `query` and optional filters (`domain`, `area`, `dimension`). Retrieved excerpts are returned to the model, which cites real course titles and URLs from `data/courses.json`.