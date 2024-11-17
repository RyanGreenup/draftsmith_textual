# Draftsmith TUI

A terminal user interface for Draftsmith PyQt markdown preview support.

## Installation


Instllation is via `clone` and `venv` (`pipx` is not supported) [^1]

[^1]: I cannot figure out how to include the css with `pipx` so this is not working yet, if the reader knows how to do this please let me know in an issue or a PR.

```bash
cd ~/.local/share/opt/
git clone --recurse-submodules https://github.com/RyanGreenup/draftsmith_textual
cd draftsmith_textual
poetry export -f requirements.txt -o requirements.txt
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Then create a script in your `$PATH` to run the TUI:

```bash
nvim ~/.local/bin/ds-tui
```

```bash
#!/bin/sh

$HOME/.local/share/opt/draftsmith_textual/main.py $@
```

```
chmod +x ~/.local/bin/ds-tui
ds-tui --with-preview
```


## Screenshot

![Screenshot](./assets/screenshot.png)

## Usage

Start the markdown preview window:

```bash
ds-preview --socket-path /tmp/markdown_preview.sock
```

In another terminal, start the TUI:

```bash
ds-tui
```

### Key Bindings

- Press `g` on a note to update it in the preview window
- Use arrow keys to navigate
- Type to filter notes

### Options

Both commands support various options:

```bash
EDITOR=nvim GUI_EDITOR=neovide ds-tui --help
ds-preview --help
```

Common options include:
- `--api-scheme`: HTTP scheme (default: http)
- `--api-host`: API host (default: localhost)
- `--api-port`: API port (default: 37240)
- `--socket-path`: Socket path for preview communication


The `GUI_EDITOR` environment variable can be used to specify the GUI editor to use when opening a note with <kbd>E</kbd>.

## Development

```bash
git clone https://github.com/RyanGreenup/
cd draftsmith_css
poetry run python markdown_preview.py --socket-path /tmp/md.sock 2>/dev/null & disown
poetry run python main.py --socket-path /tmp/md.sock
```

