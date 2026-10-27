@echo off
chcp 65001 > nul
echo ======================================================================
echo [carry.gg] 통합 테스트 실행 (scripts\run_all_tests.py)
echo ======================================================================
echo 실행 중입니다. 잠시 기다려 주세요...

cd /d "%~dp0"
if not exist logs mkdir logs
python -X utf8 scripts\run_all_tests.py > logs\run_all_tests.log 2>&1
set TEST_EXIT=%ERRORLEVEL%

echo.
echo ======================================================================
if "%TEST_EXIT%"=="0" (echo [통과] 모든 테스트 스위트가 통과했습니다.) else (echo [실패] 실패한 테스트가 있습니다. 종료 코드: %TEST_EXIT%)
echo 전체 로그: logs\run_all_tests.log
echo ======================================================================
pause
