#!/bin/bash
# Kodiak Toolbox Container Entrypoint
# Sets up the environment and starts the tool server if in sandbox mode

set -e

# Ensure PATH includes all tool directories
export PATH="/home/kodiak/go/bin:/home/kodiak/.local/bin:/home/kodiak/.npm-global/bin:$PATH"

# Print banner
echo "==============================================" 
echo " Kodiak Security Toolbox"
echo " AI-Powered Penetration Testing Environment"
echo "=============================================="
echo ""
echo "Available tools:"
echo "  Network: nmap, masscan, netcat"
echo "  Web: nuclei, nikto, sqlmap, ffuf, wapiti"
echo "  Discovery: subfinder, httpx, katana, dnsx"
echo "  Code: semgrep, bandit, trufflehog, trivy"
echo "  Browser: playwright (chromium)"
echo ""

# Check if we should start tool server
if [[ "$KODIAK_TOOL_SERVER" == "true" ]]; then
    echo "Starting Kodiak Tool Server..."
    # Tool server would be implemented here
    # For now, just keep the container running
    exec tail -f /dev/null
else
    # Interactive mode - run the provided command or start bash
    exec "$@"
fi
