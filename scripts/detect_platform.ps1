# Get GPUs
$gpus = Get-CimInstance Win32_VideoController

foreach ($gpu in $gpus) {
    $gpuName = $gpu.Name
    Write-Host "Found GPU: $gpuName" -ForegroundColor Cyan

    if ($gpuName -match "NVIDIA") {
        Write-Host "Testing NVIDIA (Windows)..." -ForegroundColor Yellow
        # Windows NVIDIA uses --gpus all
        docker run --rm --gpus all ubuntu nvidia-smi -L
    } 
    elseif ($gpuName -match "AMD|Radeon") {
        Write-Host "Testing AMD (Windows/WSL2)..." -ForegroundColor Yellow
        # Windows AMD uses /dev/dxg
        docker run --rm --device /dev/dxg ubuntu ls -l /dev/dxg
    } 
    elseif ($gpuName -match "Intel") {
        Write-Host "Testing Intel (Windows/WSL2)..." -ForegroundColor Yellow
        docker run --rm --device /dev/dxg ubuntu ls -l /dev/dxg
    } 
    else {
        Write-Host "Unknown GPU: $gpuName" -ForegroundColor Red
    }
}