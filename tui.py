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
from textual.widgets import Input
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


class FilterDialog(Container):
    DEFAULT_CSS = """
    FilterDialog {
        background: $boost;
        height: 3;  # Reduce height to 3 lines
        width: 60%;  # Set width to 60% of screen
        margin: 1 0 0 0;  # Add margin at top
        padding: 0;  # Remove padding
        border: tall $background;  # Change border style
        dock: top;  # Dock to top of screen
    }
    """

    def compose(self) -> ComposeResult:
        placeholder = (
            "Enter search text..."
            if isinstance(self.app, NotesApp) and self.app.dialog_mode == "search"
            else "Enter filter text..."
        )
        value = (
            (
                self.app.last_search
                if isinstance(self.app, NotesApp) and self.app.dialog_mode == "search"
                else self.app.last_filter
            )
            if isinstance(self.app, NotesApp)
            else ""
        )
        yield Input(placeholder=placeholder, value=value)

    def on_mount(self) -> None:
        input_widget = self.query_one(Input)
        input_widget.focus()
        if isinstance(self.app, NotesApp):
            value = (
                self.app.last_search
                if self.app.dialog_mode == "search"
                else self.app.last_filter
            )
            input_widget.cursor_position = len(value)

    def on_input_changed(self, event: Input.Changed) -> None:
        if isinstance(self.app, NotesApp):
            self.app.handle_filter_change(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if isinstance(self.app, NotesApp):
            self.app.handle_filter_submit()


class NotesApp(App):
    """Notes viewing application."""

    last_filter: str = ""  # Store the last filter query
    last_search: str = ""  # Store the last search query
    dialog_mode: str = "filter"  # Current dialog mode

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
        align: center top;
    }

    FilterDialog Input {
        width: 100%;  # Make input take full width
        margin: 0;  # Remove margin
        border: none;  # Remove border
        height: 3;  # Match container height
        background: $boost;  # Match container background
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("right", "expand_node", "Expand"),
        ("left", "collapse_node", "Collapse"),
        ("l", "expand_node", "Expand"),
        ("h", "collapse_node", "Collapse"),
        ("e", "edit_note", "Edit Note"),
        ("f", "filter_notes", "Filter Notes"),
        ("s", "search_notes", "Search Notes"),
        ("o", "unfold_tree", "Unfold All"),
        ("F", "toggle_follow", "Follow Mode"),
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
    ]

    follow_mode = reactive(True)

    def __init__(self):
        super().__init__()
        self.notes_api = api.NoteAPI("http://localhost:37240")
        self.last_search = ""
        self.last_filter = ""
        self.dialog_mode = "filter"  # Can be "filter" or "search"

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

    def _filter_notes_by_ids(
        self, notes: List[api.TreeNote], matching_ids: set[int]
    ) -> List[api.TreeNote]:
        """Filter notes tree to only include paths to matching IDs."""
        filtered = []

        for note in notes:
            current_note = api.TreeNote(
                id=note.id, title=note.title, content=note.content, children=[]
            )

            # Recursively filter children
            filtered_children = (
                self._filter_notes_by_ids(note.children, matching_ids)
                if note.children
                else []
            )

            # Include note if it matches or has matching children
            if note.id in matching_ids or filtered_children:
                current_note.children = filtered_children
                filtered.append(current_note)

        return filtered

    def _filter_notes(
        self, notes: List[api.TreeNote], query: str
    ) -> List[api.TreeNote]:
        """Filter notes based on presence of all query characters."""
        if not query:
            return notes

        filtered = []
        query_chars = set(query.lower())

        for note in notes:
            current_note = api.TreeNote(
                id=note.id, title=note.title, content=note.content, children=[]
            )

            # Check if all query characters are present in the title
            title_chars = set(note.title.lower())
            title_matches = all(char in title_chars for char in query_chars)

            # Recursively filter children
            filtered_children = (
                self._filter_notes(note.children, query) if note.children else []
            )

            # Include note if it matches or has matching children
            if title_matches or filtered_children:
                current_note.children = filtered_children
                filtered.append(current_note)
        return filtered

    def _get_expanded_nodes(self, node: TreeNode) -> set[str]:
        """Get the titles of all expanded nodes in the tree."""
        expanded = set()
        if node.is_expanded:
            expanded.add(str(node.label))
            for child in node.children:
                expanded.update(self._get_expanded_nodes(child))
        return expanded

    def _restore_expanded_nodes(self, node: TreeNode, expanded_nodes: set[str]) -> None:
        """Restore the expanded state of nodes."""
        if str(node.label) in expanded_nodes:
            node.expand()
        for child in node.children:
            self._restore_expanded_nodes(child, expanded_nodes)

    def refresh_notes(self) -> None:
        """Refresh the notes tree from the API while preserving expanded state."""
        tree = self.query_one("#notes-tree", Tree)

        # Store expanded state before clearing
        expanded_nodes = self._get_expanded_nodes(tree.root)

        tree.clear()

        try:
            notes = self.notes_api.get_notes_tree()
            # Create the root node first
            root = tree.root
            self._populate_tree(notes, root)
            # Restore expanded state
            self._restore_expanded_nodes(root, expanded_nodes)
        except Exception as e:
            # Add error message to root node
            tree.root.add_leaf("Error loading notes: " + str(e))

    def _populate_tree(
        self, notes: list[api.TreeNote], parent: Tree | TreeNode
    ) -> None:
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
                    self._populate_tree(
                        [child], node
                    )  # Pass each child as a single-item list

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        """Handle node highlight changes."""
        if self.follow_mode:
            note = event.node.data
            if note and isinstance(note, api.TreeNote):
                viewer = self.query_one("#note-viewer", NoteViewer)
                viewer.display_note(note.content)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle note selection."""
        if not self.follow_mode:
            note = event.node.data
            if note and isinstance(note, api.TreeNote):
                viewer = self.query_one("#note-viewer", NoteViewer)
                viewer.display_note(note.content)

    def action_toggle_follow(self) -> None:
        """Toggle follow mode."""
        self.follow_mode = not self.follow_mode
        self.notify(f"Follow mode {'enabled' if self.follow_mode else 'disabled'}")

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

    def _unfold_node(self, node: TreeNode) -> None:
        """Recursively unfold a node and all its children."""
        node.expand()
        for child in node.children:
            self._unfold_node(child)

    def action_unfold_tree(self) -> None:
        """Unfold the entire tree."""
        tree = self.query_one("#notes-tree", Tree)
        self._unfold_node(tree.root)

    def action_cursor_down(self) -> None:
        """Move cursor down in the tree."""
        tree = self.query_one("#notes-tree", Tree)
        tree.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up in the tree."""
        tree = self.query_one("#notes-tree", Tree)
        tree.action_cursor_up()

    def action_edit_note(self) -> None:
        """Edit the current note in an external editor."""
        tree = self.query_one("#notes-tree", Tree)
        if not tree.cursor_node or not isinstance(tree.cursor_node.data, api.TreeNote):
            return

        note = tree.cursor_node.data

        # Create a temporary file with the note content
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tmp:
            tmp.write(note.content or "")
            tmp_path = Path(tmp.name)

        try:
            # Suspend the TUI, restore terminal state
            with self.suspend():
                editor = os.environ.get("EDITOR", "vim")
                result = subprocess.run([editor, str(tmp_path)], check=True)

            # Read the edited content after resuming TUI
            with open(tmp_path) as f:
                new_content = f.read()

            # Update the note via API
            self.notes_api.update_note(
                note.id, api.UpdateNoteRequest(content=new_content)
            )

            # Update the viewer
            viewer = self.query_one("#note-viewer", NoteViewer)
            viewer.display_note(new_content)

            # Refresh the tree and reapply filter if one exists
            if self.last_filter:
                # Refresh and filter
                notes = self.notes_api.get_notes_tree()
                filtered_notes = self._filter_notes(notes, self.last_filter)
                tree = self.query_one("#notes-tree", Tree)
                tree.clear()
                self._populate_tree(filtered_notes, tree)
                self._unfold_node(tree.root)
            else:
                # Just refresh normally
                self.refresh_notes()

        except subprocess.CalledProcessError as e:
            self.notify("Failed to edit note", severity="error")
        finally:
            # Clean up temp file
            tmp_path.unlink()

    def handle_filter_change(self, value: str) -> None:
        """Handle input changes in the filter dialog."""
        if self.dialog_mode == "search":
            self.last_search = value
            if not value:
                self.refresh_notes()
                return

            tree = self.query_one("#notes-tree", Tree)
            tree.clear()

            try:
                # Get search results and extract IDs
                search_results = self.notes_api.search_notes(value)
                matching_ids = {note.id for note in search_results}

                # Get full tree and filter it based on matching IDs
                notes = self.notes_api.get_notes_tree()
                filtered_notes = self._filter_notes_by_ids(notes, matching_ids)

                # Populate tree with filtered results
                root = tree.root
                self._populate_tree(filtered_notes, root)
                self._unfold_node(tree.root)
            except Exception as e:
                tree.root.add_leaf("Error searching notes: " + str(e))
        else:
            # Original filter logic
            self.last_filter = value
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
                self._unfold_node(tree.root)
            except Exception as e:
                tree.root.add_leaf("Error filtering notes: " + str(e))

    def handle_filter_submit(self) -> None:
        """Handle input submission in the dialog."""
        dialog = self.query_one(FilterDialog)
        if dialog:
            dialog.remove()

    async def action_filter_notes(self) -> None:
        """Filter notes based on fuzzy string matching."""
        self.dialog_mode = "filter"
        await self.mount(FilterDialog())

    async def action_search_notes(self) -> None:
        """Search notes using the API search function."""
        self.dialog_mode = "search"
        await self.mount(FilterDialog())

    def handle_input_change(self, value: str) -> None:
        """Handle input changes in the filter dialog."""
        if self.dialog_mode == "search":
            self.last_search = value
            if not value:
                self.refresh_notes()
                return

            tree = self.query_one("#notes-tree", Tree)
            tree.clear()

            try:
                # Get search results
                search_results = self.notes_api.search_notes(value)

                # Convert search results to TreeNote format
                tree_notes = [
                    api.TreeNote(
                        id=note.id, title=note.title, content=note.content, children=[]
                    )
                    for note in search_results
                ]

                # Populate tree with results
                root = tree.root
                self._populate_tree(tree_notes, root)
                self._unfold_node(tree.root)
            except Exception as e:
                tree.root.add_leaf("Error searching notes: " + str(e))
        else:
            # Original filter logic
            self.last_filter = value
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
                self._unfold_node(tree.root)
            except Exception as e:
                tree.root.add_leaf("Error filtering notes: " + str(e))

    def handle_input_submit(self) -> None:
        """Handle input submission in the dialog."""
        dialog = self.query_one(FilterDialog)
        if dialog:
            dialog.remove()


if __name__ == "__main__":
    app = NotesApp()
    app.run()
