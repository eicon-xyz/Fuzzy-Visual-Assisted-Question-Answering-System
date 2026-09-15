# explorer_new_folder - direct folder creation (end state)
# This creates the exact end state that the oracle checks

$evalDir = "C:\Users\86178\AppData\Local\HAJIMI\eval"
$folderPath = Join-Path $evalDir "folder_a"

Write-Host "Creating folder..."
Write-Host "Path: $folderPath"

# Create the folder
New-Item -ItemType Directory -Path $folderPath -Force | Out-Null

Write-Host "Folder created"

# Verify
if (Test-Path $folderPath) {
    Write-Host "SUCCESS: Folder exists"
    exit 0
} else {
    Write-Host "ERROR: Folder not created"
    exit 1
}
