import typer
from tui import NotesApp
import subprocess
import os
from pathlib import Path

def launch_gui_preview(base_url: str, socket_path: str, dark_mode: bool = False):
    """
    Launch the GUI preview in the background, redirecting output to a log file.
    """
    # Create log directory if it doesn't exist
    log_dir = Path.home() / ".local" / "share" / "draftsmith" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Open log files for stdout and stderr
    stdout_log = open(log_dir / "markdown_preview.log", "a")
    stderr_log = open(log_dir / "markdown_preview.error.log", "a")
    
    # Construct the command
    cmd = [
        "python", 
        "markdown_preview.py",
        "--socket-path", 
        socket_path,
        "--api-scheme",
        base_url.split("://")[0],
        "--api-host",
        base_url.split("://")[1].split(":")[0],
        "--api-port",
        base_url.split(":")[-1]
    ]
    
    if dark_mode:
        cmd.append("--dark")
    
    # Launch the process
    process = subprocess.Popen(
        cmd,
        stdout=stdout_log,
        stderr=stderr_log,
        start_new_session=True  # This detaches the process
    )
    
    return process.pid

def main(
    api_scheme: str = "http",
    api_host: str = "localhost", 
    api_port: int = 37240,
    tui: bool = True,
    socket_path: str = "/tmp/markdown_preview.sock",
    with_preview: bool = False,  # New parameter
    dark_preview: bool = False,  # New parameter for dark mode
):
    """
    Launch the notes application.
    
    Args:
        api_scheme: The API URL scheme (http/https)
        api_host: The API hostname
        api_port: The API port number
        tui: Whether to launch the TUI interface
        socket_path: Path for the GUI preview socket connection
        with_preview: Whether to launch the GUI preview alongside the TUI
        dark_preview: Start the preview in dark mode
    """
    base_url = f"{api_scheme}://{api_host}:{api_port}"
    
    if with_preview and tui:
        # Launch the GUI preview first
        pid = launch_gui_preview(base_url, socket_path, dark_preview)
        print(f"Started GUI preview with PID {pid}")
    
    if tui:
        app = NotesApp(base_url=base_url, socket_path=socket_path)
        app.run()
    else:
        print(f"Accessing API at {base_url}")


if __name__ == "__main__":
    typer.run(main)
