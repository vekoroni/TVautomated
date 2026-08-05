@echo off
cd /d C:\Users\ACKVerissimo\AVSHUNTER-Intelligence
C:\Python314\python.exe -u scripts\go_live_uat_audit_watch.py --interval 120 --duration-minutes 360 --stall-minutes 15 >> data\logs\go_live_uat_audit_watch_task.out.log 2>> data\logs\go_live_uat_audit_watch_task.err.log
