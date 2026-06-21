<#
.SYNOPSIS
    Set up an SSH config + (optionally) key-based auth for FBClicker noVNC tunneling.

.DESCRIPTION
    Creates (or updates) %USERPROFILE%\.ssh\config with a 'fbclicker' host
    entry that auto-tunnels port 6080 (noVNC) on connect. Optionally
    generates an ed25519 key pair and prints the public key so you can
    paste it into the server's ~/.ssh/authorized_keys.

.PARAMETER Host
    IP / hostname of the remote server. Default: 192.168.1.203

.PARAMETER User
    SSH username on the remote server. Default: vscode

.PARAMETER LocalPort
    Local port to forward (noVNC). Default: 6080

.PARAMETER RemotePort
    Remote port to forward. Default: 6080

.PARAMETER KeyOnly
    Also generate an ed25519 key and print the public key for installation.

.EXAMPLE
    .\setup_ssh_tunnel.ps1
    .\setup_ssh_tunnel.ps1 -Host 192.168.1.50 -User marco
    .\setup_ssh_tunnel.ps1 -KeyOnly
#>

[CmdletBinding()]
param(
    [string]$Host     = "192.168.1.203",
    [string]$User     = "vscode",
    [int]$LocalPort   = 6080,
    [int]$RemotePort  = 6080,
    [switch]$KeyOnly
)

$ErrorActionPreference = "Stop"
$sshDir   = Join-Path $env:USERPROFILE ".ssh"
$cfgPath  = Join-Path $sshDir "config"
$keyPath  = Join-Path $sshDir "id_ed25519"
$pubPath  = "$keyPath.pub"
$alias    = "fbclicker"

# --- 1. Ensure .ssh dir exists
if (-not (Test-Path $sshDir)) {
    New-Item -ItemType Directory -Path $sshDir | Out-Null
    icacls $sshDir /inheritance:r /grant:r "$($env:USERNAME):(R,W,X)" | Out-Null
}

# --- 2. Write/update ssh config
$block = @"

# >>> FBClicker noVNC tunnel (added by setup_ssh_tunnel.ps1) >>>
Host $alias
    HostName $Host
    User $User
    LocalForward ${LocalPort} localhost:${RemotePort}
    ServerAliveInterval 60
    ServerAliveCountMax 3
# <<< FBClicker <<<
"@

if (Test-Path $cfgPath) {
    $existing = Get-Content $cfgPath -Raw
    if ($existing -match "Host $alias\b") {
        Write-Host "[ssh] removing old '$alias' block from $cfgPath"
        $existing = $existing -replace "(?s)# >>> FBClicker noVNC tunnel.*?# <<< FBClicker <<<\r?\n", ""
        $existing = $existing -replace "(?s)# >>> FBClicker noVNC tunnel.*?# <<< FBClicker <<<", ""
        Set-Content -Path $cfgPath -Value $existing -NoNewline
    }
    Add-Content -Path $cfgPath -Value $block
    Write-Host "[ssh] appended '$alias' host to existing $cfgPath"
} else {
    Set-Content -Path $cfgPath -Value $block.TrimStart("`r`n")
    Write-Host "[ssh] created $cfgPath with '$alias' host"
}

# --- 3. Optional: key generation
if ($KeyOnly) {
    if (Test-Path $keyPath) {
        Write-Host "[ssh] key already exists at $keyPath (skipping generation)"
    } else {
        Write-Host "[ssh] generating ed25519 keypair..."
        ssh-keygen -t ed25519 -f $keyPath -N '""' -C "fbclicker-windows-$env:USERNAME" | Out-Null
        Write-Host "[ssh] key created: $keyPath"
    }

    Write-Host ""
    Write-Host "=== PUBLIC KEY (paste this into the server's ~/.ssh/authorized_keys) ==="
    Get-Content $pubPath
    Write-Host "==========================================================================="
    Write-Host ""
    Write-Host "One-liner (run from THIS machine):"
    Write-Host "  type `"$pubPath`" | ssh $User@$Host `"cat >> ~/.ssh/authorized_keys`""
    Write-Host ""
    Write-Host "Then log in with the key:  ssh $alias"
}

# --- 4. Print next steps
Write-Host ""
Write-Host "============================================================"
Write-Host "  Setup done"
Write-Host "============================================================"
Write-Host "  Connect:     ssh $alias"
Write-Host "  noVNC URL:   http://localhost:${LocalPort}/vnc.html"
Write-Host "  Password:    check the value of VNC_PASSWORD in .env on the server"
Write-Host ""
Write-Host "  If this is the first time, also install the public key:"
Write-Host "    .\setup_ssh_tunnel.ps1 -KeyOnly"
Write-Host "============================================================"
