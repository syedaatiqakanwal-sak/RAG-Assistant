@echo off
netsh advfirewall firewall add rule name="Zeviq RAG 8001" dir=in action=allow protocol=TCP localport=8001
pause
