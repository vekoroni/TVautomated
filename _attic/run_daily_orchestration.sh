#!/bin/bash
##############################################################################
# AVSHUNTER DAILY ORCHESTRATION SCRIPT v2.0
##############################################################################
# Purpose: Automated daily workflow for early-entry detection system
#
# Schedule:
#   4:15 PM Daily - Run discovery + progression tracking
#   8:00 AM Daily - Run premarket intelligence
#
# Usage:
#   ./run_daily_orchestration.sh evening    # 4:15 PM run
#   ./run_daily_orchestration.sh premarket  # 8:00 AM run
#   ./run_daily_orchestration.sh full       # Complete workflow (testing)
##############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0:31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PYTHON_CMD="python"
LOG_DIR="data/logs"
OUTPUT_DIR="data/output"

# Create directories
mkdir -p "$LOG_DIR"
mkdir -p "$OUTPUT_DIR"

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Timestamp
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

##############################################################################
# FUNCTION: Evening Workflow (4:15 PM)
##############################################################################
run_evening_workflow() {
    log_info "=========================================="
    log_info "AVSHUNTER EVENING WORKFLOW"
    log_info "Time: $(date)"
    log_info "=========================================="
    
    # Step 1: Discovery Scanner
    log_info ""
    log_info "STEP 1: Running Discovery Scanner..."
    log_info "------------------------------------------"
    
    if $PYTHON_CMD avshunter_discovery_signals_v16_EARLY_DETECTION.py \
        --log_level INFO \
        --progress-every 100 \
        2>&1 | tee "$LOG_DIR/discovery_$TIMESTAMP.log"
    then
        log_success "Discovery scan complete"
    else
        log_error "Discovery scan failed!"
        exit 1
    fi
    
    # Step 2: Progression Tracker
    log_info ""
    log_info "STEP 2: Running Progression Tracker..."
    log_info "------------------------------------------"
    
    if $PYTHON_CMD early_progression_tracker.py \
        2>&1 | tee "$LOG_DIR/progression_$TIMESTAMP.log"
    then
        log_success "Progression tracking complete"
    else
        log_warning "Progression tracking failed (may be first run)"
    fi
    
    # Summary
    log_info ""
    log_info "=========================================="
    log_info "EVENING WORKFLOW COMPLETE"
    log_info "=========================================="
    
    # Count outputs
    EARLY_COUNT=$(ls -1 data/output/early_watch_*.csv 2>/dev/null | tail -1 | xargs wc -l 2>/dev/null | awk '{print $1-1}' || echo "0")
    EXECUTE_COUNT=$(ls -1 data/output/execute_ready_*.csv 2>/dev/null | tail -1 | xargs wc -l 2>/dev/null | awk '{print $1-1}' || echo "0")
    GRADUATED_COUNT=$(ls -1 data/output/graduated_to_execute_*.csv 2>/dev/null | tail -1 | xargs wc -l 2>/dev/null | awk '{print $1-1}' || echo "0")
    
    log_info "Signals Generated:"
    log_info "  👀 EARLY_WATCH: $EARLY_COUNT"
    log_info "  🚨 EXECUTE: $EXECUTE_COUNT"
    log_info "  🎓 GRADUATED: $GRADUATED_COUNT"
    log_info ""
    log_info "Next: Run premarket workflow at 8:00 AM tomorrow"
    log_info "  ./run_daily_orchestration.sh premarket"
    log_info "=========================================="
}

##############################################################################
# FUNCTION: Premarket Workflow (8:00 AM)
##############################################################################
run_premarket_workflow() {
    log_info "=========================================="
    log_info "AVSHUNTER PREMARKET WORKFLOW"
    log_info "Time: $(date)"
    log_info "=========================================="
    
    # Step 3: Premarket Intelligence
    log_info ""
    log_info "STEP 3: Generating Premarket Watchlist..."
    log_info "------------------------------------------"
    
    if $PYTHON_CMD premarket_intelligence_v2.py \
        --top 15 \
        2>&1 | tee "$LOG_DIR/premarket_$TIMESTAMP.log"
    then
        log_success "Premarket intelligence complete"
    else
        log_error "Premarket intelligence failed!"
        log_error "Check that evening workflow ran successfully"
        exit 1
    fi
    
    # Summary
    log_info ""
    log_info "=========================================="
    log_info "PREMARKET WORKFLOW COMPLETE"
    log_info "=========================================="
    
    # Find latest watchlist
    LATEST_WATCHLIST=$(ls -1t data/output/premarket_watchlist_*.csv 2>/dev/null | head -1)
    
    if [ -f "$LATEST_WATCHLIST" ]; then
        WATCHLIST_COUNT=$(wc -l < "$LATEST_WATCHLIST")
        WATCHLIST_COUNT=$((WATCHLIST_COUNT - 1))  # Subtract header
        
        log_info "Today's Watchlist: $WATCHLIST_COUNT opportunities"
        log_info "File: $LATEST_WATCHLIST"
        log_info ""
        log_info "Next Steps:"
        log_info "  1. Review watchlist CSV"
        log_info "  2. Set price alerts for EXECUTE signals"
        log_info "  3. Monitor EARLY_WATCH for progression"
        log_info "  4. Execute GRADUATED setups"
    else
        log_warning "No watchlist generated"
    fi
    
    log_info "=========================================="
}

##############################################################################
# FUNCTION: Full Workflow (Testing)
##############################################################################
run_full_workflow() {
    log_info "=========================================="
    log_info "FULL WORKFLOW (TESTING)"
    log_info "=========================================="
    
    run_evening_workflow
    
    log_info ""
    log_info "Waiting 3 seconds before premarket..."
    sleep 3
    
    run_premarket_workflow
    
    log_success "Full workflow complete!"
}

##############################################################################
# FUNCTION: Show Help
##############################################################################
show_help() {
    cat << EOF
AVSHUNTER Daily Orchestration Script v2.0

Usage:
  ./run_daily_orchestration.sh <command>

Commands:
  evening     Run evening workflow (4:15 PM)
              - Discovery scan
              - Progression tracking

  premarket   Run premarket workflow (8:00 AM)
              - Generate watchlist
              - Prioritize opportunities

  full        Run complete workflow (testing)
              - Runs both evening and premarket

  help        Show this help message

Examples:
  ./run_daily_orchestration.sh evening
  ./run_daily_orchestration.sh premarket

Scheduling (cron):
  # Add to crontab:
  15 16 * * 1-5  cd /path/to/avshunter && ./run_daily_orchestration.sh evening
  0  8  * * 1-5  cd /path/to/avshunter && ./run_daily_orchestration.sh premarket

Logs:
  Saved to: data/logs/

EOF
}

##############################################################################
# MAIN
##############################################################################
main() {
    case "$1" in
        evening)
            run_evening_workflow
            ;;
        premarket)
            run_premarket_workflow
            ;;
        full)
            run_full_workflow
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "Invalid command: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# Run main with arguments
main "$@"
