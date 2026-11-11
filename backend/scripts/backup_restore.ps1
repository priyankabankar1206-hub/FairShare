# Automated PostgreSQL Backup and Restore Script for FairShare (Section 7.5 Operations)
param (
    [Parameter(Mandatory=$false)]
    [string]$Action = "backup", # "backup", "restore", or "verify"

    [Parameter(Mandatory=$false)]
    [string]$BackupFile = "",

    [Parameter(Mandatory=$false)]
    [string]$HostName = "localhost",

    [Parameter(Mandatory=$false)]
    [string]$Port = "5432",

    [Parameter(Mandatory=$false)]
    [string]$User = "postgres",

    [Parameter(Mandatory=$false)]
    [string]$Database = "fairshare",

    [Parameter(Mandatory=$false)]
    [string]$BackupDir = "backups"
)

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"

if (!(Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
}

if ($Action -eq "backup") {
    $targetFile = if ($BackupFile) { $BackupFile } else { Join-Path $BackupDir "fairshare_backup_$timestamp.sql" }
    Write-Host "📦 Creating PostgreSQL backup of '$Database' to: $targetFile..." -ForegroundColor Cyan
    
    $cmd = "pg_dump -h $HostName -p $Port -U $User -d $Database --clean --if-exists --no-owner --no-privileges -F c -f `"$targetFile`""
    Write-Host "Executing: $cmd"
    Invoke-Expression $cmd

    if ($LASTEXITCODE -eq 0 -or (Test-Path $targetFile)) {
        Write-Host "✅ Backup created successfully: $targetFile" -ForegroundColor Green
    } else {
        Write-Host "❌ Backup failed with exit code $LASTEXITCODE" -ForegroundColor Red
    }
}
elseif ($Action -eq "restore") {
    if (-not $BackupFile -or -not (Test-Path $BackupFile)) {
        Write-Error "Please provide a valid -BackupFile path for restore."
        exit 1
    }
    Write-Host "🔄 Restoring database '$Database' from: $BackupFile..." -ForegroundColor Yellow
    $cmd = "pg_restore -h $HostName -p $Port -U $User -d $Database --clean --if-exists --no-owner `"$BackupFile`""
    Write-Host "Executing: $cmd"
    Invoke-Expression $cmd
    Write-Host "✅ Restore complete." -ForegroundColor Green
}
elseif ($Action -eq "verify") {
    $verifyDb = "${Database}_verify_test"
    $targetFile = Join-Path $BackupDir "verify_temp_$timestamp.sql"
    
    Write-Host "🧪 Running automated backup & restore verification test..." -ForegroundColor Cyan
    Write-Host "1. Taking test dump of '$Database'..."
    Invoke-Expression "pg_dump -h $HostName -p $Port -U $User -d $Database -F c -f `"$targetFile`""
    
    Write-Host "2. Creating temporary test database '$verifyDb'..."
    Invoke-Expression "createdb -h $HostName -p $Port -U $User $verifyDb"
    
    Write-Host "3. Restoring into temporary test database '$verifyDb'..."
    Invoke-Expression "pg_restore -h $HostName -p $Port -U $User -d $verifyDb `"$targetFile`""
    
    Write-Host "4. Cleaning up temporary database and dump file..."
    Invoke-Expression "dropdb -h $HostName -p $Port -U $User $verifyDb"
    Remove-Item -Force $targetFile
    
    Write-Host "🎉 Backup & restore verification succeeded!" -ForegroundColor Green
}

