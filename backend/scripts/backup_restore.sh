#!/usr/bin/env bash
# Automated PostgreSQL Backup and Restore Script for FairShare (POSIX/Linux/Mac)
set -euo pipefail

ACTION="${1:-backup}"
BACKUP_DIR="${2:-backups}"
HOST="${POSTGRES_SERVER:-localhost}"
PORT="${POSTGRES_PORT:-5432}"
USER="${POSTGRES_USER:-postgres}"
DB="${POSTGRES_DB:-fairshare}"

mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

if [ "$ACTION" = "backup" ]; then
    TARGET_FILE="$BACKUP_DIR/fairshare_backup_$TIMESTAMP.dump"
    echo "📦 Creating PostgreSQL custom dump of '$DB' to: $TARGET_FILE..."
    pg_dump -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" --clean --if-exists --no-owner --no-privileges -F c -f "$TARGET_FILE"
    echo "✅ Backup created successfully: $TARGET_FILE"

elif [ "$ACTION" = "restore" ]; then
    RESTORE_FILE="${3:-}"
    if [ -z "$RESTORE_FILE" ] || [ ! -f "$RESTORE_FILE" ]; then
        echo "❌ Error: Please specify a valid backup file to restore."
        exit 1
    fi
    echo "🔄 Restoring database '$DB' from: $RESTORE_FILE..."
    pg_restore -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" --clean --if-exists --no-owner "$RESTORE_FILE"
    echo "✅ Restore completed successfully."

elif [ "$ACTION" = "verify" ]; then
    VERIFY_DB="${DB}_verify_test"
    TEMP_DUMP="$BACKUP_DIR/verify_temp_$TIMESTAMP.dump"
    echo "🧪 Running automated backup & restore verification test..."
    pg_dump -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -F c -f "$TEMP_DUMP"
    createdb -h "$HOST" -p "$PORT" -U "$USER" "$VERIFY_DB" || true
    pg_restore -h "$HOST" -p "$PORT" -U "$USER" -d "$VERIFY_DB" "$TEMP_DUMP"
    dropdb -h "$HOST" -p "$PORT" -U "$USER" "$VERIFY_DB"
    rm -f "$TEMP_DUMP"
    echo "🎉 Backup & restore verification succeeded!"
fi

