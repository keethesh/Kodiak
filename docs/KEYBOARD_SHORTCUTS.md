# Kodiak TUI Keyboard Shortcuts Reference

## Global Shortcuts (Available Everywhere)

| Key | Action | Description |
|-----|--------|-------------|
| `q` | Quit | Exit the application |
| `h` | Home | Return to home screen |
| `?` | Help | Show help overlay |
| `Ctrl+C` | Force Quit | Emergency exit |

## Home Screen

| Key | Action | Description |
|-----|--------|-------------|
| `n` | New Project | Create new project |
| `d` | Delete | Delete selected project |
| `r` | Refresh | Refresh project list |
| `Enter` | Open | Open selected project |
| `↑/↓` | Navigate | Move selection |

## New Scan Screen

| Key | Action | Description |
|-----|--------|-------------|
| `Tab` | Next Field | Move to next input |
| `Shift+Tab` | Previous Field | Move to previous input |
| `Enter` | Submit | Create scan |
| `Escape` | Cancel | Go back |

## Mission Control

| Key | Action | Description |
|-----|--------|-------------|
| `Tab` | Cycle Panels | Switch focus between panels |
| `g` | Graph View | Open full graph view |
| `f` | Findings | Open findings screen |
| `c` | Agent Chat | Open agent chat |
| `p` | Pause/Resume | Control scan state |
| `↑/↓` | Navigate | Navigate in active panel |
| `Enter` | Select | Select item |

## Agent Chat

| Key | Action | Description |
|-----|--------|-------------|
| `←/→` | Switch Agent | Change active agent |
| `Enter` | Send Message | Send message to agent |
| `↑/↓` | History | Navigate message history |
| `Ctrl+L` | Clear Chat | Clear chat history |
| `Escape` | Back | Return to mission control |

## Graph View

| Key | Action | Description |
|-----|--------|-------------|
| `↑/↓` | Navigate | Move through nodes |
| `←/→` | Expand/Collapse | Toggle tree nodes |
| `Enter` | Details | View finding details |
| `/` | Search | Search nodes |
| `Escape` | Clear Search | Clear search filter |
| `f` | Filter | Filter by type/severity |

## Findings Screen

| Key | Action | Description |
|-----|--------|-------------|
| `↑/↓` | Navigate | Move through findings |
| `Enter` | Details | View finding details |
| `e` | Export | Export findings |
| `s` | Sort | Change sort order |
| `f` | Filter | Filter findings |
| `r` | Refresh | Refresh list |

## Finding Detail

| Key | Action | Description |
|-----|--------|-------------|
| `c` | Copy PoC | Copy proof-of-concept |
| `t` | Re-test | Re-test vulnerability |
| `e` | Export | Export finding |
| `↑/↓` | Scroll | Scroll content |
| `Escape` | Back | Return to findings |

## Status Icons Reference

### Agent Status
- 🟢 Active (working)
- 🟡 Idle (waiting)
- 🔴 Error (failed)
- ⏸️ Paused
- ⚫ Stopped

### Finding Severity
- 🔴 Critical
- 🟠 High  
- 🟡 Medium
- 🔵 Low
- ⚪ Info

### Node Types
- 🌐 Domain
- 🖥️ Host
- 🔌 Port
- 📁 Directory
- 📄 File
- 🔧 Service
- 🔍 Vulnerability

## Quick Tips

1. **Press `?` anytime** for context-sensitive help
2. **Use `Tab`** to cycle through panels and fields
3. **Use `h`** to quickly return home from anywhere
4. **Use `Escape`** to go back or cancel operations
5. **Arrow keys** work for navigation in all views
6. **`Enter`** confirms selections and actions

## Getting Started

1. Run `kodiak init` to initialize database
2. Run `kodiak config` to configure LLM
3. Run `kodiak` to start the TUI
4. Press `n` to create your first project
5. Press `?` anytime for help

For detailed usage instructions, see `docs/TUI_GUIDE.md`.