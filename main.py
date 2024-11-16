import typer
from tui import NotesApp


def main(
    api_scheme: str = "http",
    api_host: str = "localhost", 
    api_port: int = 37240,
    tui: bool = True
):
    """
    Launch the notes application.
    
    Args:
        api_scheme: The API URL scheme (http/https)
        api_host: The API hostname
        api_port: The API port number
        tui: Whether to launch the TUI interface
    """
    base_url = f"{api_scheme}://{api_host}:{api_port}"
    
    if tui:
        app = NotesApp(base_url=base_url)
        app.run()
    else:
        print(f"Accessing API at {base_url}")


if __name__ == "__main__":
    typer.run(main)
