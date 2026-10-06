# Recalculate an .xlsx in Excel and save it with cached values (so viewers that do not
# calculate, and pandas/openpyxl data_only, see numbers instead of blanks).
#   pwsh qos/tools/recalc_xlsx.ps1 -Path Bizboard_Product_Task_Universe_Master.xlsx [-Mirror Bizboard_Master_Task_Register_Enhanced.xlsx]
# Exits 1 if any formula evaluates to an error. Windows + desktop Excel only.
param(
    [Parameter(Mandatory = $true)][string]$Path,
    [string[]]$Mirror = @()
)
$full = (Resolve-Path $Path).Path
$tmp = Join-Path ([IO.Path]::GetTempPath()) ("recalc_" + [IO.Path]::GetFileName($full))
Copy-Item $full $tmp -Force
$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false; $xl.DisplayAlerts = $false
$errors = @()
try {
    $wb = $xl.Workbooks.Open($tmp)
    $xl.CalculateFull()
    foreach ($ws in $wb.Worksheets) {
        try {
            foreach ($c in $ws.UsedRange.SpecialCells(-4123).Cells) {
                if ($c.Text -like '#*') { $errors += "$($ws.Name)!$($c.Address($false,$false)) $($c.Text)" }
            }
        } catch { }
    }
    if ($errors.Count -eq 0) {
        $out = $tmp + ".saved.xlsx"
        $wb.SaveAs($out, 51)
        $wb.Close($false)
        Copy-Item $out $full -Force
        foreach ($m in $Mirror) { Copy-Item $out $m -Force }
        Remove-Item $out -ErrorAction SilentlyContinue
        Write-Output "recalculated $full, 0 formula errors"
    } else {
        $wb.Close($false)
        $errors | Select-Object -First 20 | ForEach-Object { Write-Output $_ }
        Write-Output "FAILED: $($errors.Count) formula errors, file not changed"
    }
} finally {
    $xl.Quit()
    Remove-Item $tmp -ErrorAction SilentlyContinue
}
if ($errors.Count -gt 0) { exit 1 }
