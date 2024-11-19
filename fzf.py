#!/usr/bin/env python3
import tempfile
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
) -> None:
    """
    Interactive note selection using fzf.
    Shows note titles and previews content.
    """
    try:
        api = NoteAPI(base_url)
        notes = api.get_all_notes()

        # Create mapping of titles to notes and preview files
        title_to_note: Dict[str, Note] = {}
        preview_files: Dict[str, str] = {}

        for note in notes:
            if note.title:  # Only include notes with titles
                clean_title = note.title.strip()
                title_to_note[clean_title] = note
                preview_files[clean_title] = create_preview_file(note)

        # Let user select from titles with content preview
        selected = iterfzf(
            title_to_note.keys(), preview="python fzf.py show-content {}"
        )

        if selected and isinstance(selected, str) and selected in title_to_note:
            # Print the ID of that note
            note = title_to_note[selected]
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
