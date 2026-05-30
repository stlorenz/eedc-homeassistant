#!/usr/bin/env bash
# =============================================================================
# backup-context.sh – Off-box-Durability für den gitignorten Claude/eedc-Kontext
#
# Sichert die NICHT-git-getrackten, nur-lokal existierenden Kontext-Dateien der
# zentralen Dev-Box (docker.iot, 10.100.1.200) gegen Box-/Disk-Verlust:
#   1. Memory   ~/.claude/projects/-home-gernot-claude-eedc-homeassistant/memory/
#   2. Drafts   eedc-homeassistant/docs/drafts/      (.gitignore:76)
#   3. Workspace ~/claude/eedc.code-workspace        (in keinem Repo)
#   4. settings.local.json  eedc-homeassistant/.claude/  (.gitignore:59)
#
# Diese vier liegen sonst NUR auf der einen ext4-LV der Box → Single Point of
# Loss. Dieses Script packt sie stündlich (cron) in ein Tarball (lokales
# Staging, rollendes Fenster) und rsync't das Staging-Verzeichnis off-box auf
# ein konfigurierbares Ziel (Peer/NAS).
#
# Ablöser von sync-claude.sh FÜR DIESE BOX: unter der Konsolidierung sind
# iMac/gernot001 nur noch Thin-Remote-SSH-Clients ohne lokale Kopie → es gibt
# nichts mehr zu reconcilen (kein P2P-Sync), nur noch Backup-Durability.
#
# KONFIG: ~/.config/eedc-backup.env  (wird gesourct, wenn vorhanden)
#   export CLAUDE_CTX_BACKUP_TARGET="gernot@192.168.1.102:~/claude-context-backups/"
#   # optional: CLAUDE_CTX_KEEP=96   (Anzahl lokal vorgehaltener Tarballs)
#
# EINMALIGE FREISCHALTUNG (needs Gernot, interaktiv – Box-Key auf Ziel erlauben):
#   ssh-copy-id gernot@<ziel>        # einmal Passwort des Ziels eingeben
#   # oder ~/.ssh/id_ed25519.pub-Inhalt in <ziel>:~/.ssh/authorized_keys hängen
#
# RESTORE:
#   tar xzf eedc-context-YYYYMMDD-HHMMSS.tar.gz -C /tmp/restore
#   rsync -a /tmp/restore/memory/   ~/.claude/projects/-home-gernot-claude-eedc-homeassistant/memory/
#   rsync -a /tmp/restore/drafts/   ~/claude/eedc-homeassistant/docs/drafts/
#   cp /tmp/restore/workspace/eedc.code-workspace ~/claude/
#   cp /tmp/restore/settings.local.json ~/claude/eedc-homeassistant/.claude/
# =============================================================================
set -uo pipefail

# --- Rekursions-/Re-Entry-Schutz (VOR dem Sourcen!) --------------------------
# Verhindert verschachtelte Selbstaufrufe (z. B. falls die gesourcte Konfig
# versehentlich eine Befehlszeile enthält) und überlappende cron-Läufe: ein
# Kindprozess erbt das exportierte Lock und bricht sofort ab.
if [ -n "${_EEDC_BACKUP_LOCK:-}" ]; then
  echo "[backup-context] bereits aktiv (Re-Entry/Rekursion) — Abbruch." >&2
  exit 0
fi
export _EEDC_BACKUP_LOCK=1

# --- Konfig laden (optional) -------------------------------------------------
[ -f "$HOME/.config/eedc-backup.env" ] && . "$HOME/.config/eedc-backup.env"

# --- Quellen (die vier gitignorten Asset-Sets) -------------------------------
MEMORY_DIR="$HOME/.claude/projects/-home-gernot-claude-eedc-homeassistant/memory"
DRAFTS_DIR="$HOME/claude/eedc-homeassistant/docs/drafts"
WORKSPACE="$HOME/claude/eedc.code-workspace"
SETTINGS_LOCAL="$HOME/claude/eedc-homeassistant/.claude/settings.local.json"

# --- Lokales Staging + Retention ---------------------------------------------
STAGE_DIR="${CLAUDE_CTX_STAGE:-$HOME/.claude/backups/context}"
KEEP="${CLAUDE_CTX_KEEP:-96}"                 # lokal vorgehaltene Tarballs (stündlich ≈ 4 Tage)
TARGET="${CLAUDE_CTX_BACKUP_TARGET:-}"        # rsync-Ziel; leer = LOKAL-ONLY (kein Box-Loss-Schutz)

ts="$(date +%Y%m%d-%H%M%S)"
tarball="$STAGE_DIR/eedc-context-$ts.tar.gz"
mkdir -p "$STAGE_DIR"

# --- Sauberes Staging zusammenstellen, dann packen ---------------------------
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/memory" "$work/drafts" "$work/workspace"
rsync -a "$MEMORY_DIR/" "$work/memory/" 2>/dev/null
rsync -a "$DRAFTS_DIR/" "$work/drafts/" 2>/dev/null
cp -a "$WORKSPACE" "$work/workspace/" 2>/dev/null || echo "[backup-context] WARN: workspace fehlt: $WORKSPACE"
cp -a "$SETTINGS_LOCAL" "$work/settings.local.json" 2>/dev/null || echo "[backup-context] WARN: settings.local.json fehlt: $SETTINGS_LOCAL"

{
  echo "created:       $ts"
  echo "host:          $(hostname)"
  echo "memory_files:  $(find "$work/memory" -type f | wc -l)"
  echo "drafts_files:  $(find "$work/drafts" -type f | wc -l)"
} > "$work/MANIFEST.txt"

if ! tar -czf "$tarball" -C "$work" memory drafts workspace settings.local.json MANIFEST.txt 2>/dev/null; then
  echo "[backup-context] ERROR: tar fehlgeschlagen"; exit 1
fi
echo "[backup-context] $ts  staged $tarball ($(du -h "$tarball" | cut -f1), mem=$(find "$work/memory" -type f|wc -l) drafts=$(find "$work/drafts" -type f|wc -l))"

# --- Lokale Retention (rollendes Fenster) ------------------------------------
ls -1t "$STAGE_DIR"/eedc-context-*.tar.gz 2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm -f

# --- Off-box-Leg -------------------------------------------------------------
if [ -z "$TARGET" ]; then
  echo "[backup-context] WARN: CLAUDE_CTX_BACKUP_TARGET nicht gesetzt → LOKAL-ONLY (KEIN Box-Loss-Schutz!)."
  echo "[backup-context]       Ziel in ~/.config/eedc-backup.env eintragen + Box-Key per ssh-copy-id freischalten."
  exit 0
fi
# Ohne --delete: lokal = rollendes Fenster (KEEP), Ziel = vollständiges Archiv.
if rsync -a -e 'ssh -o BatchMode=yes -o ConnectTimeout=8' "$STAGE_DIR/" "$TARGET" 2>/tmp/backup-context-rsync.err; then
  echo "[backup-context] off-box OK → $TARGET"
else
  echo "[backup-context] ERROR: off-box rsync → $TARGET fehlgeschlagen (siehe /tmp/backup-context-rsync.err). Lokales Tarball bleibt erhalten."
  exit 1
fi
