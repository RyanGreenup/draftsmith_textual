#!/usr/bin/env python3
import tempfile
import os
from iterfzf import iterfzf
from api import NoteAPI, Note
from typing import Dict, Optional
import typer
from rich import print as rprint

app = typer.Typer(help="Note selection and content display utility")


def get_note_content(
    note_id: int, base_url: str = "http://localhost:37240"
) -> Optional[str]:
    """Fetch the content of a note by its ID"""
    api = NoteAPI(base_url)
    try:
        note = api.get_note(note_id)
        return note.content or ""
    except Exception as e:
        rprint(f"[red]Error fetching note {note_id}: {e}[/red]")
        raise typer.Exit(code=1)


def create_preview_file(note: Note) -> str:
    """Create a temporary file containing the note content"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write(note.content or "")
        return f.name


@app.command()
def select_note(
    base_url: str = typer.Option("http://localhost:37240", help="API base URL"),
    return_content: bool = typer.Option(
        False, help="Return the content of the selected note (Defaults to ID)"
    ),
    show_paths: bool = typer.Option(
        True, help="Show full paths instead of just titles"
    ),
) -> None:
    """
    Interactive note selection using fzf.
    Shows note titles and previews content.
    """
    try:
        api = NoteAPI(base_url)
        notes = api.get_all_notes()

        # Get note paths if needed
        paths = api.get_all_note_paths() if show_paths else {}

        # Create mapping of display strings to notes and preview files
        display_to_note: Dict[str, Note] = {}
        preview_files: Dict[str, str] = {}

        for note in notes:
            if note.title:  # Only include notes with titles
                if show_paths:
                    display = paths.get(note.id, note.title.strip())
                else:
                    display = note.title.strip()
                display_to_note[display] = note
                preview_files[display] = create_preview_file(note)

        # Let user select from display strings with content preview
        this_dir = os.path.dirname(os.path.abspath(__file__))
        preview_cmd = os.path.join(this_dir, "fzf.py")
        preview_cmd = f"python {preview_cmd} show-content {{}} --base-url {base_url}"
        selected = iterfzf(
            display_to_note.keys(), preview=preview_cmd
        )

        if selected and isinstance(selected, str) and selected in display_to_note:
            # Print the ID of that note
            note = display_to_note[selected]
            if return_content:
                rprint(f"\n[bold]Selected note:[/bold] {note.title}")
                rprint("[bold]" + "-" * 40 + "[/bold]")
                print(note.content)
            else:
                print(note.id)

    except Exception as e:
        rprint(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(code=1)


@app.command()
def show_content(
    title: str,
    base_url: str = typer.Option("http://localhost:37240", help="API base URL"),
):
    """Display note content by title"""
    api = NoteAPI(base_url)
    notes = api.get_all_notes()

    # Find note by title
    for note in notes:
        if note.title and note.title.strip() == title:
            print(note.content or "")
            return

    rprint(f"[red]Note not found: {title}[/red]")
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
