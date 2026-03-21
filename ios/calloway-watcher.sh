#!/bin/bash
# calloway-watcher.sh — Polls GitHub for new commits, builds in Xcode simulator,
# and saves screenshots to iCloud Drive so you can see results from your phone.
#
# Usage: ./calloway-watcher.sh [poll_interval_seconds]
# Default poll interval: 30 seconds

set -euo pipefail

# --- Configuration ---
POLL_INTERVAL="${1:-30}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
XCODE_PROJECT="$REPO_ROOT/ios/CallowayApp.xcodeproj"
SCHEME="CallowayApp"
SIMULATOR_NAME="iPhone 16"
BRANCH="claude/general-discussion-LCFpD"
BUNDLE_ID="com.calloway.app"

# iCloud Drive screenshot destination
ICLOUD_DIR="$HOME/Library/Mobile Documents/com~apple~CloudDocs/Calloway-Screenshots"
mkdir -p "$ICLOUD_DIR"

# Derived data in a predictable location so we can find the .app
DERIVED_DATA="$REPO_ROOT/ios/DerivedData"

# --- Colors for terminal output ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log()  { echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"; }
ok()   { echo -e "${GREEN}[$(date '+%H:%M:%S')] ✓${NC} $1"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')] ⚠${NC} $1"; }
err()  { echo -e "${RED}[$(date '+%H:%M:%S')] ✗${NC} $1"; }

# --- Ensure simulator is booted ---
boot_simulator() {
    local sim_udid
    sim_udid=$(xcrun simctl list devices available -j | \
        python3 -c "
import json, sys
data = json.load(sys.stdin)
for runtime, devices in data['devices'].items():
    for d in devices:
        if d['name'] == '$SIMULATOR_NAME' and d['isAvailable']:
            print(d['udid'])
            sys.exit(0)
sys.exit(1)
" 2>/dev/null) || {
        err "Simulator '$SIMULATOR_NAME' not found. Available simulators:"
        xcrun simctl list devices available
        exit 1
    }

    local state
    state=$(xcrun simctl list devices -j | \
        python3 -c "
import json, sys
data = json.load(sys.stdin)
for runtime, devices in data['devices'].items():
    for d in devices:
        if d['udid'] == '$sim_udid':
            print(d['state'])
            sys.exit(0)
" 2>/dev/null)

    if [ "$state" != "Booted" ]; then
        log "Booting simulator '$SIMULATOR_NAME'..."
        xcrun simctl boot "$sim_udid" 2>/dev/null || true
        open -a Simulator
        sleep 5
        ok "Simulator booted"
    else
        ok "Simulator already running"
    fi

    echo "$sim_udid"
}

# --- Main loop ---
main() {
    log "Calloway Watcher starting"
    log "  Repo:      $REPO_ROOT"
    log "  Branch:    $BRANCH"
    log "  Scheme:    $SCHEME"
    log "  Simulator: $SIMULATOR_NAME"
    log "  Screenshots: $ICLOUD_DIR"
    log "  Poll interval: ${POLL_INTERVAL}s"
    echo ""

    # Boot simulator once at start
    SIM_UDID=$(boot_simulator)

    # Get initial commit hash
    cd "$REPO_ROOT"
    git fetch origin "$BRANCH" 2>/dev/null
    LAST_HASH=$(git rev-parse "origin/$BRANCH" 2>/dev/null || echo "none")
    log "Starting hash: ${LAST_HASH:0:8}"

    # Do an initial build so the app is ready
    log "Running initial build..."
    if build_and_screenshot "$SIM_UDID"; then
        ok "Initial build succeeded"
    else
        warn "Initial build failed — will retry on next commit"
    fi

    echo ""
    log "Watching for commits on $BRANCH (every ${POLL_INTERVAL}s)..."
    echo ""

    while true; do
        sleep "$POLL_INTERVAL"

        # Fetch latest
        if ! git fetch origin "$BRANCH" 2>/dev/null; then
            warn "Fetch failed — will retry"
            continue
        fi

        NEW_HASH=$(git rev-parse "origin/$BRANCH" 2>/dev/null || echo "none")

        if [ "$NEW_HASH" != "$LAST_HASH" ]; then
            log "New commit detected: ${NEW_HASH:0:8}"

            # Pull changes
            git pull origin "$BRANCH" --ff-only 2>/dev/null || {
                warn "Pull failed — trying reset"
                git reset --hard "origin/$BRANCH"
            }

            if build_and_screenshot "$SIM_UDID"; then
                ok "Build + screenshot complete"
            else
                err "Build failed for ${NEW_HASH:0:8}"
            fi

            LAST_HASH="$NEW_HASH"
            echo ""
        fi
    done
}

# --- Build, install, screenshot ---
build_and_screenshot() {
    local sim_udid="$1"

    # Build
    log "Building..."
    if ! xcodebuild \
        -project "$XCODE_PROJECT" \
        -scheme "$SCHEME" \
        -destination "platform=iOS Simulator,id=$sim_udid" \
        -derivedDataPath "$DERIVED_DATA" \
        -configuration Debug \
        build 2>&1 | tail -5; then
        err "xcodebuild failed"
        return 1
    fi

    # Find the built .app
    local app_path
    app_path=$(find "$DERIVED_DATA" -name "CallowayApp.app" -type d | head -1)
    if [ -z "$app_path" ]; then
        err "Could not find built .app"
        return 1
    fi

    # Install and launch
    log "Installing to simulator..."
    xcrun simctl install "$sim_udid" "$app_path"
    xcrun simctl terminate "$sim_udid" "$BUNDLE_ID" 2>/dev/null || true
    xcrun simctl launch "$sim_udid" "$BUNDLE_ID"

    # Wait for UI to render
    sleep 3

    # Screenshot → iCloud
    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)
    local screenshot_path="$ICLOUD_DIR/calloway_${timestamp}.png"
    xcrun simctl io "$sim_udid" screenshot "$screenshot_path"
    ok "Screenshot saved: calloway_${timestamp}.png"

    # Also save a "latest.png" for quick checking
    cp "$screenshot_path" "$ICLOUD_DIR/latest.png"

    return 0
}

main "$@"
