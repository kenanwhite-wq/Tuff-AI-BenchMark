#!/usr/bin/env bash
# deploy.sh — pull latest code, reinstall deps, rebuild React, restart services
# Run on the VPS as the deploy user: ./deploy.sh

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$APP_DIR/.venv-1"
FRONTEND="$APP_DIR/frontend"
DB="$APP_DIR/benchmark.db"
BACKUP_DIR="$APP_DIR/backups"

# ── colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC}  $*"; }
warn() { echo -e "${YELLOW}!${NC}  $*"; }
die()  { echo -e "${RED}✗${NC}  $*" >&2; exit 1; }

# ── preflight ──────────────────────────────────────────────────────────────────
[[ -d "$VENV" ]]            || die "Virtualenv $VENV not found — run initial setup first"
[[ -f "$FRONTEND/package.json" ]] || die "Frontend package.json not found"
command -v npm   >/dev/null || die "npm not found"

echo ""
echo "══════════════════════════════════════════"
echo "  Tuff AI — deploy $(date '+%Y-%m-%d %H:%M:%S')"
echo "══════════════════════════════════════════"
echo ""

# ── 1. backup database ─────────────────────────────────────────────────────────
echo "── 1/5  Backing up database"
mkdir -p "$BACKUP_DIR"
if [[ -f "$DB" ]]; then
    STAMP=$(date '+%Y%m%d-%H%M%S')
    cp "$DB" "$BACKUP_DIR/benchmark-${STAMP}.db"
    ok "Backed up to $BACKUP_DIR/benchmark-${STAMP}.db"
    # Keep only the 10 most recent backups
    ls -t "$BACKUP_DIR"/benchmark-*.db 2>/dev/null | tail -n +11 | xargs -r rm --
else
    warn "benchmark.db not found — skipping backup"
fi

# ── 2. git pull ────────────────────────────────────────────────────────────────
echo ""
echo "── 2/5  Pulling latest code"
cd "$APP_DIR"

BEFORE=$(git rev-parse --short HEAD)
git pull --ff-only
AFTER=$(git rev-parse --short HEAD)

if [[ "$BEFORE" == "$AFTER" ]]; then
    warn "Already up to date ($AFTER) — continuing anyway"
else
    ok "Updated $BEFORE → $AFTER"
    echo ""
    git log --oneline "$BEFORE..$AFTER"
fi

# ── 3. python deps ─────────────────────────────────────────────────────────────
echo ""
echo "── 3/5  Installing Python dependencies"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$APP_DIR/requirements.txt"
ok "Python dependencies up to date"

# ── 4. build react ─────────────────────────────────────────────────────────────
echo ""
echo "── 4/5  Building React frontend"
cd "$FRONTEND"
npm install --silent
REACT_APP_API_BASE_URL=/api npm run build
ok "React build complete → $FRONTEND/build"

# ── 5. restart services ────────────────────────────────────────────────────────
echo ""
echo "── 5/5  Restarting services"
sudo systemctl restart tuffai-api
ok "tuffai-api restarted"

sudo systemctl restart tuffai-scheduler
ok "tuffai-scheduler restarted"

# Reload nginx to pick up any new static assets (no downtime)
sudo systemctl reload nginx
ok "nginx reloaded"

# ── health check ───────────────────────────────────────────────────────────────
echo ""
echo "── Health check"
sleep 3

for svc in tuffai-api tuffai-scheduler nginx; do
    if systemctl is-active --quiet "$svc"; then
        ok "$svc is running"
    else
        die "$svc failed to start — check: sudo journalctl -u $svc -n 50"
    fi
done

# Quick API smoke test
if curl -sf -o /dev/null --max-time 5 http://127.0.0.1:5001/api/models; then
    ok "API responded on :5001"
else
    warn "API did not respond on :5001 yet (may still be starting)"
fi

echo ""
echo -e "${GREEN}Deploy complete.${NC}"
echo "  Logs:  sudo journalctl -u tuffai-api -f"
echo "         sudo journalctl -u tuffai-scheduler -f"
echo ""
