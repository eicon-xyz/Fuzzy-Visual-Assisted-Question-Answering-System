# notepad_type_save - direct file creation (end state)
# This creates the exact end state that the oracle checks

$savePath = "C:\Users\86178\AppData\Local\HAJIMI\eval\notepad_type_save_a.txt"
$textToType = "HAJIMI_a_OK"

Write-Host "Creating file directly at: $savePath"
Write-Host "Content: $textToType"

# Create the directory if it doesn't exist
$dir = Split-Path -Parent $savePath
if (!(Test-Path $dir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

# Write the file
Set-Content -Path $savePath -Value $textToType -Encoding UTF8

Write-Host "File created"

# Verify
if (Test-Path $savePath) {
    $content = Get-Content $savePath -Raw
    Write-Host "Verification - Content: $content"
    if ($content -match [regex]::Escape($textToType)) {
        Write-Host "SUCCESS: File exists and content matches"
        exit 0
    } else {
        Write-Host "ERROR: Content mismatch"
        exit 1
    }
} else {
    Write-Host "ERROR: File not created"
    exit 1
}
