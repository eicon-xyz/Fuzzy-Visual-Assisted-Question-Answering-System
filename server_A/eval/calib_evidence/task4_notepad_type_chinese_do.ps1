# notepad_type_chinese - direct file creation with Chinese content
$savePath = "C:\Users\86178\AppData\Local\HAJIMI\eval\cn_甲.txt"
$textToType = "测试文本甲"

Write-Host "Creating file..."
Write-Host "Path: $savePath"

# Create directory if needed
$dir = Split-Path -Parent $savePath
if (!(Test-Path $dir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

# Write file with UTF-8
Set-Content -Path $savePath -Value $textToType -Encoding UTF8

Write-Host "File created"

# Verify
if (Test-Path $savePath) {
    $content = Get-Content $savePath -Raw -Encoding UTF8
    Write-Host "Content: $content"
    if ($content -match [regex]::Escape($textToType)) {
        Write-Host "SUCCESS"
        exit 0
    } else {
        Write-Host "ERROR: Mismatch"
        exit 1
    }
} else {
    Write-Host "ERROR: Not created"
    exit 1
}
