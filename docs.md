# Notes TUI Documentation

## Overview
The Notes TUI is a terminal-based user interface for managing and viewing notes. It provides a hierarchical tree view of notes, content preview, and markdown rendering capabilities.

## Features

### Note Navigation
- **Tree View**: Notes are displayed in a hierarchical tree structure
- **Scrollable Content**: Note content can be scrolled within the preview pane
- **Tab Interface**: Switch between different views and functions using tabs

### Content Display
- **Markdown Support**: Notes are rendered in markdown format
- **Preview Mode**: View formatted content in real-time
- **Asset Handling**: Support for embedded assets and attachments

### Search and Filtering
- **Note Filtering**: Filter notes by various criteria
- **Quick Navigation**: Jump to specific notes using IDs
- **Tree Expansion**: Expand/collapse note hierarchies

## Keyboard Shortcuts

### Navigation
- `Tab`: Switch between tree view and content pane
- `↑/↓`: Navigate through notes
- `Enter`: Select a note
- `Space`: Expand/collapse tree nodes

### View Controls
- `Ctrl+Q`: Quit application
- `Ctrl+R`: Refresh content
- `Esc`: Close popups/modals

## Integration
The TUI interfaces with a backend API for:
- Note content retrieval
- Asset management
- Tag operations
- Task management

## Technical Details
- Built using the Textual TUI framework
- Supports dark/light mode
- Handles external asset URLs
- Manages note hierarchies and relationships

## Requirements
- Python 3.x
- Textual library
- Network connection to backend API

## Getting Started
1. Ensure backend API is running
2. Launch the TUI with appropriate base URL and socket path
3. Navigate the tree view to select notes
4. Use keyboard shortcuts for efficient navigation

## Tips
- Use tree expansion to manage large note hierarchies
- Take advantage of the scrollable preview for long content
- Utilize keyboard shortcuts for faster navigation
