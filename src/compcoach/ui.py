import os
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, TypeVar

from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner

if TYPE_CHECKING:
    pass

T = TypeVar("T")


@contextmanager
def wait_while(
    console: Console,
    message: str = "Thinking",
    *,
    spinner: str = "dots",
) -> Iterator[None]:
    """Spinner without redirecting stdout (avoids FileProxy shutdown errors)."""
    widget = Spinner(spinner, text=f"[info]{message}[/info]")
    live = Live(
        widget,
        console=console,
        transient=True,
        redirect_stdout=False,
        redirect_stderr=False,
    )
    with live:
        yield


def run_with_wait(
    console: Console,
    fn: Callable[[], T],
    message: str = "Thinking",
) -> T:
    with wait_while(console, message):
        return fn()


def restore_std_streams() -> None:
    """Unwrap Rich FileProxy and flush any pending bytes to the real stream."""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        while type(stream).__name__ == "FileProxy":
            buffer = getattr(stream, "_FileProxy__buffer", None)
            underlying = stream.rich_proxied_file
            if buffer:
                pending = "".join(buffer)
                if pending:
                    try:
                        underlying.write(pending)
                        underlying.flush()
                    except Exception:
                        pass
                buffer.clear()
            stream = underlying
        setattr(sys, name, stream)


def shutdown_console(console: Console) -> None:
    """Stop active Live displays and restore stdout/stderr."""
    live_stack = list(getattr(console, "_live_stack", []))
    for live in reversed(live_stack):
        try:
            live.stop()
        except Exception:
            pass
    restore_std_streams()


def exit_app(console: Console | None = None) -> None:
    """Clean shutdown message then hard exit (avoids Rich flush during interpreter teardown)."""
    if console is not None:
        shutdown_console(console)
    else:
        restore_std_streams()
    try:
        sys.stdout.write("\nGoodbye!\n")
        sys.stdout.flush()
    except Exception:
        pass
    os._exit(0)
