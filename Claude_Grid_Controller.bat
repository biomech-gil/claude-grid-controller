@echo off
start wt wsl bash /mnt/c/Users/SportScienceTeam/tmux-controller-start.sh
timeout /t 4 /nobreak >nul
start http://localhost:8080
