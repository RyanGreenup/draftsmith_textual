from dataclasses import dataclass
from textual.widgets import Tree, Static
from textual.containers import Container
from typing import Optional, List, TYPE_CHECKING
import api
from note_managers import NoteTreeManager

if TYPE_CHECKING:
    from tui import NotesApp, NoteViewer


@dataclass
class TabContent:
    """Represents the content of a single tab"""

    tree: Tree
    viewer: "NoteViewer"  # Forward reference
    last_filter: str = ""
    last_search: str = ""
    dialog_mode: str = "filter"


class TabManager:
    """Manages all tab-related operations"""

    def __init__(self, app: "NotesApp", notes_api: api.NoteAPI):  # Forward reference
        self.app = app
        self.notes_api = notes_api
        self.tabs: List[TabContent] = []
        self.current_tab_index: int = 0
        self.tree_manager = NoteTreeManager(notes_api)

    @property
    def current_tab(self) -> Optional[TabContent]:
        """Get the current tab content"""
        return self.tabs[self.current_tab_index] if self.tabs else None

    def create_new_tab(self) -> None:
        """Create a new tab with its own tree and viewer"""
        from tui import NoteViewer  # Import here to avoid circular dependency

        try:
            old_tree = self.app.query_one(f"#notes-tree-{len(self.tabs)-1}", Tree)
            expanded_nodes = self.tree_manager.get_expanded_nodes(old_tree.root)
        except Exception:
            expanded_nodes = set()
        tree = Tree("Notes", id=f"notes-tree-{len(self.tabs)}")
        viewer = NoteViewer(id=f"note-viewer-{len(self.tabs)}")
        new_tab = TabContent(tree=tree, viewer=viewer)
        self.tabs.append(new_tab)
        self.switch_to_tab(len(self.tabs) - 1)
        self.refresh_current_tab()
        # Set initial fold level to 1 for the new tab
        tree = self.app.query_one(f"#notes-tree-{len(self.tabs)-1}", Tree)
        self.app._fold_to_level(tree.root, 0)
        self.app._restore_expanded_nodes(tree.root, expanded_nodes)

    def close_current_tab(self) -> None:
        """Close the current tab if there's more than one"""
        if len(self.tabs) > 1:
            self.tabs.pop(self.current_tab_index)
            self.current_tab_index = max(0, self.current_tab_index - 1)
            self.switch_to_tab(self.current_tab_index)

    def switch_to_tab(self, index: int) -> None:
        """Switch to the specified tab"""
        if 0 <= index < len(self.tabs):
            tab_content = self.app.query_one("#tab-content", Container)
            tab_content.remove_children()

            self.current_tab_index = index
            current_tab = self.current_tab
            if current_tab:
                tab_content.mount(current_tab.tree)
                tab_content.mount(current_tab.viewer)
                self.refresh_current_tab()

            self.update_tab_bar()

    def update_tab_bar(self) -> None:
        """Update the tab bar display"""
        tab_bar = self.app.query_one("#tab-bar", Static)
        tab_text = " ".join(
            f"[{'bold white' if i == self.current_tab_index else 'dim'}]Tab {i + 1}[/]"
            for i in range(len(self.tabs))
        )
        tab_bar.update(tab_text)

    def refresh_current_tab(self) -> None:
        """Refresh the current tab's content"""
        current_tab = self.current_tab
        if not current_tab:
            return

        tree = current_tab.tree
        expanded_nodes = self.tree_manager.get_expanded_nodes(tree.root)
        tree.clear()

        try:
            notes = self.notes_api.get_notes_tree()
            self.tree_manager.populate_tree(notes, tree, self.app.marked_for_move)
            self.tree_manager.restore_expanded_nodes(tree.root, expanded_nodes)
        except Exception as e:
            tree.root.add_leaf(f"Error loading notes: {str(e)}")

    def next_tab(self) -> None:
        """Switch to the next tab"""
        if self.tabs:
            next_index = (self.current_tab_index + 1) % len(self.tabs)
            self.switch_to_tab(next_index)

    def previous_tab(self) -> None:
        """Switch to the previous tab"""
        if self.tabs:
            prev_index = (self.current_tab_index - 1) % len(self.tabs)
            self.switch_to_tab(prev_index)

    def handle_node_highlight(
        self, node: Tree.NodeHighlighted, follow_mode: bool, auto_sync: bool
    ) -> None:
        """Handle node highlight event"""
        if not follow_mode:
            return

        current_tab = self.current_tab
        if not current_tab:
            return

        note = node.node.data
        if note and isinstance(note, api.TreeNote):
            current_tab.viewer.display_note(note.content)
            if auto_sync:
                self.app.connect_to_gui()
