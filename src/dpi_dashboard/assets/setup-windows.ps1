# DPI Dashboard setup helper for Windows. Runs elevated (UAC). Windows PowerShell 5.1+.
#
# The app does not run this file from disk: it embeds the script, compressed, in the
# elevated command line, so nothing a normal user can write is executed as administrator.
# For the same reason this helper downloads and verifies zapret itself, inside a folder
# only administrators can write, and logs to a folder users can read but not change:
#     %ProgramData%\dpi-dashboard\logs\<LogName>.log
#
#   -Mode install|tune|uninstall -LogName NAME [-Strategies "s1|s2"] [-Hosts a,b] [-Tries N]
#
# install: downloads the latest bol-van/zapret release, checks the archive against the
#          SHA-256 published by GitHub and each program against upstream's sha256sum.txt,
#          copies winws and WinDivert to %ProgramFiles%\zapret, creates the "zapret"
#          service, then runs tune.
# tune:    measures the blocking with the service stopped, tries each strategy until one
#          reaches every test site, keeps the best and sets the service to start
#          automatically. Only the service installed by DPI Dashboard is changed.
# Parameters are plain strings on purpose: everything is validated after the log is open,
# so even a bad argument ends up as a message in the window.
param([string]$Mode = '', [string]$LogName = '', [string]$Strategies = '',
      [string]$Hosts = 'discord.com', [string]$Tries = '3')

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'      # Invoke-WebRequest is very slow with it
$OnWindows = ($PSVersionTable.PSEdition -eq 'Desktop') -or $IsWindows
$Base = Join-Path $env:ProgramData 'dpi-dashboard'
$Dest = Join-Path $env:ProgramFiles 'zapret'
$Svc = 'zapret'
$Mark = Join-Path $Dest '.installed-by-dpi-dashboard'
$Reg = "HKLM:\SYSTEM\CurrentControlSet\Services\$Svc"
$Api = 'https://api.github.com/repos/bol-van/zapret/releases/latest'
$DownloadPrefix = 'https://github.com/bol-van/zapret/releases/download/'
$SafeStrategy = '^--[A-Za-z0-9 =,._+:/-]+$'
$SafeHost = '^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$'
$Log = $null

# --- a folder normal users cannot write to ---------------------------------------------
# Users may create folders in %ProgramData%. A folder we did not create (wrong owner) or a
# junction pointing elsewhere is moved aside, never deleted recursively: in PowerShell 5.1
# a recursive delete follows junctions into their target.
function Protect-Dir([string]$path, [bool]$usersRead) {
    if (Test-Path -LiteralPath $path) {
        $item = Get-Item -LiteralPath $path -Force
        $reparse = [bool]($item.Attributes -band [IO.FileAttributes]::ReparsePoint)
        $ownerOk = -not $OnWindows
        if ($OnWindows -and -not $reparse) {
            $owner = [System.IO.Directory]::GetAccessControl($path).GetOwner([System.Security.Principal.SecurityIdentifier]).Value
            $ownerOk = $owner -in @('S-1-5-32-544', 'S-1-5-18')
        }
        if ($reparse -or -not $ownerOk) {
            Rename-Item -LiteralPath $path -NewName ("{0}.untrusted-{1}" -f (Split-Path $path -Leaf), [guid]::NewGuid())
        }
    }
    if (-not (Test-Path -LiteralPath $path)) { New-Item -ItemType Directory -Path $path | Out-Null }
    if (-not $OnWindows) { return }
    $admins = New-Object System.Security.Principal.SecurityIdentifier('S-1-5-32-544')
    $acl = New-Object System.Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true, $false)
    $inherit = [System.Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'
    $none = [System.Security.AccessControl.PropagationFlags]::None
    $allow = [System.Security.AccessControl.AccessControlType]::Allow
    foreach ($sid in 'S-1-5-32-544', 'S-1-5-18') {
        $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule(
            (New-Object System.Security.Principal.SecurityIdentifier($sid)), 'FullControl', $inherit, $none, $allow)))
    }
    if ($usersRead) {
        $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule(
            (New-Object System.Security.Principal.SecurityIdentifier('S-1-5-32-545')), 'ReadAndExecute', $inherit, $none, $allow)))
    }
    $acl.SetOwner($admins)
    # .NET instead of Set-Acl: no module to load, and it does not try to write the audit
    # list (which needs SeSecurityPrivilege).
    [System.IO.Directory]::SetAccessControl($path, $acl)
}

# Write-Host, not Write-Output: inside a function, Write-Output becomes part of the
# function's return value (Get-Release would return the log lines with the path, and a
# failed Start-Zapret would return @("start failed...", $false), which counts as true).
function Log([string]$s) {
    if ($Log) { [System.IO.File]::AppendAllText($Log, "$s`n", (New-Object System.Text.UTF8Encoding($false))) }
    Write-Host $s
}
function Fail([string]$s) { Log "@@ERROR $s"; Log '@@DONE fail'; exit 1 }

# --- open the log first, then validate ---------------------------------------------------
if ($LogName -notmatch '^[A-Za-z0-9-]{8,64}$') { Write-Output '@@ERROR invalid log name'; exit 2 }
Protect-Dir $Base $true
Protect-Dir (Join-Path $Base 'logs') $true
$Log = Join-Path (Join-Path $Base 'logs') "$LogName.log"
[System.IO.File]::WriteAllText($Log, '')

if ($Mode -notin @('install', 'tune', 'uninstall')) { Fail 'unknown mode' }
if ($Tries -notmatch '^[1-9][0-9]?$') { Fail 'invalid tries' }
$TriesN = [int]$Tries
$HostList = @($Hosts.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
foreach ($h in $HostList) { if ($h -notmatch $SafeHost) { Fail 'invalid host' } }
$Max = $HostList.Count * $TriesN
$List = @($Strategies.Split('|') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
foreach ($s in $List) { if ($s -notmatch $SafeStrategy) { Fail 'unsafe strategy' } }

function ImagePath([string]$strategy) {
    "`"$Dest\winws.exe`" --wf-tcp=80,443 --filter-tcp=80 --hostcase --new --filter-tcp=443 $strategy"
}

# --- download and verification -----------------------------------------------------------
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12 -bor `
    [System.Net.ServicePointManager]::SecurityProtocol

function Get-Url([string]$url, [string]$outFile) {
    $headers = @{ 'User-Agent' = 'dpi-dashboard'; 'Accept' = 'application/vnd.github+json' }
    if ($env:GITHUB_TOKEN -and $url.StartsWith('https://api.github.com/')) {
        $headers['Authorization'] = "Bearer $env:GITHUB_TOKEN"
    }
    try {
        Invoke-WebRequest -Uri $url -OutFile $outFile -Headers $headers -UseBasicParsing -TimeoutSec 120
    } catch {
        $code = $null
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        if ($code -eq 403 -or $code -eq 429) {
            Fail "GitHub's request limit was reached for this network; try again in an hour"
        }
        Fail "download failed: $($_.Exception.Message)"
    }
}

function Get-Release([string]$work) {
    Log '@@STEP download'
    $json = Join-Path $work 'release.json'
    Get-Url $Api $json
    $d = Get-Content -LiteralPath $json -Raw -Encoding UTF8 | ConvertFrom-Json
    $tag = [string]$d.tag_name
    if ($tag -notmatch '^v[0-9][0-9A-Za-z.\-]{0,30}$') { Fail 'release information: unexpected tag' }
    $zip = $d.assets | Where-Object { $_.name -eq "zapret-$tag.zip" } | Select-Object -First 1
    $sums = $d.assets | Where-Object { $_.name -eq 'sha256sum.txt' } | Select-Object -First 1
    if (-not $zip -or -not $sums) { Fail 'release information: no Windows archive or sha256sum.txt' }
    $digest = [string]$zip.digest
    if ($digest -notmatch '^sha256:[0-9a-f]{64}$') { Fail 'release information: GitHub did not publish a checksum' }
    foreach ($u in $zip.browser_download_url, $sums.browser_download_url) {
        if (-not ([string]$u).StartsWith($DownloadPrefix)) { Fail 'release information: unexpected download URL' }
    }
    Log "release ${tag}: $($zip.browser_download_url)"
    $zipFile = Join-Path $work 'zapret.zip'
    $sumFile = Join-Path $work 'sha256sum.txt'
    Get-Url $zip.browser_download_url $zipFile
    Get-Url $sums.browser_download_url $sumFile
    if ((Get-FileHash -LiteralPath $zipFile -Algorithm SHA256).Hash.ToLower() -ne $digest.Substring(7)) {
        Fail "archive checksum does not match GitHub's"
    }

    # Upstream's hashes of the Windows programs, keyed by path inside the archive.
    $want = @{}
    $prefix = "zapret-$tag/binaries/windows-x86_64/"
    foreach ($line in Get-Content -LiteralPath $sumFile) {
        $p = $line -split '\s+', 2
        if ($p.Count -eq 2 -and $p[1].Trim().TrimStart('*').StartsWith($prefix)) {
            $want[$p[1].Trim().TrimStart('*')] = $p[0].ToLower()
        }
    }
    if (-not $want.ContainsKey($prefix + 'winws.exe')) { Fail 'sha256sum.txt does not list winws.exe' }

    # Extract only those files, by name, into the protected work folder.
    $out = Join-Path $work 'bin'
    New-Item -ItemType Directory -Path $out | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $z = [System.IO.Compression.ZipFile]::OpenRead($zipFile)
    try {
        foreach ($e in $z.Entries) {
            $name = $e.FullName.Replace('\', '/')
            if (-not $want.ContainsKey($name)) { continue }
            $leaf = $name.Substring($prefix.Length)
            if ($leaf -notmatch '^[A-Za-z0-9._-]+$') { Fail "unexpected file name in archive: $name" }
            $target = Join-Path $out $leaf
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($e, $target)
            if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLower() -ne $want[$name]) {
                Fail "$leaf does not match upstream's sha256sum.txt"
            }
            $want.Remove($name)
        }
    } finally { $z.Dispose() }
    if ($want.Count) { Fail "missing from the archive: $(@($want.Keys) -join ', ')" }
    Log "@@STEP verified $tag"
    return $out
}

# --- service -------------------------------------------------------------------------------
Add-Type -AssemblyName System.Net.Http
[System.Net.ServicePointManager]::DefaultConnectionLimit = 64

# Every attempt is a new TLS connection (Connection: close); any HTTP answer counts.
function Probe {
    $handler = New-Object System.Net.Http.HttpClientHandler
    $handler.AllowAutoRedirect = $false
    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(8)
    $tasks = @()
    foreach ($h in $HostList) {
        for ($i = 0; $i -lt $TriesN; $i++) {
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
    if (-not (Test-Path -LiteralPath $Mark)) { Fail 'the zapret service was not installed by DPI Dashboard' }
    if ($List.Count -eq 0) { Fail 'no strategies' }
    $old = (Get-ItemProperty -LiteralPath $Reg).ImagePath
    $oldStart = (Get-Service -Name $Svc).StartType
    $wasRunning = (Get-Service -Name $Svc).Status -eq 'Running'

    Log '@@STEP baseline'
    Stop-Zapret
    Log "@@BASELINE $(Probe)/$Max"

    $best = -1; $bi = 0
    for ($i = 1; $i -le $List.Count; $i++) {
        $s = $List[$i - 1]
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
    Set-ItemProperty -LiteralPath $Reg -Name ImagePath -Value (ImagePath $List[$bi - 1])
    Set-Service -Name $Svc -StartupType Automatic
    if (-not (Start-Zapret)) { Fail 'zapret did not start with the chosen strategy' }
    Log "@@CHOSEN $bi $best/$Max"
    Log '@@DONE ok'
}

function Do-Install {
    if (-not [Environment]::Is64BitOperatingSystem) { Fail '64-bit Windows is required' }
    if (Get-Service -Name $Svc -ErrorAction SilentlyContinue) { Fail "a service named '$Svc' already exists" }
    if (Test-Path -LiteralPath $Dest) { Fail "$Dest already exists" }
    if ($List.Count -eq 0) { Fail 'no strategies' }

    $work = Join-Path $Base ("work-" + [guid]::NewGuid())
    Protect-Dir $work $false
    try {
        $bin = Get-Release $work
        Log '@@STEP copy'
        New-Item -ItemType Directory -Path $Dest | Out-Null      # inherits Program Files' ACL
        Copy-Item -Path (Join-Path $bin '*') -Destination $Dest -Force
        Set-Content -LiteralPath $Mark -Value "installed by DPI Dashboard on $(Get-Date -Format o)"
    } finally {
        Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    }

    Log '@@STEP unit'
    try {
        New-Service -Name $Svc -BinaryPathName (ImagePath $List[0]) `
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
