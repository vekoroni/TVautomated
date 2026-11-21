# Waits for today's POST_CLOSE macro build to finish COMPLETE, then starts the evening pipeline.
# Checks every 5 minutes; gives up at 02:00 UK without starting anything.
$repo = "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
$py   = Join-Path $repo "venv\Scripts\python.exe"
$chk  = Join-Path $repo "data\scratch\workaround\check_postclose_done.py"
$day  = "2026-11-19"
$giveUp = (Get-Date).Date.AddDays(1).AddHours(2)
while ($true) {
    $s = (& $py $chk $day | Select-Object -Last 1)
    Write-Host ("[{0:HH:mm}] post-close macro: {1}" -f (Get-Date), $s)
    if ($s -eq "COMPLETE") { break }
    if ((Get-Date) -ge $giveUp) { Write-Host "[STOPPED] No COMPLETE post-close build by 02:00: evening NOT started."; exit 1 }
    Start-Sleep -Seconds 300
}
Write-Host "[START] Post-close macro COMPLETE: starting the evening pipeline"
& (Join-Path $repo "run_evening_scheduled.ps1")
exit $LASTEXITCODE
