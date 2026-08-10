@echo off
title DramaDex Workbench server
echo Starting the workbench at http://localhost:8321/workbench.html
echo (The mic only works through this address, not by double-clicking the file.)
echo Keep this window open while you practice. Close it when done.
start http://localhost:8321/workbench.html
python -m http.server 8321 --directory "%~dp0"
