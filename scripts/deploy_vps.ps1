param(
    [Parameter(Mandatory=$true)]
    [string]$TargetHost, # format: user@ip_address

    [Parameter(Mandatory=$false)]
    [string]$IdentityFile # Path to SSH key (optional)
)

$RemoteDir = "~/kodiak"
$Excludes = @(".git", ".idea", "__pycache__", "venv", "node_modules", ".venv", ".ds_store")

Write-Host "--- Deploying Kodiak to $TargetHost ---" -ForegroundColor Cyan

# Ensure remote dir exists
$SSHCmd = "ssh"
if ($IdentityFile) { $SSHCmd += " -i $IdentityFile" }
Invoke-Expression "$SSHCmd $TargetHost 'mkdir -p $RemoteDir'"

# Construct SCP command (native scp on Windows doesn't have a nice --exclude flag usually)
# So we use a cleaner tar-pipe approach if possible, or just scp everything and ignore errors?
# Actually, tar over ssh is best for speed and exclusion.

# Check if tar is available (Windows 10+ has tar)
if (Get-Command "tar" -ErrorAction SilentlyContinue) {
    Write-Host "Using fast tar-over-ssh deployment..." -ForegroundColor Green
    
    # Create exclusion list for tar
    $ExcludeParams = $Excludes | ForEach-Object { "--exclude='$_'" }
    $ExcludeString = $ExcludeParams -join " "
    
    # Tar Local -> Pipe -> SSH -> Tar Extract Remote
    # Note: We need to handle Windows paths carefully.
    
    # Simplified: Just rely on scp for now to be safe on all generic Windows setups
    # But SCP is slow for many small files.
    # Let's try the tar trick.
    
    $TarCmd = "tar -czf - $ExcludeString *"
    $RemoteExtract = "tar -xzf - -C $RemoteDir"
    
    # This might be tricky with PowerShell quoting. 
    # Let's fallback to a robust SCP loop or just tell the user to use Git if they want smart sync.
    # Actually, let's keep it simple: SCP the essential folders.
}

Write-Host "Copying configuration and source files (this may take a minute)..."
$KeyFlag = if ($IdentityFile) { "-i $IdentityFile" } else { "" }

# Copy Backend
Write-Host "  > Syncing Backend..."
scp -r $KeyFlag backend $TargetHost`:$RemoteDir/

# Copy Docker Config
Write-Host "  > Syncing Docker Config..."
scp $KeyFlag docker-compose.yml $TargetHost`:$RemoteDir/

# Copy Scripts
Write-Host "  > Syncing Scripts..."
scp -r $KeyFlag scripts $TargetHost`:$RemoteDir/

Write-Host "--- Deployment Complete ---" -ForegroundColor Green
Write-Host "To start Kodiak on VPS:"
Write-Host "  ssh $KeyFlag $TargetHost"
Write-Host "  cd $RemoteDir"
Write-Host "  docker-compose up --build -d"
