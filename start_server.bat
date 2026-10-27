@echo off
chcp 65001 > nul
title carry.gg 전적 검색 서버
echo ==================================================
echo [carry.gg] 전적 검색 로컬 서버를 실행합니다...
echo 브라우저 접속 주소: http://localhost:3000
echo 종료하려면 창을 닫거나 Ctrl+C를 누르세요.
echo ==================================================
python run.py
pause
