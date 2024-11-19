from textual.app import ComposeResult
from textual.widgets.markdown import Markdown
from typing import Optional
from textual.widgets import Static
import re


class NoteViewer(Static):
    """Widget to display note content"""

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        self.link_regex = re.compile(r"\[\[(\d+)\]\]")
        yield Markdown()

    def display_note(self, content: Optional[str]) -> None:
        """Update the display with note content"""
        markdown = self.query_one(Markdown)
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
