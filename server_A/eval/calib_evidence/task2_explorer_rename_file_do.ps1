# explorer_rename_file - direct rename (end state)
# This creates the exact end state that the oracle checks

$evalDir = "C:\Users\86178\AppData\Local\HAJIMI\eval"
$oldFile = Join-Path $evalDir "old_a.txt"
$newFile = Join-Path $evalDir "new_a.txt"

Write-Host "Renaming file..."
Write-Host "From: $oldFile"
Write-Host "To: $newFile"

# Check if old file exists
if (!(Test-Path $oldFile)) {
    Write-Host "ERROR: Old file does not exist"
    exit 1
}

# Rename the file
Rename-Item -Path $oldFile -NewName "new_a.txt" -Force

Write-Host "File renamed"

# Verify
if ((Test-Path $newFile) -and !(Test-Path $oldFile)) {
    Write-Host "SUCCESS: File renamed correctly"
    Write-Host "new_a.txt exists: $(Test-Path $newFile)"
    Write-Host "old_a.txt exists: $(Test-Path $oldFile)"
    exit 0
} else {
    Write-Host "ERROR: Rename failed"
    Write-Host "new_a.txt exists: $(Test-Path $newFile)"
    Write-Host "old_a.txt exists: $(Test-Path $oldFile)"
    exit 1
}
