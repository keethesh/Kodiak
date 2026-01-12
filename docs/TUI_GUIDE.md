# Kodiak TUI User Guide

## Overview

Kodiak's Terminal User Interface (TUI) provides a modern, keyboard-driven experience for penetration testing workflows. Built with Textual, it offers real-time updates, intuitive navigation, and comprehensive functionality without requiring a web browser.

## Getting Started

### Launch the TUI

```bash
# Start the TUI application
kodiak

# Or explicitly launch TUI
kodiak tui

# Run with debug mode for troubleshooting
kodiak tui --debug
```

### First Time Setup

1. **Initialize Database**: Run `kodiak init` to set up the database schema
2. **Configure LLM**: Run `kodiak config` to set up your AI provider
3. **Launch TUI**: Run `kodiak` to start the interface

## Navigation Overview

The TUI consists of several main views:

- **Home**: Project management and selection
- **New Scan**: Create new security assessments
- **Mission Control**: Real-time monitoring dashboard
- **Agent Chat**: Direct communication with AI agents
- **Graph View**: Attack surface visualization
- **Findings**: Vulnerability reports and analysis
- **Finding Detail**: Detailed vulnerability information

## Global Keyboard Shortcuts

These shortcuts work from any view:

| Key | Action | Description |
|-----|--------|-------------|
| `q` | Quit | Exit the application |
| `h` | Home | Return to home screen |
| `?` | Help | Show help overlay with shortcuts |
| `Ctrl+C` | Force Quit | Emergency exit |

## View-Specific Navigation

### Home Screen

| Key | Action | Description |
|-----|--------|-------------|
| `n` | New Project | Create a new project |
| `d` | Delete | Delete selected project |
| `r` | Refresh | Refresh project list |
| `Enter` | Open | Open selected project |
| `↑/↓` | Navigate | Move selection up/down |

### New Scan Screen

| Key | Action | Description |
|-----|--------|-------------|
| `Tab` | Next Field | Move to next input field |
| `Shift+Tab` | Previous Field | Move to previous input field |
| `Enter` | Submit | Create the scan (when valid) |
| `Escape` | Cancel | Return to previous screen |
| `Ctrl+A` | Select All | Select all text in current field |

### Mission Control Screen

| Key | Action | Description |
|-----|--------|-------------|
| `Tab` | Cycle Panels | Switch between agents, graph, and activity |
| `g` | Graph View | Open full-screen graph view |
| `f` | Findings | Open findings screen |
| `c` | Agent Chat | Open agent chat screen |
| `p` | Pause/Resume | Pause or resume scan |
| `↑/↓` | Navigate | Navigate within active panel |
| `Enter` | Select | Select item in active panel |

### Agent Chat Screen

| Key | Action | Description |
|-----|--------|-------------|
| `←/→` | Switch Agent | Change active agent |
| `Enter` | Send Message | Send typed message to agent |
| `↑/↓` | Message History | Navigate through message history |
| `Ctrl+L` | Clear Chat | Clear chat history |
| `Escape` | Back | Return to mission control |

### Graph View Screen

| Key | Action | Description |
|-----|--------|-------------|
| `↑/↓` | Navigate | Move through graph nodes |
| `←/→` | Expand/Collapse | Expand or collapse tree nodes |
| `Enter` | View Details | Open finding details (if applicable) |
| `/` | Search | Search for specific nodes |
| `Escape` | Clear Search | Clear search filter |
| `f` | Filter | Filter by node type or severity |

### Findings Screen

| Key | Action | Description |
|-----|--------|-------------|
| `↑/↓` | Navigate | Move through findings list |
| `Enter` | View Details | Open finding detail screen |
| `e` | Export | Export findings to file |
| `s` | Sort | Change sorting criteria |
| `f` | Filter | Filter by severity or category |
| `r` | Refresh | Refresh findings list |

### Finding Detail Screen

| Key | Action | Description |
|-----|--------|-------------|
| `c` | Copy PoC | Copy proof-of-concept to clipboard |
| `t` | Re-test | Trigger re-testing of vulnerability |
| `e` | Export | Export finding to file |
| `↑/↓` | Scroll | Scroll through finding details |
| `Escape` | Back | Return to findings list |

## Status Indicators

### Agent Status Icons

- 🟢 **Active**: Agent is currently working
- 🟡 **Idle**: Agent is waiting for tasks
- 🔴 **Error**: Agent encountered an error
- ⏸️ **Paused**: Agent is paused
- ⚫ **Stopped**: Agent is not running

### Finding Severity Colors

- 🔴 **Critical**: Immediate security risk
- 🟠 **High**: Significant security concern
- 🟡 **Medium**: Moderate security issue
- 🔵 **Low**: Minor security finding
- ⚪ **Info**: Informational finding

### Node Type Icons

- 🌐 **Domain**: Target domain or subdomain
- 🖥️ **Host**: Individual host or server
- 🔌 **Port**: Open network port
- 📁 **Directory**: Web directory or path
- 📄 **File**: Individual file or resource
- 🔧 **Service**: Running service or application
- 🔍 **Vulnerability**: Security finding

## Tips and Best Practices

### Efficient Navigation

1. **Use Tab Cycling**: In multi-panel views, use Tab to quickly switch focus
2. **Learn Global Shortcuts**: `h` for home and `?` for help are your friends
3. **Use Search**: In graph view, use `/` to quickly find specific nodes
4. **Filter Findings**: Use filtering to focus on specific severity levels

### Monitoring Scans

1. **Mission Control Dashboard**: Primary view for monitoring active scans
2. **Activity Log**: Watch real-time agent activities and discoveries
3. **Agent Chat**: Communicate directly with agents for guidance
4. **Graph Updates**: Watch the attack surface grow in real-time

### Managing Findings

1. **Severity Grouping**: Findings are automatically grouped by severity
2. **Export Options**: Export individual findings or complete reports
3. **Re-testing**: Use the re-test feature to validate fixes
4. **Copy PoCs**: Easily copy proof-of-concepts for validation

### Performance Tips

1. **Limit Agent Count**: Start with 2-3 agents for better performance
2. **Use Filters**: Filter large datasets to improve responsiveness
3. **Regular Cleanup**: Delete old projects to maintain performance
4. **Monitor Resources**: Watch system resources during large scans

## Troubleshooting

### Common Issues

**TUI Won't Start**
- Check database connection with `kodiak init`
- Verify LLM configuration with `kodiak config`
- Run with `--debug` flag for detailed error messages

**Slow Performance**
- Reduce number of active agents
- Check system resources (CPU, memory)
- Clear old scan data from database

**Agent Errors**
- Check LLM API keys and quotas
- Verify network connectivity
- Review agent logs in activity panel

**Display Issues**
- Ensure terminal supports Unicode characters
- Check terminal size (minimum 80x24 recommended)
- Try different terminal emulators if issues persist

### Debug Mode

Run with debug mode for detailed logging:

```bash
kodiak tui --debug
```

This provides:
- Detailed error messages
- Performance metrics
- Database query logging
- Agent communication logs

### Getting Help

1. **In-App Help**: Press `?` for context-sensitive help
2. **Documentation**: Check `docs/` directory for detailed guides
3. **Logs**: Review application logs for error details
4. **Community**: Join discussions and report issues on GitHub

## Advanced Features

### Custom Keyboard Shortcuts

The TUI supports customization through configuration files. Advanced users can modify keyboard bindings by editing the configuration.

### Multi-Project Workflows

- Switch between projects without losing state
- Run multiple scans simultaneously
- Share findings across related projects

### Integration with External Tools

- Export findings in multiple formats
- Import target lists from external sources
- Integrate with CI/CD pipelines

### Automation

- Use CLI commands for automated workflows
- Script project creation and management
- Integrate with monitoring systems

## Accessibility

The TUI is designed with accessibility in mind:

- Full keyboard navigation (no mouse required)
- High contrast color schemes
- Screen reader compatible text
- Consistent navigation patterns
- Clear visual indicators and feedback

For accessibility issues or suggestions, please open an issue on GitHub.