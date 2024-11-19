from textual.app import ComposeResult
from textual.widgets.markdown import Markdown
from typing import Optional
from textual.widgets import Static
from textual.containers import ScrollableContainer
import re

from api import NoteAPI


class NoteViewer(Static):
    """Widget to display note content"""

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        self.link_regex = re.compile(r"\[\[(\d+)\]\]")
        self.note_api = None
        yield ScrollableContainer(Markdown())

    def display_note(self, note_id: Optional[int], base_url: Optional[str]) -> None:
        """Update the display with note content"""
        markdown = self.query_one("ScrollableContainer Markdown")
        if base_url:
            if not self.note_api:
                self.note_api = NoteAPI(base_url)
        if not self.note_api:
            markdown.update("No API base_url provided")
            return
        if note_id:
            content = self.note_api.get_rendered_note(note_id, "md")
            markdown.update(content)
        else:
            markdown.update("No content")

    def display_content(self, content: Optional[str]) -> None:
        """Update the display with some content"""
        markdown = self.query_one("ScrollableContainer Markdown")
        if content:
            content = self.preprocess(content)
            markdown.update(content)
        else:
            markdown.update("No content")

    def preprocess(self, content: str) -> str:
        """Preprocess content before displaying"""

        # Define a replacement function that will be called for each match.
        def replacer(match):
            # Extract the numeric id from the matched group
            number = match.group(1)
            # Return the new string format
            return f"[{number}]({number})"

        # Use sub with the compiled pattern and the replacement function.
        result = self.link_regex.sub(replacer, content)
        return result
