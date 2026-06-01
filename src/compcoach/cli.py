import sys
from typing import Literal

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.theme import Theme

from compcoach.audit import AuditLogger
from compcoach.auth import User, authenticate
from compcoach.config import OPENAI_API_KEY
from compcoach.db import ChatStore
from compcoach.commands import normalize_user_input, parse_chat_command
from compcoach.llm import CoachLLM
from compcoach.prompts_loader import build_system_prompt, load_opening_user_message
from compcoach.export import export_conversation
from compcoach.profile import print_competence_profile
from compcoach.rag.indexer import build_course_index
from compcoach.rag.retriever import CourseRetriever
from compcoach.ui import exit_app, run_with_wait

console = Console(
    theme=Theme(
        {
            "info": "cyan",
            "user": "bold green",
            "assistant": "bold blue",
            "warn": "yellow",
            "error": "bold red",
        }
    )
)

ChatAction = Literal["menu"]

OPENING_USER_MESSAGE = load_opening_user_message()

MAIN_MENU_HELP = (
    "[dim]n[/dim] = new chat  ·  "
    "[dim]r[/dim] = resume (then chat ID)  ·  "
    "[dim]p[/dim] = profile  ·  "
    "[dim]e[/dim] = export (then chat ID)  ·  "
    "[dim]q[/dim] = quit"
)

CHAT_HELP = "[info]Type /menu to save and return to the main menu[/info]"


def _prompt(
    audit: AuditLogger,
    label: str,
    *,
    username: str | None = None,
    event: str = "user_input",
    password: bool = False,
    audit_extra: dict | None = None,
    **prompt_kwargs,
) -> str:
    """Rich prompt with audit logging (passwords are never logged)."""
    value = Prompt.ask(label, password=password, **prompt_kwargs)
    extra = audit_extra or {}
    if password:
        audit.log(
            f"{event}_password_entered",
            username=username,
            prompt=label,
            value="[REDACTED]",
            **extra,
        )
    else:
        audit.log_input(
            event, username=username, prompt=label, value=value, **extra
        )
    return value


def _login(audit: AuditLogger) -> User | None:
    console.print(Panel.fit("[bold]CompCoach[/bold] — competence coaching chat", style="info"))
    audit.log("login_screen_shown")
    for attempt in range(3):
        username = _prompt(audit, "Username", event="login_username")
        password = _prompt(
            audit, "Password", username=username, event="login", password=True
        )
        user = authenticate(username, password)
        if user:
            audit.log("login_success", username=user.username, attempt=attempt + 1)
            audit.start_session(user.username)
            console.print(f"[info]Welcome, {user.display_name}![/info]")
            return user
        audit.log("login_failure", username=username, attempt=attempt + 1)
        console.print("[error]Invalid username or password.[/error]")
    audit.log("login_abandoned", reason="max_attempts")
    return None


def _ensure_index(audit: AuditLogger, username: str) -> None:
    try:
        CourseRetriever()
    except Exception:
        audit.log("index_build_started", username=username)
        console.print("[warn]Course index not found. Building RAG index…[/warn]")
        n = build_course_index()
        audit.log("index_build_completed", username=username, chunks=n)
        console.print(f"[info]Indexed {n} chunks.[/info]")


def _pick_chat(store: ChatStore, user: User, audit: AuditLogger) -> tuple[int, list[dict]] | None:
    while True:
        console.print()
        console.print(Panel.fit("[bold]Main menu[/bold]", style="info"))
        audit.log("main_menu_shown", username=user.username)
        chats = store.list_chats(user.username)
        if chats:
            table = Table(title="Saved chats")
            table.add_column("#", style="dim")
            table.add_column("ID")
            table.add_column("Title")
            table.add_column("Messages")
            table.add_column("Updated")
            for i, c in enumerate(chats, 1):
                table.add_row(
                    str(i), str(c["id"]), c["title"] or "", str(c["msg_count"]), c["updated_at"][:19]
                )
            console.print(table)
        else:
            console.print("[dim]No saved chats yet.[/dim]")

        console.print(MAIN_MENU_HELP)
        choice = _prompt(
            audit,
            "Choose an option",
            username=user.username,
            event="menu_choice",
            choices=["n", "r", "p", "e", "q"],
            default="n",
        ).lower()

        if choice == "q":
            audit.log("app_quit", username=user.username, from_="main_menu")
            return None

        if choice == "p":
            audit.log("profile_viewed", username=user.username)
            print_competence_profile(console, user, audit)
            continue

        if choice == "e":
            chat_id_str = _prompt(
                audit,
                "Chat ID to export",
                username=user.username,
                event="export_chat_id",
            )
            chat_id = int(chat_id_str)
            try:
                json_path, md_path = export_conversation(store, user, chat_id)
                audit.log(
                    "export_success",
                    username=user.username,
                    chat_id=chat_id,
                    json_path=str(json_path),
                    md_path=str(md_path),
                )
                console.print("[info]Conversation exported:[/info]")
                console.print(f"  [dim]JSON:[/dim] {json_path}")
                console.print(f"  [dim]Markdown:[/dim] {md_path}")
            except ValueError as err:
                audit.log(
                    "export_failure",
                    username=user.username,
                    chat_id=chat_id,
                    error=str(err),
                )
                console.print(f"[error]{err}[/error]")
            continue

        if choice == "r":
            chat_id_str = _prompt(
                audit,
                "Chat ID",
                username=user.username,
                event="resume_chat_id",
            )
            chat_id = int(chat_id_str)
            history = store.get_messages(chat_id)
            audit.log(
                "chat_resumed",
                username=user.username,
                chat_id=chat_id,
                message_count=len(history),
            )
            if not history:
                console.print("[warn]No messages in that chat; starting fresh thread in same ID.[/warn]")
            return chat_id, history

        title = _prompt(
            audit,
            "Chat title (optional)",
            username=user.username,
            event="new_chat_title",
            default="",
        )
        title = title or None
        chat_id = store.create_chat(user.username, title=title)
        audit.log(
            "chat_created",
            username=user.username,
            chat_id=chat_id,
            title=store.get_chat(chat_id, user.username)["title"],
        )
        return chat_id, []


def _print_user(text: str) -> None:
    console.print()
    console.print(Panel(text, title="You", border_style="user", title_align="left"))
    console.print()


def _print_assistant(text: str) -> None:
    console.print()
    console.print(Panel(Markdown(text), title="CompCoach", border_style="assistant", title_align="left"))
    console.print()


def _print_history(history: list[dict]) -> None:
    if not history:
        return
    console.print(Panel.fit("[bold]Chat history[/bold]", style="dim"))
    for msg in history:
        role = msg.get("role")
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            _print_user(content)
        elif role == "assistant":
            _print_assistant(content)
    console.print("[dim]— Continue below —[/dim]")


def _count_user_turns(messages: list[dict]) -> int:
    return sum(
        1
        for m in messages
        if m.get("role") == "user" and m.get("content") != OPENING_USER_MESSAGE
    )


def _ask_llm(
    llm: CoachLLM,
    messages: list[dict],
    user: User,
    chat_id: int,
    turn_number: int,
    audit: AuditLogger,
    *,
    searching: bool = False,
    status: str | None = None,
    is_opening: bool = False,
) -> str:
    if status is None:
        status = "Searching courses and thinking" if searching else "Thinking"
    return run_with_wait(
        console,
        lambda: llm.complete(
            messages,
            audit=audit,
            username=user.username,
            chat_id=chat_id,
            turn_number=turn_number,
            is_opening=is_opening,
        ),
        message=status,
    )


def _prompt_chat_satisfaction(audit: AuditLogger, user: User, chat_id: int) -> None:
    console.print()
    console.print("[info]How helpful was this coaching chat?[/info]")
    rating = _prompt(
        audit,
        "Rate 1 (not helpful) to 5 (very helpful), or Enter to skip",
        username=user.username,
        event="chat_satisfaction",
        audit_extra={"chat_id": chat_id},
        default="",
    ).strip()
    if not rating:
        audit.log("chat_satisfaction_skipped", username=user.username, chat_id=chat_id)
        return
    if rating not in {"1", "2", "3", "4", "5"}:
        audit.log(
            "chat_satisfaction_invalid",
            username=user.username,
            chat_id=chat_id,
            value=rating,
        )
        console.print("[warn]Invalid rating — not recorded.[/warn]")
        return
    audit.log(
        "chat_satisfaction",
        username=user.username,
        chat_id=chat_id,
        rating=int(rating),
    )
    console.print("[info]Thanks for your feedback![/info]")


def run_chat(
    user: User,
    chat_id: int,
    history: list[dict],
    llm: CoachLLM,
    audit: AuditLogger,
) -> tuple[list[dict], ChatAction]:
    system = build_system_prompt(user.display_name, user.profile)
    messages: list[dict] = [{"role": "system", "content": system}]
    messages.extend(history)

    audit.log(
        "chat_started",
        username=user.username,
        chat_id=chat_id,
        resumed=bool(history),
        message_count=len(history),
    )

    console.print()
    if history:
        console.print(f"[info]Chat #{chat_id} — resuming where you left off.[/info]")
        _print_history(history)
    else:
        console.print(f"[info]Chat #{chat_id} — new conversation.[/info]")
        console.print(CHAT_HELP)
        audit.log("chat_opening_requested", username=user.username, chat_id=chat_id)
        try:
            opening = _ask_llm(
                llm,
                messages + [{"role": "user", "content": OPENING_USER_MESSAGE}],
                user,
                chat_id,
                turn_number=0,
                audit=audit,
                status="Analyzing competence profile",
                is_opening=True,
            )
            messages.append({"role": "assistant", "content": opening})
            _print_assistant(opening)
        except Exception as e:
            audit.log(
                "chat_opening_failed",
                username=user.username,
                chat_id=chat_id,
                error=str(e),
            )
            console.print(f"[error]Could not start chat: {e}[/error]")
            return messages, "menu"
    if history:
        console.print(CHAT_HELP)

    while True:
        try:
            next_turn = _count_user_turns(messages) + 1
            user_input = _prompt(
                audit,
                "[user]You[/user]",
                username=user.username,
                event="chat_message",
                audit_extra={"chat_id": chat_id, "turn_number": next_turn},
            ).strip()
        except (EOFError, KeyboardInterrupt):
            audit.log(
                "chat_interrupted",
                username=user.username,
                chat_id=chat_id,
                reason="keyboard_interrupt",
            )
            console.print()
            return messages, "menu"

        if not user_input:
            continue

        if parse_chat_command(user_input) == "menu":
            audit.log(
                "chat_command",
                username=user.username,
                chat_id=chat_id,
                command=user_input.strip(),
                normalized=normalize_user_input(user_input),
                action="main_menu",
            )
            return messages, "menu"

        messages.append({"role": "user", "content": user_input})
        try:
            wants_courses = any(
                word in user_input.lower()
                for word in ("course", "courses", "recommend", "learning path", "training")
            )
            reply = _ask_llm(
                llm,
                messages,
                user,
                chat_id,
                next_turn,
                audit,
                searching=wants_courses,
            )
        except Exception as e:
            audit.log(
                "chat_llm_error",
                username=user.username,
                chat_id=chat_id,
                error=str(e),
            )
            console.print(f"[error]LLM error: {e}[/error]")
            messages.pop()
            continue

        messages.append({"role": "assistant", "content": reply})
        _print_assistant(reply)


def save_conversation(
    store: ChatStore,
    chat_id: int,
    messages: list[dict],
    audit: AuditLogger,
    username: str,
) -> None:
    to_save = [m for m in messages if m["role"] in ("user", "assistant")]
    store.replace_conversation(chat_id, to_save)
    audit.log(
        "chat_saved",
        username=username,
        chat_id=chat_id,
        message_count=len(to_save),
    )
    console.print(f"[info]Saved chat #{chat_id} ({len(to_save)} messages).[/info]")


def _session_loop(user: User, store: ChatStore, llm: CoachLLM, audit: AuditLogger) -> None:
    while True:
        picked = _pick_chat(store, user, audit)
        if picked is None:
            return

        chat_id, history = picked
        messages, _action = run_chat(user, chat_id, history, llm, audit)
        save_conversation(store, chat_id, messages, audit, user.username)
        _prompt_chat_satisfaction(audit, user, chat_id)
        audit.log("chat_session_ended", username=user.username, chat_id=chat_id, action="main_menu")
        console.print("[info]Back to the main menu.[/info]")


def main() -> None:
    audit = AuditLogger()
    audit.log("app_started", argv=sys.argv)
    user: User | None = None
    store: ChatStore | None = None
    quitting = False

    if len(sys.argv) > 1 and sys.argv[1] == "build-index":
        n = build_course_index()
        audit.log("index_build_cli", chunks=n)
        console.print(f"[info]Indexed {n} course chunks.[/info]")
        return

    if not OPENAI_API_KEY:
        audit.log("app_exit", reason="missing_openai_api_key")
        console.print("[error]Set OPENAI_API_KEY in .env (see .env.example).[/error]")
        sys.exit(1)

    user = _login(audit)
    if not user:
        sys.exit(1)

    _ensure_index(audit, user.username)
    store = ChatStore()
    try:
        llm = run_with_wait(console, CoachLLM, message="Loading coach")
        audit.log("coach_loaded", username=user.username)
        _session_loop(user, store, llm, audit)
        quitting = True
    finally:
        if store is not None:
            store.close()
        if user is not None:
            audit.log("app_session_closed", username=user.username)
        if quitting:
            exit_app(console)


if __name__ == "__main__":
    main()
