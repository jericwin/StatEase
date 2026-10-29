# Starts the backend (port 8000) and the Vite dev server (port 5173) for development on Windows.
$root = Split-Path -Parent $PSScriptRoot
Start-Process -NoNewWindow -FilePath "$root\backend\.venv\Scripts\python.exe" -ArgumentList "-m","uvicorn","app.main:app","--reload","--port","8000" -WorkingDirectory "$root\backend"
Set-Location "$root\frontend"
npm run dev
