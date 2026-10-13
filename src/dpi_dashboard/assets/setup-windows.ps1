# DPI Dashboard setup helper for Windows. Runs elevated (UAC). Windows PowerShell 5.1+.
#
#   setup-windows.ps1 -Mode install   -Log FILE -Source DIR -Strategies FILE -Hosts a,b [-Tries N]
#   setup-windows.ps1 -Mode tune      -Log FILE -Strategies FILE -Hosts a,b [-Tries N]
#   setup-windows.ps1 -Mode uninstall -Log FILE
#
# install: copies winws and WinDivert from an extracted, already verified zapret release to
#          "%ProgramFiles%\zapret", creates the "zapret" service, then runs tune.
# tune:    measures the blocking with the service stopped, tries each strategy until one
#          reaches every test site, keeps the best and sets the service to start
#          automatically. Only the service installed by DPI Dashboard is changed.
# Progress goes to the log file using the @@ protocol described in runner.py.
param(
    [Parameter(Mandatory = $true)][ValidateSet('install', 'tune', 'uninstall')][string]$Mode,
    [Parameter(Mandatory = $true)][string]$Log,
    [string]$Source = '',
    [string]$Strategies = '',
    [string]$Hosts = 'discord.com',
    [ValidateRange(1, 99)][int]$Tries = 3
)
$ErrorActionPreference = 'Stop'
$Dest = Join-Path $env:ProgramFiles 'zapret'
$Svc = 'zapret'
$Mark = Join-Path $Dest '.installed-by-dpi-dashboard'
$Reg = "HKLM:\SYSTEM\CurrentControlSet\Services\$Svc"
$SafeStrategy = '^--[A-Za-z0-9 =,._+:/-]+$'
$SafeHost = '^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$'

function Log([string]$s) {
    [System.IO.File]::AppendAllText($Log, "$s`n", (New-Object System.Text.UTF8Encoding($false)))
    Write-Output $s
}
function Fail([string]$s) { Log "@@ERROR $s"; Log '@@DONE fail'; exit 1 }

$HostList = @($Hosts.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
foreach ($h in $HostList) { if ($h -notmatch $SafeHost) { Fail "invalid host: $h" } }
$Max = $HostList.Count * $Tries

function ImagePath([string]$strategy) {
    "`"$Dest\winws.exe`" --wf-tcp=80,443 --filter-tcp=80 --hostcase --new --filter-tcp=443 $strategy"
}

function Read-Strategies {
    if (-not (Test-Path -LiteralPath $Strategies)) { Fail 'strategy file not found' }
    $list = @(Get-Content -LiteralPath $Strategies | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    if ($list.Count -eq 0) { Fail 'no strategies' }
    foreach ($s in $list) { if ($s -notmatch $SafeStrategy) { Fail "unsafe strategy: $s" } }
    return $list
}

Add-Type -AssemblyName System.Net.Http
[System.Net.ServicePointManager]::DefaultConnectionLimit = 64
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12 -bor `
    [System.Net.ServicePointManager]::SecurityProtocol

# Every attempt is a new TLS connection (Connection: close); any HTTP answer counts.
function Probe {
    $handler = New-Object System.Net.Http.HttpClientHandler
    $handler.AllowAutoRedirect = $false
    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(8)
    $tasks = @()
    foreach ($h in $HostList) {
        for ($i = 0; $i -lt $Tries; $i++) {
            $req = New-Object System.Net.Http.HttpRequestMessage([System.Net.Http.HttpMethod]::Head, "https://$h/")
            $req.Headers.ConnectionClose = $true
            $tasks += $client.SendAsync($req)
        }
    }
    try { [void][System.Threading.Tasks.Task]::WaitAll([System.Threading.Tasks.Task[]]$tasks, 20000) } catch { }
    $ok = @($tasks | Where-Object { $_.Status -eq 'RanToCompletion' }).Count
    $client.Dispose()
    return $ok
}

function Stop-Zapret {
    $s = Get-Service -Name $Svc -ErrorAction SilentlyContinue
    if ($s -and $s.Status -ne 'Stopped') {
        Stop-Service -Name $Svc -Force
        $s.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(15))
    }
}

function Start-Zapret {
    try {
        Stop-Zapret
        Start-Service -Name $Svc
        (Get-Service -Name $Svc).WaitForStatus('Running', [TimeSpan]::FromSeconds(10))
        Start-Sleep -Seconds 2
        return ((Get-Service -Name $Svc).Status -eq 'Running')
    } catch {
        Log "start failed: $($_.Exception.Message)"
        return $false
    }
}

function Do-Tune {
    if (-not (Test-Path -LiteralPath $Mark)) { Fail "the zapret service was not installed by DPI Dashboard" }
    $list = Read-Strategies
    $old = (Get-ItemProperty -LiteralPath $Reg).ImagePath
    $oldStart = (Get-Service -Name $Svc).StartType
    $wasRunning = (Get-Service -Name $Svc).Status -eq 'Running'

    Log '@@STEP baseline'
    Stop-Zapret
    Log "@@BASELINE $(Probe)/$Max"

    $best = -1; $bi = 0
    for ($i = 1; $i -le $list.Count; $i++) {
        $s = $list[$i - 1]
        Log "@@STEP try $i"
        Log "strategy ${i}: $s"
        Set-ItemProperty -LiteralPath $Reg -Name ImagePath -Value (ImagePath $s)
        if (-not (Start-Zapret)) { Log "@@TRY $i fail"; continue }
        $ok = Probe
        Log "@@TRY $i $ok/$Max"
        if ($ok -gt $best) { $best = $ok; $bi = $i }
        if ($ok -eq $Max) { break }
    }

    if ($best -le 0) {
        Stop-Zapret
        Set-ItemProperty -LiteralPath $Reg -Name ImagePath -Value $old
        Set-Service -Name $Svc -StartupType $oldStart
        if ($wasRunning) { [void](Start-Zapret) }
        Fail 'no strategy worked; previous settings restored'
    }
    Set-ItemProperty -LiteralPath $Reg -Name ImagePath -Value (ImagePath $list[$bi - 1])
    Set-Service -Name $Svc -StartupType Automatic
    if (-not (Start-Zapret)) { Fail 'zapret did not start with the chosen strategy' }
    Log "@@CHOSEN $bi $best/$Max"
    Log '@@DONE ok'
}

function Do-Install {
    $bin = Join-Path $Source 'binaries\windows-x86_64'
    if (-not (Test-Path -LiteralPath (Join-Path $bin 'winws.exe'))) { Fail "not a zapret release: $Source" }
    if (-not [Environment]::Is64BitOperatingSystem) { Fail '64-bit Windows is required' }
    if (Get-Service -Name $Svc -ErrorAction SilentlyContinue) { Fail "a service named '$Svc' already exists" }
    if (Test-Path -LiteralPath $Dest) { Fail "$Dest already exists" }
    $list = Read-Strategies

    Log '@@STEP copy'
    New-Item -ItemType Directory -Path $Dest | Out-Null
    Copy-Item -Path (Join-Path $bin '*') -Destination $Dest -Recurse -Force
    Set-Content -LiteralPath $Mark -Value "installed by DPI Dashboard on $(Get-Date -Format o)"

    Log '@@STEP unit'
    try {
        New-Service -Name $Svc -BinaryPathName (ImagePath $list[0]) `
            -DisplayName 'zapret DPI bypass (DPI Dashboard)' -StartupType Manual | Out-Null
        & sc.exe description $Svc 'zapret DPI bypass, installed by DPI Dashboard' | Out-Null
    } catch {
        Remove-Item -LiteralPath $Dest -Recurse -Force -ErrorAction SilentlyContinue
        Fail "could not create the service: $($_.Exception.Message)"
    }
    Do-Tune
}

function Do-Uninstall {
    if (-not (Test-Path -LiteralPath $Mark)) { Fail "zapret in $Dest was not installed by DPI Dashboard" }
    Log '@@STEP remove'
    try { Stop-Zapret } catch { }
    & sc.exe delete $Svc | Out-Null
    # winws loads the WinDivert driver from its own folder; let it unload before deleting.
    & sc.exe stop WinDivert 2>&1 | Out-Null
    for ($i = 0; $i -lt 10 -and (Test-Path -LiteralPath $Dest); $i++) {
        try { Remove-Item -LiteralPath $Dest -Recurse -Force } catch { Start-Sleep -Seconds 1 }
    }
    if (Test-Path -LiteralPath $Dest) { Fail "could not remove $Dest (reboot and try again)" }
    Log '@@DONE ok'
}

try {
    switch ($Mode) {
        'install' { Do-Install }
        'tune' { Do-Tune }
        'uninstall' { Do-Uninstall }
    }
} catch {
    Fail $_.Exception.Message
}
exit 0
