import tempfile
import subprocess
import os
from datetime import datetime
from typing import Optional
from pathlib import Path

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
        ("right", "expand_node", "Expand"),
        ("left", "collapse_node", "Collapse"),
        ("e", "edit_note", "Edit Note"),
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
            # Create the root node first
            root = tree.root
            self._populate_tree(notes, root)
        except Exception as e:
            # Add error message to root node
            tree.root.add_leaf("Error loading notes: " + str(e))

    def _populate_tree(self, notes: list[api.TreeNote], parent: Tree | TreeNode) -> None:
        """Recursively populate the tree with notes."""
        for note in notes:
            # Create a node for this note
            node = parent.add(note.title, data=note, expand=True)  # expand=True shows all levels
            # Recursively add all children
            if note.children:
                for child in note.children:
                    self._populate_tree([child], node)  # Pass each child as a single-item list

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle note selection."""
        note = event.node.data
        if note and isinstance(note, api.TreeNote):
            viewer = self.query_one("#note-viewer", NoteViewer)
            viewer.display_note(note.content)

    def action_refresh(self) -> None:
        """Refresh the notes tree."""
        self.refresh_notes()

    def action_expand_node(self) -> None:
        """Expand the selected tree node."""
        tree = self.query_one("#notes-tree", Tree)
        if tree.cursor_node:
            tree.cursor_node.expand()

    def action_collapse_node(self) -> None:
        """Collapse the selected tree node."""
        tree = self.query_one("#notes-tree", Tree)
        if tree.cursor_node:
            tree.cursor_node.collapse()

    def action_edit_note(self) -> None:
        """Edit the current note in an external editor."""
        tree = self.query_one("#notes-tree", Tree)
        if not tree.cursor_node or not isinstance(tree.cursor_node.data, api.TreeNote):
            return

        note = tree.cursor_node.data
        
        # Create a temporary file with the note content
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as tmp:
            tmp.write(note.content or '')
            tmp_path = Path(tmp.name)

        try:
            # Suspend the TUI, restore terminal state
            with self.suspend():
                editor = os.environ.get('EDITOR', 'vim')
                result = subprocess.run([editor, str(tmp_path)], check=True)
            
            # Read the edited content after resuming TUI
            with open(tmp_path) as f:
                new_content = f.read()

            # Update the note via API
            self.notes_api.update_note(note.id, api.UpdateNoteRequest(content=new_content))
            
            # Update the viewer
            viewer = self.query_one("#note-viewer", NoteViewer)
            viewer.display_note(new_content)
            
            # Refresh the tree to show any title changes
            self.refresh_notes()
            
        except subprocess.CalledProcessError as e:
            self.notify("Failed to edit note", severity="error")
        finally:
            # Clean up temp file
            tmp_path.unlink()

if __name__ == "__main__":
    app = NotesApp()
    app.run()
