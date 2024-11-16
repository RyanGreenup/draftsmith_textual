# Draftsmith TUI

A terminal user interface for Draftsmith with markdown preview support.

## Installation

Install using pipx:

```bash
pipx install git+https://github.com/RyanGreenup/draftsmith_css
```

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
ds-tui --help
ds-preview --help
```

Common options include:
- `--api-scheme`: HTTP scheme (default: http)
- `--api-host`: API host (default: localhost)
- `--api-port`: API port (default: 37240)
- `--socket-path`: Socket path for preview communication


## Development

```
git clone https://github.com/RyanGreenup/
cd draftsmith_css

```

