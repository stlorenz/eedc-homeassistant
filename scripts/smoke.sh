#!/bin/bash
# =============================================================================
# smoke.sh — Pre-Release-Smoke-Test ohne HA-Anbindung
#
# Verwendung:
#   cd /home/gernot/claude/eedc-homeassistant
#   ./scripts/smoke.sh
#
# Was wird geprüft:
#   1. Dev-venv vorhanden + pytest installiert (auto-install via
#      requirements-dev.txt, falls fehlt)
#   2. App-Boot in Standalone-Modus → erwartete Routen-Anzahl
#   3. pytest läuft alle Akzeptanz-Tests aus eedc/backend/tests/
#
# Nutzung:
#   - Manuell zwischen Sessions als Sanity-Check
#   - Eingehängt als Pre-Check in scripts/release.sh (vor Version-Bump)
#
# Exit-Codes:
#   0 — alle Checks grün
#   1 — venv fehlt oder pip-Install fehlgeschlagen
#   2 — App-Boot fehlgeschlagen (Import-Fehler / Routen-Zahl falsch)
#   3 — pytest fehlgeschlagen (mindestens ein Test rot)
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
EEDC_DIR="$REPO_DIR/eedc"
VENV="$EEDC_DIR/backend/venv"

# Erwartete Mindest-Routen-Zahl. Wenn die App-Refactors hinzukommen, wird
# die Zahl steigen — Wert wird hier hochgezogen, damit ein versehentliches
# Routen-Drop (z. B. fehlerhafter Router-Mount im Refactor) sichtbar ist.
EXPECTED_ROUTES=217

echo -e "${BOLD}=== EEDC Smoke ===${NC}"
echo ""

# ── 1. venv + pytest sicherstellen ───────────────────────────────────────────
if [ ! -d "$VENV" ]; then
    echo -e "${RED}[1/3] Dev-venv fehlt: $VENV${NC}"
    echo "  Bitte einmalig: cd eedc && python3 -m venv backend/venv && backend/venv/bin/pip install -r backend/requirements-dev.txt"
    exit 1
fi

PYTEST="$VENV/bin/pytest"
if [ ! -x "$PYTEST" ]; then
    echo -e "${YELLOW}[1/3] pytest nicht installiert — installiere requirements-dev.txt...${NC}"
    "$VENV/bin/pip" install -q -r "$EEDC_DIR/backend/requirements-dev.txt"
    if [ ! -x "$PYTEST" ]; then
        echo -e "${RED}  pytest-Install fehlgeschlagen.${NC}"
        exit 1
    fi
fi
echo -e "${GREEN}[1/3] Dev-venv + pytest verfügbar.${NC}"

# ── 2. App-Boot + Routen-Check ───────────────────────────────────────────────
echo -e "${CYAN}[2/3] App-Boot prüfen (Standalone-Modus, kein HA-Token nötig)...${NC}"

cd "$EEDC_DIR"
APP_BOOT_LOG=$(mktemp)
trap 'rm -f "$APP_BOOT_LOG"' EXIT

if ! "$VENV/bin/python" -c "
import sys
from backend.main import app
n = len(app.routes)
print(f'Routes: {n}')
if n < $EXPECTED_ROUTES:
    print(f'FEHLER: erwartet >= $EXPECTED_ROUTES, gefunden {n}', file=sys.stderr)
    sys.exit(1)
" >"$APP_BOOT_LOG" 2>&1; then
    echo -e "${RED}  App-Boot fehlgeschlagen:${NC}"
    sed 's/^/    /' "$APP_BOOT_LOG"
    exit 2
fi
ROUTES_LINE=$(grep "^Routes:" "$APP_BOOT_LOG" || echo "Routes: ?")
echo -e "${GREEN}  $ROUTES_LINE (>=$EXPECTED_ROUTES erwartet)${NC}"

# ── 3. pytest ────────────────────────────────────────────────────────────────
echo -e "${CYAN}[3/3] Akzeptanz-Tests via pytest...${NC}"

if ! "$PYTEST" -q --no-header 2>&1 | tee /tmp/eedc-smoke-pytest.log | tail -3; then
    echo -e "${RED}  pytest fehlgeschlagen — Detail in /tmp/eedc-smoke-pytest.log${NC}"
    exit 3
fi

echo ""
echo -e "${BOLD}${GREEN}Smoke OK.${NC}"
