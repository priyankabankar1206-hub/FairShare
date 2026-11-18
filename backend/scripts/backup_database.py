from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, unquote
import os
import subprocess
import sys

BACKUP_DIR = Path(__file__).resolve().parent.parent / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

try:
    url = next(
        line.strip().split("=", 1)[1].strip().strip('"').strip("'")
        for line in ENV_FILE.open(encoding="utf-8")
        if line.strip().startswith("DATABASE_URL=")
    )
except (StopIteration, OSError):
    print("ERROR: DATABASE_URL was not found in backend/.env")
    sys.exit(1)

parts = urlsplit(url)
database_name = (parts.path or "").lstrip("/")

if database_name != "fairshare_db":
    print("ERROR: Automatic backup is restricted to fairshare_db.")
    print("No database was backed up.")
    sys.exit(1)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_file = BACKUP_DIR / f"fairshare_db_{timestamp}.dump"

env = os.environ.copy()
env["PGPASSWORD"] = unquote(parts.password or "")

command = [
    r"C:\Program Files\PostgreSQL\18\bin\pg_dump.exe",
    "-h", parts.hostname or "localhost",
    "-p", str(parts.port or 5432),
    "-U", parts.username or "postgres",
    "-F", "c",
    "-f", str(backup_file),
    database_name,
]

try:
    result = subprocess.run(command, env=env)
finally:
    env.pop("PGPASSWORD", None)

if result.returncode != 0:
    if backup_file.exists():
        backup_file.unlink()
    print("ERROR: Database backup failed.")
    sys.exit(result.returncode)

now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
print(f"[{now_str}] Backup completed successfully.")
print("Backup file:", backup_file)
print("Backup size:", backup_file.stat().st_size, "bytes")
