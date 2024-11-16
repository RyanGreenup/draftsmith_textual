#!/usr/bin/env python3
import sys
import base64
import typer
import socket
import threading
import os
import json
from pathlib import Path
from typing import Optional

# Import QWebEngineUrlScheme before any other WebEngine modules
from PySide6.QtWebEngineCore import QWebEngineUrlScheme, QWebEngineUrlRequestJob

# Define and register the custom URL scheme for assets
asset_scheme = QWebEngineUrlScheme(b"asset")
asset_scheme.setSyntax(QWebEngineUrlScheme.Syntax.Path)
asset_scheme.setFlags(
    QWebEngineUrlScheme.LocalAccessAllowed | QWebEngineUrlScheme.CorsEnabled
)
QWebEngineUrlScheme.registerScheme(asset_scheme)

# Now import the rest of the required modules
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QComboBox,
    QVBoxLayout,
    QWidget,
    QToolBar,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl, QByteArray, QBuffer, QIODevice, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QAction, QPalette
from PySide6.QtWebEngineCore import (
    QWebEngineSettings,
    QWebEngineUrlSchemeHandler,
    QWebEngineProfile,
    QWebEnginePage,
)
from api import NoteAPI
import re
import os


class NotePage(QWebEnginePage):
    def __init__(self, profile, parent, app):
        super().__init__(profile, parent)
        self.app = app

    def acceptNavigationRequest(self, url, _type, isMainFrame):
        url_str = url.toString()
        if url_str.startswith("file:///note/"):
            try:
                # Extract note ID from path
                note_id = int(url.path().split("/")[-1])
                # Update the combo box
                self.app._update_note_id(note_id)
                return False  # Prevent actual navigation
            except (ValueError, IndexError):
                print(f"Invalid note link: {url_str}")
        return True  # Allow all other navigation



class AssetUrlSchemeHandler(QWebEngineUrlSchemeHandler):
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url

    def requestStarted(self, job):
        url = job.requestUrl()
        print(f"AssetUrlSchemeHandler.requestStarted called with URL: {url.toString()}")

        try:
            # Extract asset ID, handling potential URL encoding
            asset_id = url.path()[1:]  # Remove the leading '/'
            if not asset_id:
                print("Error: Empty asset ID")
                job.fail(QWebEngineUrlRequestJob.RequestFailed)
                return

            # Create the redirect URL to the API endpoint
            api_url = f"{self.base_url}/assets/download/{asset_id}"
            print(f"Redirecting to API URL: {api_url}")
            
            # Perform the redirect
            job.redirect(QUrl(api_url))

        except Exception as e:
            print(f"Error handling asset request: {e}")
            job.fail(QWebEngineUrlRequestJob.RequestFailed)


class MarkdownPreviewApp(QMainWindow):
    update_note_id = Signal(int)

    def __init__(
        self,
        base_url: str,
        initial_note_id: Optional[int] = None,
        socket_path: Optional[str] = None,
    ):
        super().__init__()
        # Change to this location so css can be loaded
        os.chdir(os.path.dirname(os.path.abspath(__file__)))

        self.note_api = NoteAPI(base_url)
        self.dark_mode = False
        self.setWindowTitle("Markdown Preview")
        self.setGeometry(100, 100, 800, 600)

        # Create toolbar
        toolbar = QToolBar()
        self.addToolBar(toolbar)

        # Add dark mode toggle action
        self.dark_mode_action = QAction("Dark Mode", self)
        self.dark_mode_action.setShortcut(QKeySequence("Ctrl+D"))
        self.dark_mode_action.setCheckable(True)
        self.dark_mode_action.triggered.connect(self.toggle_dark_mode)
        toolbar.addAction(self.dark_mode_action)

        # Add view source action
        self.view_source_action = QAction("View Source", self)
        self.view_source_action.setShortcut(QKeySequence("Ctrl+U"))
        self.view_source_action.triggered.connect(self.view_source)
        toolbar.addAction(self.view_source_action)

        # Create a combo box for note IDs
        self.combo_box = QComboBox()
        self.combo_box.currentIndexChanged.connect(self.on_combo_box_changed)

        # Set up the profile and register the scheme handler
        self.profile = QWebEngineProfile.defaultProfile()
        self.scheme_handler = AssetUrlSchemeHandler(self.note_api.base_url)
        self.profile.installUrlSchemeHandler(b"asset", self.scheme_handler)

        # Create the web view and set its page to use the profile
        self.web_view = QWebEngineView()
        self.web_page = NotePage(self.profile, self.web_view, self)
        self.web_view.setPage(self.web_page)

        # Configure WebEngine settings
        settings = self.profile.settings()
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.AllowRunningInsecureContent, True)
        settings.setAttribute(QWebEngineSettings.PlaybackRequiresUserGesture, False)
        settings.setAttribute(QWebEngineSettings.PluginsEnabled, True)
        settings.setAttribute(QWebEngineSettings.ShowScrollBars, True)

        # Layout setup
        layout = QVBoxLayout()
        layout.addWidget(self.combo_box)
        layout.addWidget(self.web_view)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Fetch and populate note IDs
        self.populate_combo_box()

        # Set initial note if provided
        if initial_note_id is not None:
            index = self.combo_box.findData(initial_note_id)
            if index >= 0:
                self.combo_box.setCurrentIndex(index)

        # Connect the update signal
        self.update_note_id.connect(self._update_note_id)

        # Set up IPC if socket path is provided
        if socket_path:
            self.setup_ipc_server(socket_path)

    def populate_combo_box(self):
        try:
            notes = self.note_api.get_all_notes_without_content()
            for note in notes:
                self.combo_box.addItem(str(note.id), note.id)
        except Exception as e:
            print(f"Error fetching notes: {e}")

    def on_combo_box_changed(self, index):
        if index >= 0:
            note_id = self.combo_box.itemData(index)
            try:
                html_content = self.note_api.get_rendered_note(
                    note_id=note_id, format="html"
                )
                # Inject KaTeX and markdown.css resources into the HTML content
                full_html_content = self.inject_resources(html_content)
                self.web_view.setHtml(full_html_content, QUrl("file:///"))
            except Exception as e:
                print(f"Error rendering markdown: {e}")

    def toggle_dark_mode(self):
        """Toggle dark mode and refresh the current note."""
        self.dark_mode = self.dark_mode_action.isChecked()

        # Update application palette
        if self.dark_mode:
            QApplication.instance().setPalette(get_dark_palette())
        else:
            QApplication.instance().setPalette(QApplication.style().standardPalette())

        # Refresh current note
        current_index = self.combo_box.currentIndex()
        if current_index >= 0:
            self.on_combo_box_changed(current_index)

    def setup_ipc_server(self, socket_path: str):
        """Set up the IPC server using Unix Domain Socket."""
        self.socket_path = socket_path

        # Remove existing socket file if it exists
        if os.path.exists(socket_path):
            os.unlink(socket_path)

        # Create the socket server
        self.ipc_server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.ipc_server.bind(socket_path)
        self.ipc_server.listen(1)

        # Start listening thread
        self.ipc_thread = threading.Thread(
            target=self._handle_ipc_connections, daemon=True
        )
        self.ipc_thread.start()

    def _handle_ipc_connections(self):
        """Handle incoming IPC connections."""
        while True:
            try:
                conn, _ = self.ipc_server.accept()
                with conn:
                    while True:
                        data = conn.recv(1024)
                        if not data:
                            break

                        try:
                            message = json.loads(data.decode())
                            if message.get("command") == "set_note":
                                note_id = message.get("note_id")
                                if note_id is not None:
                                    # Schedule the combo box update in the main thread
                                    self.update_note_id.emit(note_id)
                        except json.JSONDecodeError:
                            print("Error: Invalid JSON message received")
                        except Exception as e:
                            print(f"Error handling IPC message: {e}")
            except Exception as e:
                print(f"IPC connection error: {e}")
                if not os.path.exists(self.socket_path):
                    # Socket file was deleted, exit the thread
                    break

    def _update_note_id(self, note_id: int):
        """Update the combo box to show the specified note ID."""
        index = self.combo_box.findData(note_id)
        if index >= 0:
            self.combo_box.setCurrentIndex(index)

    def cleanup_ipc(self):
        """Clean up IPC resources."""
        if hasattr(self, "ipc_server"):
            self.ipc_server.close()
        if hasattr(self, "socket_path") and os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

    def closeEvent(self, event):
        """Handle application closure."""
        self.cleanup_ipc()
        super().closeEvent(event)

    def view_source(self):
        """Show the HTML source of the current page in a new window."""
        self.web_view.page().toHtml(self._show_source_window)

    def _show_source_window(self, html_content: str):
        """Create a new window to display the HTML source."""
        source_window = QMainWindow(self)
        source_window.setWindowTitle("Page Source")
        source_window.setGeometry(150, 150, 800, 600)
        
        source_view = QWebEngineView(source_window)
        # Display the HTML content as plain text
        escaped_html = html_content.replace("<", "&lt;").replace(">", "&gt;")
        source_view.setHtml(f"<pre style='white-space: pre-wrap; word-wrap: break-word;'>{escaped_html}</pre>")
        
        source_window.setCentralWidget(source_view)
        source_window.show()

    def inject_resources(self, html_content: str) -> str:
        try:
            base_path = os.path.abspath("draftsmith_css/static")

            # Read all CSS files from the css directory
            css_dir = os.path.join(base_path, "css")
            all_css = ""
            for css_file in sorted(os.listdir(css_dir)):
                if css_file.endswith(".css"):
                    if css_file == "dark.css" and not self.dark_mode:
                        continue
                    if css_file == "light.css" and self.dark_mode:
                        continue
                    if css_file != "katex.min.css":
                        with open(
                            os.path.join(css_dir, css_file), "r", encoding="utf-8"
                        ) as f:
                            all_css += f.read() + "\n"

            # Read KaTeX resources
            with open(
                os.path.join(base_path, "katex/dist/katex.min.js"),
                "r",
                encoding="utf-8",
            ) as f:
                katex_js = f.read()
            with open(
                os.path.join(base_path, "katex/dist/contrib/auto-render.min.js"),
                "r",
                encoding="utf-8",
            ) as f:
                auto_render_js = f.read()

            # Read and process KaTeX CSS and fonts
            with open(
                os.path.join(base_path, "katex/dist/katex.min.css"),
                "r",
                encoding="utf-8",
            ) as f:
                katex_css = f.read()

            # Create a mapping of font filenames to their base64 data
            fonts_path = os.path.join(base_path, "katex/dist/fonts")
            font_data_map = {}
            for font_file in os.listdir(fonts_path):
                if font_file.endswith(".woff2"):
                    with open(os.path.join(fonts_path, font_file), "rb") as f:
                        font_data_map[font_file] = base64.b64encode(f.read()).decode(
                            "utf-8"
                        )

            # Replace font URLs in katex.css with base64-encoded data URLs
            for font_file, font_data in font_data_map.items():
                # Replace the font file references in the CSS
                font_url = f"url(fonts/{font_file})"
                data_url = f"url(data:font/woff2;base64,{font_data})"
                katex_css = katex_css.replace(font_url, data_url)

            full_html_content = f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Markdown Preview</title>
                <style>
                    {katex_css}
                </style>
                <style>
                    {all_css}
                </style>
                <style>
                    /* Override code block backgrounds */
                    .markdown code {{
                        background: transparent !important;
                    }}
                    :root {{
                        --bg-color: {self.dark_mode and '#1e1e1e' or '#ffffff'};
                        --text-color: {self.dark_mode and '#d4d4d4' or '#000000'};
                    }}
                    html, body {{
                        background-color: var(--bg-color) !important;
                        color: var(--text-color);
                        margin: 0;
                        padding: 0;
                        min-height: 100vh;
                    }}
                    .markdown {{
                        background-color: {self.dark_mode and '#2d2d2d' or '#ffffff'};
                        color: var(--text-color);
                        padding: 20px;
                        min-height: calc(100vh - 40px);
                        margin: 20px;
                        border-radius: 8px;
                        box-shadow: 0 2px 4px {self.dark_mode and 'rgba(0,0,0,0.5)' or 'rgba(0,0,0,0.1)'};
                    }}
                    /* Dark mode heading styles */
                    {self.dark_mode and '''
                    .markdown h1,
                    .markdown h2, 
                    .markdown h3,
                    .markdown h4,
                    .markdown h5,
                    .markdown h6 {
                        color: #d4d4d4;
                        border-bottom-color: #444;
                    }
                    ''' or ''}
                </style>
            </head>
            <body>
                <div class="markdown">
                    {html_content}
                </div>
                <script>
                    {katex_js}
                </script>
                <script>
                    {auto_render_js}
                </script>
                <script>
                    document.addEventListener("DOMContentLoaded", function() {{
                        renderMathInElement(document.body, {{
                            delimiters: [
                                {{left: "$$", right: "$$", display: true}},
                                {{left: "$", right: "$", display: false}},
                                {{left: "\\\\(", right: "\\\\)", display: false}},
                                {{left: "\\\\[", right: "\\\\]", display: true}}
                            ],
                            ignoredTags: ["script", "noscript", "style", "textarea", "pre"]
                        }});
                    }});
                </script>
            </body>
            </html>
            """
        except Exception as e:
            print(f"Error loading resources: {e}")
            return f"<html><body><pre>Error loading resources: {e}</pre><hr>{html_content}</body></html>"
        # Replace note links to use the file scheme
        full_html_content = re.sub(
            r'href="/note/(\d+)"',
            r'href="file:///note/\1"',
            full_html_content
        )
        # Replace asset URLs in the HTML content to use the custom scheme
        full_html_content = full_html_content.replace('src="/m/', 'src="asset:///')
        return full_html_content


def get_dark_palette():
    """
    Return a QPalette with a dark color scheme.
    """
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
    return dark_palette


def launch_preview(
    base_url: str = "http://localhost:37240",
    initial_note_id: Optional[int] = None,
    dark_mode: bool = False,
    socket_path: Optional[str] = None,
):
    """Launch the markdown preview application."""
    app = QApplication(sys.argv)
    window = MarkdownPreviewApp(
        base_url=base_url, initial_note_id=initial_note_id, socket_path=socket_path
    )
    if dark_mode:
        window.dark_mode_action.setChecked(True)
        window.toggle_dark_mode()
    window.show()
    return app.exec()


app = typer.Typer()


@app.command()
def preview(
    api_scheme: str = typer.Option("http", help="API scheme (http/https)"),
    api_host: str = typer.Option("localhost", help="API host"),
    api_port: int = typer.Option(37240, help="API port"),
    id: Optional[int] = typer.Option(None, help="Open specific note by ID"),
    dark: bool = typer.Option(False, help="Start in dark mode"),
    socket_path: Optional[str] = typer.Option(
        None, help="Unix Domain Socket path for IPC"
    ),
):
    """Launch the markdown preview application with the specified API settings."""
    base_url = f"{api_scheme}://{api_host}:{api_port}"
    sys.exit(
        launch_preview(
            base_url, initial_note_id=id, dark_mode=dark, socket_path=socket_path
        )
    )


if __name__ == "__main__":
    app()
