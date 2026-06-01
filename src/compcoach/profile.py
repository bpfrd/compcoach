import json
from typing import Any

from typing import TYPE_CHECKING

from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from compcoach.audit import AuditLogger
    from compcoach.auth import User

DIMENSIONS = ("attitude", "behaviour", "knowledge", "skill")
DOMAIN_LABELS = {
    "digital_competences": "Digital competences (DigComp)",
    "ai_competences": "AI competences",
}


def _score_cell(score: float) -> Text:
    """Color-coded score with a simple 1–5 bar."""
    if score < 2.5:
        style = "red"
    elif score < 3.5:
        style = "yellow"
    elif score < 4.0:
        style = "cyan"
    else:
        style = "green"
    filled = max(0, min(5, int(round(score))))
    bar = "█" * filled + "░" * (5 - filled)
    text = Text()
    text.append(f"{score:.1f} ", style=f"bold {style}")
    text.append(bar, style=style)
    return text


def _humanize_area(area: str) -> str:
    return area.replace("_", " ").title()


def profile_summary(profile: dict[str, Any]) -> str:
    """Human-readable summary of strengths and gaps."""
    lines: list[str] = []
    for domain_key, domain_label in (
        ("digital_competences", "Digital competences (DigComp)"),
        ("ai_competences", "AI competences"),
    ):
        areas = profile.get(domain_key, {})
        if not areas:
            continue
        lines.append(f"\n## {domain_label}")
        for area, dims in sorted(areas.items()):
            scores = {k: float(v) for k, v in dims.items()}
            avg = sum(scores.values()) / len(scores)
            weakest = min(scores, key=scores.get)
            strongest = max(scores, key=scores.get)
            lines.append(
                f"- **{area.replace('_', ' ')}**: avg {avg:.1f}/5 — "
                f"strongest: {strongest} ({scores[strongest]:.1f}), "
                f"weakest: {weakest} ({scores[weakest]:.1f})"
            )
    return "\n".join(lines)


def profile_json(profile: dict[str, Any]) -> str:
    return json.dumps(profile, indent=2)


def _domain_table(profile: dict[str, Any], domain_key: str) -> Table:
    areas = profile.get(domain_key, {})
    table = Table(
        title=DOMAIN_LABELS.get(domain_key, domain_key),
        show_header=True,
        header_style="bold magenta",
        border_style="blue",
        expand=True,
    )
    table.add_column("Competence area", style="bold", min_width=28)
    for dim in DIMENSIONS:
        table.add_column(dim.replace("_", " ").title(), justify="center")
    table.add_column("Average", justify="center", style="bold")

    for area in sorted(areas.keys()):
        dims = areas[area]
        scores = {d: float(dims.get(d, 0)) for d in DIMENSIONS}
        avg = sum(scores.values()) / len(DIMENSIONS)
        row: list[RenderableType | str] = [_humanize_area(area)]
        for dim in DIMENSIONS:
            row.append(_score_cell(scores[dim]))
        row.append(_score_cell(avg))
        table.add_row(*row)

    return table


def print_competence_profile(
    console: Console,
    user: "User",
    audit: "AuditLogger | None" = None,
) -> None:
    """Print the user's survey profile in color (main menu)."""
    profile = user.profile
    console.print()
    console.print(
        Panel.fit(
            f"[bold]{user.display_name}[/bold]\n[dim]Competence survey profile · scores 1–5[/dim]",
            title="Your profile",
            border_style="info",
        )
    )
    console.print(
        "[dim]█ = relative level · "
        "[red]red[/] <2.5 · [yellow]yellow[/] 2.5–3.4 · [cyan]cyan[/] 3.5–3.9 · [green]green[/] 4+[/dim]"
    )
    console.print()
    for domain_key in ("digital_competences", "ai_competences"):
        if profile.get(domain_key):
            console.print(_domain_table(profile, domain_key))
            console.print()
    console.print("[dim]Press Enter to return to the menu.[/dim]")
    try:
        input()
        if audit is not None:
            audit.log(
                "profile_dismissed",
                username=user.username,
                prompt="Press Enter to return to the menu",
            )
    except EOFError:
        if audit is not None:
            audit.log("profile_dismissed", username=user.username, reason="eof")
