Set-Location $PSScriptRoot
Write-Host "Iniciando Enriquecimento NIO em http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "Pressione Ctrl+C para parar." -ForegroundColor DarkGray
python manage.py runserver 8000
