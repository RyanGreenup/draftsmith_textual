import tempfile
import subprocess
import os
from datetime import datetime
from typing import Optional, List
from Levenshtein import distance
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

    FilterDialog {
        align: center middle;
    }

    FilterDialog Input {
        width: 80%;
        margin: 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("right", "expand_node", "Expand"),
        ("left", "collapse_node", "Collapse"),
        ("e", "edit_note", "Edit Note"),
        ("f", "filter_notes", "Filter Notes"),
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

    def _filter_notes(self, notes: List[api.TreeNote], query: str, max_distance: int = 3) -> List[api.TreeNote]:
        """Filter notes based on fuzzy string matching."""
        filtered = []
        for note in notes:
            # Check if the current note matches
            if distance(query.lower(), note.title.lower()) <= max_distance:
                # If it matches, include it with empty children
                filtered.append(api.TreeNote(
                    id=note.id,
                    title=note.title,
                    content=note.content,
                    children=[]
                ))
            # Recursively filter children
            if note.children:
                filtered_children = self._filter_notes(note.children, query)
                if filtered_children:
                    # If any children match, include this note with only matching children
                    if not any(n.id == note.id for n in filtered):
                        filtered.append(api.TreeNote(
                            id=note.id,
                            title=note.title,
                            content=note.content,
                            children=filtered_children
                        ))
                    else:
                        # Update existing note's children
                        for existing in filtered:
                            if existing.id == note.id:
                                existing.children = filtered_children
        return filtered

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
            if isinstance(parent, Tree):
                node = parent.root.add(note.title, data=note)
            else:
                # Use add_leaf for nodes without children, add for nodes with children
                if note.children:
                    node = parent.add(note.title, data=note)
                else:
                    node = parent.add_leaf(note.title, data=note)
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
            
    async def handle_input_change(self, value: str) -> None:
        """Handle input changes in the filter dialog."""
        if not value:
            self.refresh_notes()
            return
            
        tree = self.query_one("#notes-tree", Tree)
        tree.clear()
        
        try:
            notes = self.notes_api.get_notes_tree()
            filtered_notes = self._filter_notes(notes, value)
            root = tree.root
            self._populate_tree(filtered_notes, root)
        except Exception as e:
            tree.root.add_leaf("Error filtering notes: " + str(e))

    def handle_input_submit(self) -> None:
        """Handle input submission in the filter dialog."""
        dialog = self.query_one(FilterDialog)
        if dialog:
            dialog.remove()

    async def action_filter_notes(self) -> None:
        """Filter notes based on fuzzy string matching."""
        from textual.widgets import Input
        from textual.containers import Container
        
        class FilterDialog(Container):
            DEFAULT_CSS = """
            FilterDialog {
                background: $boost;
                height: auto;
                padding: 1;
                border: thick $background;
            }
            """
            
            def compose(self) -> ComposeResult:
                yield Input(placeholder="Enter filter text...")

            def on_mount(self) -> None:
                self.query_one(Input).focus()

            def on_input_changed(self, event: Input.Changed) -> None:
                self.app.handle_input_change(event.value)

            def on_input_submitted(self, event: Input.Submitted) -> None:
                self.app.handle_input_submit()
        
        await self.mount(FilterDialog())

if __name__ == "__main__":
    app = NotesApp()
    app.run()
