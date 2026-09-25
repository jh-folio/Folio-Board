$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

# 번들 파이썬은 fastapi 등 의존성이 실제로 있을 때만 사용하고, 없으면 시스템 py -3로 폴백한다.
# (codex 런타임이 리셋되어 패키지가 빠져도 이 런처가 계속 동작하도록.)
$UseBundled = $false
if (Test-Path $BundledPython) {
  # 프로브 중에는 에러 중단(Stop)을 끈다: 깨진 번들 파이썬의 stderr가 스크립트를 멈추지 않도록.
  $eap = $ErrorActionPreference
  $ErrorActionPreference = 'SilentlyContinue'
  & $BundledPython -c "import fastapi" 1>$null 2>$null
  if ($LASTEXITCODE -eq 0) { $UseBundled = $true }
  $ErrorActionPreference = $eap
}

# app.py와 같은 기본값을 쓴다. 여기서만 8787을 박아두면 PORT를 바꿨을 때 안내가 어긋난다.
$Port = if ($env:PORT) { $env:PORT } else { "8787" }
# localhost가 아니라 127.0.0.1이다. Windows에서 localhost는 ::1을 먼저 시도하고 폴백까지
# 기다려 요청마다 약 2초를 낸다(실측 2.02초 vs 0.01초). 서버는 IPv4만 연다.
$Url = "http://127.0.0.1:$Port"

Write-Host ""
Write-Host "Folio Board starting..." -ForegroundColor Green
Write-Host "Address: $Url" -ForegroundColor Cyan
Write-Host "Closing this window stops Folio Board." -ForegroundColor Yellow
Write-Host ""

# 서버가 실제로 응답하기 시작하면 브라우저를 연다. 바로 열면 연결 거부 화면이 먼저 뜬다.
# 백그라운드 작업이라 아래 서버 실행을 막지 않는다. 앱 안의 `서버 재시작`(종료 코드 3)으로
# 다시 돌 때는 열지 않는다 — 이미 열려 있는 탭 옆에 새 탭이 계속 쌓인다.
# 넉넉히 기다린다. 시작 시간은 인덱스 크기에 좌우된다 — 실측으로 12,730개 문서
# 701MB 인덱스를 따뜻한 디스크에서 6.9초에 읽지만, 콜드 캐시나 느린 디스크에서는
# 훨씬 오래 걸린다. 기다리는 비용은 없고, 못 뜨면 이 작업만 조용히 끝난다.
$Opener = Start-Job -ArgumentList $Url, $Port -ScriptBlock {
  param($Url, $Port)
  for ($i = 0; $i -lt 1200; $i++) {
    try {
      $client = New-Object System.Net.Sockets.TcpClient
      $client.Connect("127.0.0.1", [int]$Port)
      $client.Close()
      Start-Process $Url
      return
    } catch {
      Start-Sleep -Milliseconds 500
    }
  }
}

# Exit code 7 = restart signal from the in-app restart button (app.py RESTART_EXIT_CODE).
# NOT 3: uvicorn exits 3 (STARTUP_FAILURE) on any startup failure, including a port
# that is already in use. Treating 3 as "restart" made this loop forever - start,
# fail to bind, print Restarting..., start again. Measured on this machine.
# Loop until the server exits with any other code.
$shouldRestart = $true
while ($shouldRestart) {
  try {
    if ($UseBundled) {
      & $BundledPython app.py
    } else {
      py -3 app.py
    }
  } catch {
    Write-Host ""
    Write-Host "Folio Board could not start:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    # 여기서만 창을 붙잡는다. 오류 메시지가 창과 함께 사라지면 원인을 알 수 없다.
    Read-Host "Press Enter to close"
    $shouldRestart = $false
    continue
  }
  $exitCode = $LASTEXITCODE
  $shouldRestart = ($exitCode -eq 7)
  if ($shouldRestart) {
    Write-Host ""
    Write-Host "Restarting..." -ForegroundColor Yellow
    Write-Host ""
  } elseif ($exitCode -ne 0) {
    # The server printed why it could not start. Hold the window so the reason
    # stays readable instead of vanishing when the window closes.
    Write-Host ""
    Read-Host "Press Enter to close"
  }
}

if ($Opener) { Remove-Job -Job $Opener -Force -ErrorAction SilentlyContinue }
