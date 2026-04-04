#!/bin/bash
# Nave run script - quick access to common workflows

set -euo pipefail

# Change to script directory
cd "$(dirname "${BASH_SOURCE[0]}")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_usage() {
    cat << EOF
Usage: ./run.sh <command> [options]

Commands:
  weekly-cot          Run weekly COT analysis (Sunday driver)
  openbb_tools        Launch OpenBB tools interface
  trading             Run trading strategy (dry-run)
  help                Show this help message

Weekly COT Options:
  --live              Enable live trading (default: dry-run)
  --capital N         Set trading capital (default: 2000)
  --risk N            Set risk per trade as decimal (default: 0.10)
  --plain             Plain text output (no rich formatting)
  --wallet NAME       Use specific wallet (default: openfang)

Examples:
  ./run.sh weekly-cot                    # Dry run with defaults
  ./run.sh weekly-cot --capital 5000     # Custom capital
  ./run.sh weekly-cot --live             # Live trading mode
  ./run.sh weekly-cot --plain --risk 0.08  # Plain output, 8% risk

EOF
}

# Parse command
cmd="${1:-}"
shift || true

case "$cmd" in
  "weekly-cot")
    echo -e "${BLUE}Running Weekly COT Analysis...${NC}"
    python scripts/weekly_cot_analysis.py "$@"
    ;;
    
  "openbb_tools")
    echo -e "${BLUE}Launching OpenBB Tools...${NC}"
    python scripts/openbb_tools.py "$@"
    ;;
    
  "trading")
    echo -e "${YELLOW}Running trading strategy (dry-run mode)...${NC}"
    python -m trading.strategy --dry-run "$@"
    ;;
    
  "help"|"--help"|"-h"|"")
    print_usage
    ;;
    
  *)
    echo -e "${RED}Error: Unknown command '$cmd'${NC}" >&2
    print_usage
    exit 1
    ;;
esac
