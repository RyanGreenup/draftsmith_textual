import tempfile
import subprocess
import os
import asyncio
import socket
import json
import tempfile
import subprocess
import os
import asyncio
import socket
import json
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
    marked_for_move: set[int] = set()  # Store IDs of notes marked for moving

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

    Footer {
        background: $boost;
        color: $text;
        padding: 0 1;
    }

    Footer > .footer--key {
        background: $primary-darken-2;
        color: $text;
        padding: 0 1;
        margin: 0 1 0 0;
        border: none;
    }

    Footer > .footer--highlight {
        background: $primary-darken-3;
        color: $text;
    }

    Footer > .footer--description {
        color: $text-muted;
        padding: 0 2 0 0;
    }
    """

    BINDINGS = [
        # Navigation
        ("j", "cursor_down", "↓"),
        ("k", "cursor_up", "↑"),
        ("h", "collapse_node", "←"),
        ("l", "expand_node", "→"),
        # Folding
        ("z", "fold_cycle", "Fold →"),
        ("Z", "fold_cycle_reverse", "← Fold"),
        ("o", "unfold_tree", "Unfold"),
        ("O", "fold_to_first", "Level 1"),
        # Actions
        ("e", "edit_note", "Edit"),
        ("E", "gui_edit_note", "GUI Edit"),
        ("f", "filter_notes", "Filter"),
        ("s", "search_notes", "Search"),
        ("F", "toggle_follow", "Follow"),
        ("r", "refresh", "Refresh"),
        ("f5", "toggle_flat_view", "Flat View"),
        ("g", "connect_gui", "GUI Preview"),
        ("G", "toggle_auto_sync", "Toggle Auto-sync"),
        ("x", "mark_for_move", "Mark"),
        ("p", "paste_as_children", "Paste"),
        ("escape", "clear_marks", "Clear marks"),
        ("n", "new_note", "New Note"),
        ("d", "delete_note", "Delete"),
        # System
        ("q", "quit", "Quit"),
    ]

    follow_mode = reactive(True)
    auto_sync_gui = reactive(False)

    def __init__(
        self,
        base_url: str = "http://localhost:37240",
        socket_path: str = "/tmp/markdown_preview.sock",
    ):
        super().__init__()
        self.notes_api = api.NoteAPI(base_url)
        self.last_search = ""
        self.last_filter = ""
        self.dialog_mode = "filter"  # Can be "filter" or "search"
        self.current_fold_level = 0  # Track current fold level
        self.flat_view = False  # Track if we're in flat view mode
        self.socket_path = socket_path  # Store socket path

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
        # Fold to first level on startup
        tree = self.query_one("#notes-tree", Tree)
        self.current_fold_level = 1
        self._fold_to_level(tree.root, 1)

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
            # Create label with visual indicator if note is marked
            label = (
                f"[red]*[/red] {note.title}"
                if note.id in self.marked_for_move
                else note.title
            )

            # Create a node for this note
            if isinstance(parent, Tree):
                node = parent.root.add(label, data=note)
            else:
                # Use add_leaf for nodes without children, add for nodes with children
                if note.children:
                    node = parent.add(label, data=note)
                else:
                    node = parent.add_leaf(label, data=note)
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

                # Auto-sync to GUI if enabled
                if self.auto_sync_gui:
                    self.connect_to_gui()

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

    def _get_node_level(self, node: TreeNode) -> int:
        """Get the level of a node in the tree (root is 0)."""
        level = 0
        current = node
        while current.parent is not None:
            level += 1
            current = current.parent
        return level

    def _fold_to_level(self, node: TreeNode, target_level: int) -> None:
        """Fold/unfold nodes to show up to target_level."""
        current_level = self._get_node_level(node)

        # Always process the root node
        if current_level <= target_level:
            node.expand()
            # Process children recursively
            for child in node.children:
                self._fold_to_level(child, target_level)
        else:
            node.collapse()

    def action_fold_cycle(self) -> None:
        """Cycle through fold levels (expanding)."""
        tree = self.query_one("#notes-tree", Tree)

        # Calculate next fold level
        if self.current_fold_level == 0:
            self.current_fold_level = 1
        else:
            self.current_fold_level *= 2

        # If we've gone too deep, reset to 0
        max_depth = self._get_max_depth(tree.root)
        if self.current_fold_level > max_depth:
            self.current_fold_level = 0
            tree.root.collapse_all()
            return

        # Apply the new fold level
        self._fold_to_level(tree.root, self.current_fold_level)

        # Notify user
        self.notify(f"Fold level: {self.current_fold_level}")

    def action_fold_cycle_reverse(self) -> None:
        """Cycle through fold levels (collapsing)."""
        tree = self.query_one("#notes-tree", Tree)

        # Calculate previous fold level
        if self.current_fold_level <= 1:
            self.current_fold_level = 0
            tree.root.collapse_all()
        else:
            self.current_fold_level //= 2
            self._fold_to_level(tree.root, self.current_fold_level)

        # Notify user
        self.notify(f"Fold level: {self.current_fold_level}")

    def _get_max_depth(self, node: TreeNode) -> int:
        """Get the maximum depth of the tree."""
        if not node.children:
            return self._get_node_level(node)
        return max(self._get_max_depth(child) for child in node.children)

    def action_fold_to_first(self) -> None:
        """Fold tree to show only first level items."""
        tree = self.query_one("#notes-tree", Tree)
        self.current_fold_level = 1
        self._fold_to_level(tree.root, 1)
        self.notify("Folded to first level")

    def action_unfold_tree(self) -> None:
        """Unfold the entire tree."""
        tree = self.query_one("#notes-tree", Tree)
        self._unfold_node(tree.root)
        self.current_fold_level = self._get_max_depth(tree.root)

    def connect_to_gui(self) -> None:
        """Connect to the GUI preview via Unix Domain Socket."""
        try:
            # Get current note ID
            tree = self.query_one("#notes-tree", Tree)
            if not tree.cursor_node or not isinstance(
                tree.cursor_node.data, api.TreeNote
            ):
                self.notify("No note selected", severity="warning")
                return

            note = tree.cursor_node.data
            note_id = note.id

            # Try to connect and send the note ID
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                try:
                    sock.connect(self.socket_path)
                    message = json.dumps({"command": "set_note", "note_id": note_id})
                    sock.sendall(message.encode())
                    # Only notify if this was triggered by manual action (not auto-sync)
                    if not self.auto_sync_gui:
                        self.notify("Connected to GUI preview")
                except FileNotFoundError:
                    self.notify(
                        f"GUI preview not running. Start it with: python markdown_preview.py --socket-path {self.socket_path}",
                        severity="error",
                    )
                except ConnectionRefusedError:
                    self.notify("Could not connect to GUI preview", severity="error")

        except Exception as e:
            self.notify(f"Error connecting to GUI preview: {str(e)}", severity="error")

    def action_cursor_down(self) -> None:
        """Move cursor down in the tree."""
        tree = self.query_one("#notes-tree", Tree)
        tree.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up in the tree."""
        tree = self.query_one("#notes-tree", Tree)
        tree.action_cursor_up()

    async def _edit_note_with_editor(
        self, editor_cmd: str, suspend: bool = True
    ) -> None:
        """Edit the current note with specified editor command."""
        tree = self.query_one("#notes-tree", Tree)
        if not tree.cursor_node or not isinstance(tree.cursor_node.data, api.TreeNote):
            return

        note = tree.cursor_node.data

        # Create a temporary file with the note content
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tmp:
            tmp.write(note.content or "")
            tmp_path = Path(tmp.name)

        try:
            if suspend:
                # Suspend the TUI, restore terminal state
                with self.suspend():
                    result = subprocess.run([editor_cmd, str(tmp_path)], check=True)
                # Refresh footer after resuming
                self.query_one(Footer).refresh()
            else:
                # Run async without suspending TUI
                process = await asyncio.create_subprocess_exec(
                    editor_cmd,
                    str(tmp_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await process.wait()

            # Read the edited content
            with open(tmp_path) as f:
                new_content = f.read()

            # Update the note via API
            self.notes_api.update_note(
                note.id, api.UpdateNoteRequest(content=new_content)
            )

            # Update the viewer
            viewer = self.query_one("#note-viewer", NoteViewer)
            viewer.display_note(new_content)

            # Refresh the tree and reapply filter/search if one exists
            if self.last_filter:
                self._apply_filter(self.last_filter)
            elif self.last_search:
                self._apply_search(self.last_search)
            else:
                self.refresh_notes()

        except (subprocess.CalledProcessError, OSError) as e:
            self.notify(f"Failed to edit note: {str(e)}", severity="error")
        finally:
            # Clean up temp file
            tmp_path.unlink()

    async def action_edit_note(self) -> None:
        """Edit the current note in an external editor."""
        editor = os.environ.get("EDITOR", "vim")
        await self._edit_note_with_editor(editor, suspend=True)

    async def action_gui_edit_note(self) -> None:
        """Edit the current note in a GUI editor."""
        editor = os.environ.get("GUI_EDITOR")
        if not editor:
            self.notify("GUI_EDITOR environment variable not set", severity="error")
            return
        await self._edit_note_with_editor(editor, suspend=False)

    def _flatten_filtered_notes(self, notes: List[api.TreeNote]) -> List[api.TreeNote]:
        """Convert hierarchical filtered notes into a flat list."""
        flattened = []

        def collect_matches(note: api.TreeNote):
            # If this note has no children, it must be a match
            if not note.children:
                flattened.append(
                    api.TreeNote(
                        id=note.id, title=note.title, content=note.content, children=[]
                    )
                )
            # If it has children, recurse and collect matches
            else:
                for child in note.children:
                    collect_matches(child)

        for note in notes:
            collect_matches(note)

        return flattened

    def action_toggle_flat_view(self) -> None:
        """Toggle between flat and hierarchical view for filtered results."""
        self.flat_view = not self.flat_view

        # Immediately refresh the view while preserving any active search/filter
        if self.last_search:
            self._apply_search(self.last_search)
        elif self.last_filter:
            self._apply_filter(self.last_filter)
        else:
            # If no search/filter active, just refresh the normal tree
            self.refresh_notes()

        self.notify(f"{'Flat' if self.flat_view else 'Hierarchical'} view")

    def action_connect_gui(self) -> None:
        """Connect to GUI preview."""
        self.connect_to_gui()

    def action_toggle_auto_sync(self) -> None:
        """Toggle automatic GUI preview sync."""
        self.auto_sync_gui = not self.auto_sync_gui
        self.notify(f"Auto-sync {'enabled' if self.auto_sync_gui else 'disabled'}")

        # Only refresh if we're currently filtering/searching
        if self.last_filter or self.last_search:
            if self.dialog_mode == "search":
                self._apply_search(self.last_search)
            else:
                self._apply_filter(self.last_filter)

    def action_mark_for_move(self) -> None:
        """Mark current note for moving."""
        tree = self.query_one("#notes-tree", Tree)
        if not tree.cursor_node or not isinstance(tree.cursor_node.data, api.TreeNote):
            self.notify("No note selected", severity="warning")
            return

        note = tree.cursor_node.data
        if note.id in self.marked_for_move:
            self.marked_for_move.remove(note.id)
            self.notify(f"Unmarked note: {note.title}")
        else:
            self.marked_for_move.add(note.id)
            self.notify(f"Marked note: {note.title}")

        # Refresh the tree to show visual indicators
        # Preserve current filter/search state
        if self.last_filter:
            self._apply_filter(self.last_filter)
        elif self.last_search:
            self._apply_search(self.last_search)
        else:
            self.refresh_notes()

    def action_paste_as_children(self) -> None:
        """Attach marked notes as children to current note."""
        if not self.marked_for_move:
            self.notify("No notes marked for moving", severity="warning")
            return

        tree = self.query_one("#notes-tree", Tree)
        if not tree.cursor_node or not isinstance(tree.cursor_node.data, api.TreeNote):
            self.notify("No target note selected", severity="warning")
            return

        target_note = tree.cursor_node.data

        try:
            for note_id in self.marked_for_move:
                # First detach from current parent
                try:
                    self.notes_api.detach_note_from_parent(note_id)
                except Exception:
                    # Ignore error if note doesn't have a parent
                    pass

                # Then attach to new parent
                self.notes_api.attach_note_to_parent(note_id, target_note.id)

            self.notify(
                f"Moved {len(self.marked_for_move)} notes as children of: {target_note.title}"
            )
            self.marked_for_move.clear()
            self.refresh_notes()
        except Exception as e:
            self.notify(f"Error moving notes: {str(e)}", severity="error")

    def action_clear_marks(self) -> None:
        """Clear all marked notes."""
        count = len(self.marked_for_move)
        self.marked_for_move.clear()
        self.notify(f"Cleared {count} marked notes")

        # Refresh the tree to remove visual indicators
        # Preserve current filter/search state
        if self.last_filter:
            self._apply_filter(self.last_filter)
        elif self.last_search:
            self._apply_search(self.last_search)
        else:
            self.refresh_notes()

    def action_delete_note(self) -> None:
        """Delete the current note after confirmation."""
        tree = self.query_one("#notes-tree", Tree)
        if not tree.cursor_node or not isinstance(tree.cursor_node.data, api.TreeNote):
            self.notify("No note selected", severity="warning")
            return

        note = tree.cursor_node.data
        try:
            # Delete the note
            self.notes_api.delete_note(note.id)

            # Clear the viewer
            viewer = self.query_one("#note-viewer", NoteViewer)
            viewer.display_note(None)

            # Refresh the tree view
            self.refresh_notes()

            # Notify user
            self.notify(f"Deleted note: {note.title}")

        except Exception as e:
            self.notify(f"Error deleting note: {str(e)}", severity="error")

    def action_new_note(self) -> None:
        """Create a new note and attach it to the current note."""
        try:
            # Get current note
            tree = self.query_one("#notes-tree", Tree)

            # Create a new note with default title and empty content
            title = datetime.now().strftime("New Note %Y-%m-%d %H:%M:%S")
            new_note = self.notes_api.create_note(title=title, content="")
            new_note_id = new_note["id"]  # Store the new note's ID

            # Attach as a Child of the current note
            if not tree.cursor_node or not isinstance(
                tree.cursor_node.data, api.TreeNote
            ):
                self.notify("No parent note selected", severity="warning")
            else:
                current_note = tree.cursor_node.data
                # Attach it to the current note
                self.notes_api.attach_note_to_parent(new_note_id, current_note.id)
                # Notify user
                self.notify(f"Created new note as child of: {current_note.title}")

            # Refresh the tree view
            self.refresh_notes()

            # Find and focus the new note
            def focus_new_note(node: TreeNode) -> bool:
                if isinstance(node.data, api.TreeNote) and node.data.id == new_note_id:
                    # Expand all parent nodes
                    parent = node.parent
                    while parent and parent != tree.root:
                        parent.expand()
                        parent = parent.parent
                    tree.root.expand()  # Ensure root is expanded
                    
                    # Set cursor to the new node
                    tree.cursor_node = node
                    # Scroll to make the node visible
                    node.scroll_visible()
                    return True
                for child in node.children:
                    if focus_new_note(child):
                        return True
                return False

            # Focus the new note
            focus_new_note(tree.root)

            # Start editing the new note immediately
            self.app.set_timer(0.1, self.action_edit_note)

        except Exception as e:
            self.notify(f"Error creating note: {str(e)}", severity="error")

    def _apply_search(self, value: str) -> None:
        """Apply search with current view mode."""
        tree = self.query_one("#notes-tree", Tree)
        tree.clear()

        try:
            # Get search results
            search_results = self.notes_api.search_notes(value)

            if self.flat_view:
                # In flat view, directly use search results in their original order
                filtered_notes = [
                    api.TreeNote(
                        id=note.id, title=note.title, content=note.content, children=[]
                    )
                    for note in search_results
                ]
            else:
                # For hierarchical view, preserve paths but order matched leaves by search order
                matching_ids = {note.id: idx for idx, note in enumerate(search_results)}
                notes = self.notes_api.get_notes_tree()
                filtered_notes = self._filter_notes_by_ids(
                    notes, set(matching_ids.keys())
                )

                # Sort the leaf nodes based on search order
                def sort_by_search_order(
                    notes: List[api.TreeNote],
                ) -> List[api.TreeNote]:
                    # Sort immediate children
                    notes.sort(
                        key=lambda n: matching_ids.get(n.id, float("inf"))
                        if not n.children
                        else -1
                    )
                    # Recursively sort children's children
                    for note in notes:
                        if note.children:
                            note.children = sort_by_search_order(note.children)
                    return notes

                filtered_notes = sort_by_search_order(filtered_notes)

            # Apply additional filter if one exists
            if self.last_filter:
                filtered_notes = self._filter_notes(filtered_notes, self.last_filter)

            # Populate tree with filtered results
            root = tree.root
            self._populate_tree(filtered_notes, root)
            self._unfold_node(tree.root)
        except Exception as e:
            tree.root.add_leaf("Error searching notes: " + str(e))

    def _apply_filter(self, value: str) -> None:
        """Apply filter with current view mode."""
        tree = self.query_one("#notes-tree", Tree)
        tree.clear()

        try:
            # If there's an active search, filter those results
            if self.last_search:
                self._apply_search(self.last_search)  # This will also apply the filter
                return

            # Otherwise filter the full tree
            notes = self.notes_api.get_notes_tree()
            filtered_notes = self._filter_notes(notes, value)

            # Convert to flat view if needed
            if self.flat_view:
                filtered_notes = self._flatten_filtered_notes(filtered_notes)

            root = tree.root
            self._populate_tree(filtered_notes, root)
            self._unfold_node(tree.root)
        except Exception as e:
            tree.root.add_leaf("Error filtering notes: " + str(e))

    def handle_filter_change(self, value: str) -> None:
        """Handle input changes in the filter dialog."""
        if self.dialog_mode == "search":
            self.last_search = value
            if not value:
                self.refresh_notes()
                return
            self._apply_search(value)
        else:
            # Filter logic
            self.last_filter = value
            if not value:
                self.refresh_notes()
                return
            self._apply_filter(value)

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
