#!/usr/bin/env python3

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static
from textual.widgets.markdown import Markdown
from textual.screen import ModalScreen
from typing import List
import api


# NOTE this class is not using the API to render the markdown
# It uses the content directly
# Given this is just a quick popup, we'll keep the code simple.
class PopupScreen(ModalScreen):
    """A popup screen that displays a list of notes with preview."""

    BINDINGS = [
        ("b", "close_popup", "Close"),
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("enter", "select_note", "Select"),  # Add this binding
    ]

    def __init__(self, notes: List[api.Note]):
        super().__init__()
        self.notes = notes
        self.current_index = 0 if notes else -1

    def compose(self) -> ComposeResult:
        yield Container(
            Container(
                Static(self._get_notes_list_text(), id="notes-list"),
                id="notes-list-container",
            ),
            Container(
                Markdown(self._get_current_preview(), id="preview"),
                id="preview-container",
            ),
            id="popup-container",
        )

    def _get_notes_list_text(self) -> str:
        """Generate the text display for the notes list."""
        lines = []
        for i, note in enumerate(self.notes):
            prefix = ">" if i == self.current_index else " "
            lines.append(f"{prefix} {note.title}")
        return "\n".join(lines) if lines else "No notes to display"

    def _get_current_preview(self) -> str:
        """Get the preview text for the currently selected note."""
        if 0 <= self.current_index < len(self.notes):
            return self.notes[self.current_index].content or "No content"
        return "No note selected"

    def _refresh_display(self) -> None:
        """Refresh both the list and preview displays."""
        self.query_one("#notes-list", Static).update(self._get_notes_list_text())
        try:
            self.query_one("#preview", Markdown).update(self._get_current_preview())
        except Exception:
            pass

    def action_cursor_down(self) -> None:
        """Move cursor down in the list."""
        if self.notes and self.current_index < len(self.notes) - 1:
            self.current_index += 1
            self._refresh_display()

    def action_cursor_up(self) -> None:
        """Move cursor up in the list."""
        if self.notes and self.current_index > 0:
            self.current_index -= 1
            self._refresh_display()

    def action_close_popup(self) -> None:
        """Close the popup screen."""
        self.app.pop_screen()

    def action_select_note(self) -> None:
        """Handle note selection with Enter key."""
        if 0 <= self.current_index < len(self.notes):
            selected_note = self.notes[self.current_index]
            # Pop screen first, then select the note in the main app
            self.app.pop_screen()
            # Use call_after_refresh to ensure the main app is ready
            self.app.call_after_refresh(
                lambda: self.app.select_node_by_id(selected_note.id)
            )
