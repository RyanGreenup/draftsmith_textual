from datetime import datetime
from pathlib import Path
from textual.widgets import Tree
from textual.widgets.tree import TreeNode
from typing import Optional, List, Set
import api
import asyncio
import json
import socket
import subprocess
import tempfile


class NoteTreeManager:
    """Handles all tree-related operations"""

    def __init__(self, notes_api: api.NoteAPI):
        self.notes_api = notes_api
        self.current_fold_level = 0

    def populate_tree(
        self, notes: list[api.TreeNote], parent: Tree | TreeNode, marked_notes: Set[int]
    ) -> None:
        """Recursively populate the tree with notes."""
        for note in notes:
            # Create label with visual indicator if note is marked
            label = (
                f"[red]*[/red] {note.title}" if note.id in marked_notes else note.title
            )

            # Determine if this note should be added as a leaf or branch
            has_children = bool(note.children)

            if isinstance(parent, Tree):
                # Root level nodes
                if has_children:
                    node = parent.root.add(label, data=note)
                else:
                    node = parent.root.add_leaf(label, data=note)
            else:
                # Non-root nodes
                if has_children:
                    node = parent.add(label, data=note)
                else:
                    node = parent.add_leaf(label, data=note)

            # Recursively add children if they exist
            if has_children:
                for child in note.children:
                    self.populate_tree([child], node, marked_notes)

    def filter_notes(self, notes: List[api.TreeNote], query: str) -> List[api.TreeNote]:
        """Filter notes based on presence of all query characters."""
        if not query:
            return notes

        filtered = []
        query_chars = set(query.lower())

        for note in notes:
            current_note = api.TreeNote(
                id=note.id, title=note.title, content=note.content, children=[]
            )

            title_chars = set(note.title.lower())
            title_matches = all(char in title_chars for char in query_chars)

            filtered_children = (
                self.filter_notes(note.children, query) if note.children else []
            )

            if title_matches or filtered_children:
                current_note.children = filtered_children
                filtered.append(current_note)
        return filtered

    def filter_notes_by_ids(
        self, notes: List[api.TreeNote], matching_ids: set[int]
    ) -> List[api.TreeNote]:
        """Filter notes tree to only include paths to matching IDs."""
        filtered = []

        for note in notes:
            current_note = api.TreeNote(
                id=note.id, title=note.title, content=note.content, children=[]
            )

            filtered_children = (
                self.filter_notes_by_ids(note.children, matching_ids)
                if note.children
                else []
            )

            if note.id in matching_ids or filtered_children:
                current_note.children = filtered_children
                filtered.append(current_note)

        return filtered

    def get_expanded_nodes(self, node: TreeNode) -> set[str]:
        """Get the titles of all expanded nodes in the tree."""
        expanded = set()
        if node.is_expanded:
            expanded.add(str(node.label))
            for child in node.children:
                expanded.update(self.get_expanded_nodes(child))
        return expanded

    def restore_expanded_nodes(self, node: TreeNode, expanded_nodes: set[str]) -> None:
        """Restore the expanded state of nodes."""
        if str(node.label) in expanded_nodes:
            node.expand()
        for child in node.children:
            self.restore_expanded_nodes(child, expanded_nodes)

    def get_node_level(self, node: TreeNode) -> int:
        """Get the level of a node in the tree (root is 0)."""
        level = 0
        current = node
        while current.parent is not None:
            level += 1
            current = current.parent
        return level

    def fold_to_level(self, node: TreeNode, target_level: int) -> None:
        """Fold/unfold nodes to show up to target_level."""
        current_level = self.get_node_level(node)

        if current_level <= target_level:
            node.expand()
            for child in node.children:
                self.fold_to_level(child, target_level)
        else:
            node.collapse()

    def get_max_depth(self, node: TreeNode) -> int:
        """Get the maximum depth of the tree."""
        if not node.children:
            return self.get_node_level(node)
        return max(self.get_max_depth(child) for child in node.children)


class NoteContentManager:
    """Handles note content operations"""

    def __init__(self, notes_api: api.NoteAPI):
        self.notes_api = notes_api

    async def edit_note_with_editor(
        self, note: api.TreeNote, editor_cmd: str, suspend: bool = True
    ) -> str:
        """Edit the note with specified editor command."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tmp:
            tmp.write(note.content or "")
            tmp_path = Path(tmp.name)

        try:
            if suspend:
                # Use context manager for suspension if provided
                if hasattr(self, "suspend_context"):
                    with self.suspend_context():  # pyright: ignore
                        _result = subprocess.run(
                            [editor_cmd, str(tmp_path)], check=True
                        )
                else:
                    _result = subprocess.run([editor_cmd, str(tmp_path)], check=True)
            else:
                process = await asyncio.create_subprocess_exec(
                    editor_cmd,
                    str(tmp_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await process.wait()

            with open(tmp_path) as f:
                new_content = f.read()

            return new_content

        finally:
            tmp_path.unlink()

    def create_note(self, parent_id: Optional[int] = None) -> dict:
        """Create a new note."""
        title = datetime.now().strftime("New Note %Y-%m-%d %H:%M:%S")
        new_note = self.notes_api.create_note(title=title, content="")

        if parent_id is not None:
            self.notes_api.attach_note_to_parent(new_note["id"], parent_id)

        return new_note


class ExternalIntegrationManager:
    """Handles external connections and integrations"""

    def __init__(self, base_url: str, socket_path: str):
        self.notes_api = api.NoteAPI(base_url)
        self.socket_path = socket_path

    def connect_to_gui(self, note_id: int) -> None:
        """Connect to GUI preview via Unix Domain Socket."""
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.connect(self.socket_path)
                message = json.dumps({"command": "set_note", "note_id": note_id})
                sock.sendall(message.encode())
        except (FileNotFoundError, ConnectionRefusedError) as e:
            raise ConnectionError(f"GUI preview connection failed: {str(e)}")

    def refresh_gui(self) -> None:
        """Send refresh signal to GUI preview."""
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.connect(self.socket_path)
                message = json.dumps({"command": "refresh"})
                sock.sendall(message.encode())
        except (FileNotFoundError, ConnectionRefusedError) as e:
            raise ConnectionError(f"GUI preview connection failed: {str(e)}")


class NoteStateManager:
    """Manages application state"""

    def __init__(self):
        self.marked_notes: set[int] = set()
        self.last_filter: str = ""
        self.last_search: str = ""
        self.dialog_mode: str = "filter"
        self.follow_mode: bool = True
        self.auto_sync: bool = False
        self.flat_view: bool = False
        self.current_fold_level: int = 0


def filter_notes_by_query(notes: List[api.TreeNote], query: str) -> List[api.TreeNote]:
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
            filter_notes_by_query(note.children, query) if note.children else []
        )

        # Include note if it matches or has matching children
        if title_matches or filtered_children:
            current_note.children = filtered_children
            filtered.append(current_note)
    return filtered


def filter_notes_by_ids(
    notes: List[api.TreeNote], matching_ids: set[int]
) -> List[api.TreeNote]:
    """Filter notes tree to only include paths to matching IDs."""
    filtered = []

    for note in notes:
        current_note = api.TreeNote(
            id=note.id, title=note.title, content=note.content, children=[]
        )

        filtered_children = (
            filter_notes_by_ids(note.children, matching_ids) if note.children else []
        )

        if note.id in matching_ids or filtered_children:
            current_note.children = filtered_children
            filtered.append(current_note)

    return filtered


def flatten_filtered_notes(notes: List[api.TreeNote]) -> List[api.TreeNote]:
    """Convert hierarchical filtered notes into a flat list."""
    flattened = []

    def collect_matches(note: api.TreeNote):
        if not note.children:
            flattened.append(
                api.TreeNote(
                    id=note.id, title=note.title, content=note.content, children=[]
                )
            )
        else:
            for child in note.children:
                collect_matches(child)

    for note in notes:
        collect_matches(note)

    return flattened
