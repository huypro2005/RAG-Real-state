<#
Sửa file backup: chuyển mọi bảng từ 5 schema cũ (admin, amenities, listing,
ml, rag) sang schema mặc định public, rồi xuất ra file backup mới.

Các bước script làm:
  1. Tạo DB tạm housing_fix_tmp
  2. pg_restore file backup gốc vào DB tạm
       - Nếu máy chưa cài pgvector: tự bỏ extension "vector" và bảng
         rag.listing_embeddings (bảng duy nhất dùng kiểu vector), phần còn lại restore bình thường
  3. Chạy db/move_to_public.sql (1 transaction)
  4. pg_dump ra 2 file: housing_public.dump (custom) và housing_public.sql (text)
  5. Xóa DB tạm
File backup gốc KHÔNG bị sửa.

Cách chạy (PowerShell, ở thư mục gốc project):
  $env:PGPASSWORD = "mat_khau_postgres"
  .\scripts\fix_backup.ps1 -Backup "D:\backup\data_ultilities.sql"

Tùy chọn:
  -PgBin "C:\Program Files\PostgreSQL\18\bin"   nếu báo không tìm thấy pg_restore
  -SkipVector                                  ép bỏ qua pgvector dù máy đã cài
#>
param(
    [Parameter(Mandatory = $true)][string]$Backup,
    [string]$OutDir = ".",
    [string]$DbUser = "postgres",
    [string]$DbHost = "localhost",
    [int]$Port = 5432,
    [string]$PgBin = "",
    [switch]$SkipVector
)

$ErrorActionPreference = "Stop"
if ($PgBin) { $env:Path = "$PgBin;$env:Path" }

$TmpDb   = "housing_fix_tmp"
$SqlDir  = Join-Path $PSScriptRoot "..\db"
$Backup  = (Resolve-Path $Backup).Path
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$OutDir  = (Resolve-Path $OutDir).Path
$Conn    = @("-h", $DbHost, "-p", "$Port", "-U", $DbUser)
$ListFile = Join-Path ([System.IO.Path]::GetTempPath()) "housing_restore_list.txt"

function Invoke-Pg([string]$Exe, [string[]]$Argv) {
    Write-Host ">> $Exe $($Argv -join ' ')" -ForegroundColor Cyan
    & $Exe @Argv
    if ($LASTEXITCODE -ne 0) { throw "$Exe lỗi (exit code $LASTEXITCODE)" }
}

Invoke-Pg dropdb   ($Conn + @("--if-exists", $TmpDb))
Invoke-Pg createdb ($Conn + @($TmpDb))
try {
    # --- pgvector có trên server này không? -------------------------------
    $count = [string](& psql @Conn -d $TmpDb -tAc "SELECT count(*) FROM pg_available_extensions WHERE name = 'vector'")
    if ($LASTEXITCODE -ne 0) { throw "Không kiểm tra được extension vector (psql lỗi)" }
    $useVector = ($count.Trim() -ne "0") -and (-not $SkipVector)

    $restoreArgs = $Conn + @("-d", $TmpDb, "--no-owner", "--no-privileges", "--exit-on-error")

    if (-not $useVector) {
        Write-Host ""
        Write-Host "pgvector chưa cài (hoặc dùng -SkipVector): bỏ extension vector và bảng rag.listing_embeddings" -ForegroundColor Yellow

        # pg_restore -l in mục lục; dòng nào bắt đầu bằng ';' thì pg_restore bỏ qua
        $toc = & pg_restore -l $Backup
        if ($LASTEXITCODE -ne 0) { throw "pg_restore -l lỗi (exit code $LASTEXITCODE)" }

        $skipped = 0
        $kept = foreach ($line in $toc) {
            if ($line -match 'EXTENSION - vector\b' -or $line -match 'EXTENSION vector\b' -or $line -match '\srag\slisting_embeddings\s') {
                $skipped++
                ";$line"
            } else {
                $line
            }
        }
        [System.IO.File]::WriteAllLines($ListFile, [string[]]$kept, (New-Object System.Text.UTF8Encoding($false)))
        Write-Host "Đã bỏ $skipped mục trong mục lục backup (dự kiến 6: extension, comment, bảng, dữ liệu, khóa chính, khóa ngoại)"

        $restoreArgs += @("-L", $ListFile)
    }

    Invoke-Pg pg_restore ($restoreArgs + @($Backup))

    # move_to_public.sql dùng \ir functions.sql -> chạy từ thư mục db
    Push-Location $SqlDir
    try {
        Invoke-Pg psql ($Conn + @("-d", $TmpDb, "-1", "-v", "ON_ERROR_STOP=1", "-f", "move_to_public.sql"))
    } finally { Pop-Location }

    $dump = Join-Path $OutDir "housing_public.dump"
    $sql  = Join-Path $OutDir "housing_public.sql"
    Invoke-Pg pg_dump ($Conn + @("-Fc", "--no-owner", "--no-privileges", "-f", $dump, $TmpDb))
    Invoke-Pg pg_dump ($Conn + @("-Fp", "--no-owner", "--no-privileges", "-f", $sql,  $TmpDb))

    Write-Host ""
    Write-Host "Xong:" -ForegroundColor Green
    Write-Host "  $dump  (restore: pg_restore -d housing --no-owner housing_public.dump)"
    Write-Host "  $sql   (restore: psql -d housing -f housing_public.sql)"
    if (-not $useVector) {
        Write-Host ""
        Write-Host "LƯU Ý: file mới KHÔNG có bảng listing_embeddings (cần pgvector)." -ForegroundColor Yellow
        Write-Host "File backup gốc vẫn còn đủ. Cài pgvector rồi chạy lại script này (không dùng -SkipVector) sẽ ra bản đầy đủ." -ForegroundColor Yellow
    }
}
finally {
    Remove-Item -Force -ErrorAction SilentlyContinue $ListFile
    Invoke-Pg dropdb ($Conn + @("--if-exists", $TmpDb))
}
