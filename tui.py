from datetime import datetime
from typing import Optional

from rich.markdown import Markdown
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Container, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Footer, Header, Static, Tree
from textual.widgets.tree import TreeNode
import api

class NoteViewer(Static):
    """Widget to display note content"""
    
    def display_note(self, content: Optional[str]) -> None:
        """Update the display with note content"""
        if content:
            # Render markdown content
            markdown = Markdown(content)
            self.update(markdown)
        else:
            self.update("No content")

class NotesApp(App):
    """Notes viewing application."""

    CSS = """
    Tree {
        width: 30%;
        dock: left;
    }
    
    NoteViewer {
        width: 70%;
        dock: right;
        background: $surface;
        padding: 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
    ]

    def __init__(self):
        super().__init__()
        self.notes_api = api.NoteAPI("http://localhost:37240")

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header()
        yield Container(
            Tree("Notes", id="notes-tree"),
            NoteViewer(id="note-viewer"),
        )
        yield Footer()

    def on_mount(self) -> None:
        """Load the notes tree when the app starts."""
        self.refresh_notes()

    def refresh_notes(self) -> None:
        """Refresh the notes tree from the API."""
        tree = self.query_one("#notes-tree", Tree)
        tree.clear()
        
        try:
            notes = self.notes_api.get_notes_tree()
            self._populate_tree(notes, tree)
        except Exception as e:
            tree.root.add("Error loading notes: " + str(e))

    def _populate_tree(self, notes: list[api.TreeNote], parent: Tree | TreeNode) -> None:
        """Recursively populate the tree with notes."""
        for note in notes:
            node = parent.add(note.title, data=note)
            if note.children:
                self._populate_tree(note.children, node)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle note selection."""
        note = event.node.data
        if note and isinstance(note, api.TreeNote):
            viewer = self.query_one("#note-viewer", NoteViewer)
            viewer.display_note(note.content)

    def action_refresh(self) -> None:
        """Refresh the notes tree."""
        self.refresh_notes()

if __name__ == "__main__":
    app = NotesApp()
    app.run()
