#!/usr/bin/env bash
# Generate a changelog from git history (last 6 months), grouped by date.
# Output: docs/changelog.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT="$PROJECT_ROOT/docs/changelog.md"

{
    echo "# Changelog"
    echo ""
    echo "_Auto-generated from git history. Last updated: $(date -u '+%Y-%m-%d %H:%M UTC')_"
    echo ""

    current_date=""
    git -C "$PROJECT_ROOT" log --no-merges --since="6 months ago" \
        --pretty=format:"%ad|%s|%an" --date=short | \
    while IFS='|' read -r date subject author; do
        if [ "$date" != "$current_date" ]; then
            current_date="$date"
            echo ""
            echo "## $date"
            echo ""
        fi
        echo "- $subject ($author)"
    done
} > "$OUTPUT"

echo "Changelog written to $OUTPUT"
