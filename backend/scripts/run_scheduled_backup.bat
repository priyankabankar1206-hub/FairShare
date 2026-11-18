@echo off
cd /d "C:\Users\Shweta\OneDrive\Desktop\FairShare-GitHub\backend"
"C:\Users\Shweta\AppData\Local\Programs\Python\Python314\python.exe" "C:\Users\Shweta\OneDrive\Desktop\FairShare-GitHub\backend\scripts\backup_database.py" >> "C:\Users\Shweta\OneDrive\Desktop\FairShare-GitHub\backend\logs\scheduled_backup.log" 2>&1
exit /b %errorlevel%
