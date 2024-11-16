import typer
from tui import NotesApp
import subprocess
import os
from pathlib import Path


def launch_gui_preview(base_url: str, socket_path: str, dark_mode: bool = False):
    """
    Launch the GUI preview in the background, discarding output.
    """
    # Construct the command
    cmd = [
        "ds-preview",
        "--socket-path",
        socket_path,
        "--api-scheme",
        base_url.split("://")[0],
        "--api-host",
        base_url.split("://")[1].split(":")[0],
        "--api-port",
        base_url.split(":")[-1],
    ]

    if dark_mode:
        cmd.append("--dark")

    # Launch the process with output discarded
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # This detaches the process
    )

    return process.pid


def main(
    api_scheme: str = typer.Option(
        "http", help="The API URL scheme (e.g., http or https)."
    ),
    api_host: str = typer.Option("localhost", help="The API hostname to connect to."),
    api_port: int = typer.Option(37240, help="The API port number to connect to."),
    socket_path: str = typer.Option(
        "/tmp/markdown_preview.sock",
        help="The file system path for the GUI preview socket connection.",
    ),
    with_preview: bool = typer.Option(
        False, help="Whether to launch the GUI preview alongside the TUI."
    ),
    dark_preview: bool = typer.Option(
        False, help="If set, starts the GUI preview in dark mode."
    ),
):
    """
    Launch the notes application.

    This command initiates the notes application with options for
    previewing notes in a GUI, setting the API connection parameters,
    and choosing a display mode.
    """
    base_url = f"{api_scheme}://{api_host}:{api_port}"

    if with_preview:
        # Launch the GUI preview first
        pid = launch_gui_preview(base_url, socket_path, dark_preview)
        print(f"Started GUI preview with PID {pid}")

    app = NotesApp(base_url=base_url, socket_path=socket_path)
    app.run()


if __name__ == "__main__":
    typer.run(main)
