#!/usr/bin/env python3
"""
carry.gg 통합 테스트 러너

기본 스위트는 라이엇 실데이터 기능·보안·운영 기능만 검증한다.
생성(난수) 데이터 기능 테스트는 tests/legacy_synthetic/ 로 옮겨 기본 실행에서 제외했다.
"""

import os
import sys
import time
import subprocess
from pathlib import Path
from typing import List, Dict, Any

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).resolve().parent.parent
SUITE_TIMEOUT_SEC = 300

TEST_SUITES = [
    {
        "id": 1,
        "name": "DOM 계층 및 탭 무결성 검증",
        "script": "scripts/validate_dom_integrity.py",
        "description": "index.html <body> 직계 자식 구조, 탭 누락/중첩 0건, Admin 버튼 비노출 검증"
    },
    {
        "id": 2,
        "name": "라이엇 실데이터 계층 검증",
        "script": "test_real_data.py",
        "description": "Match-V5/Spectator-V5/League-V4 픽스처 변환, 키 없음 시 데이터 미생성, 매치 캐시, 생성 기능 차단"
    },
    {
        "id": 3,
        "name": "Admin 격리 및 탭 엔드포인트 상태 코드 검증",
        "script": "test_admin_and_tab_endpoints.py",
        "description": "실데이터 기능은 200/404/503, 생성 데이터 기능은 503으로 응답하는지 검증"
    },
    {
        "id": 4,
        "name": "디스코드(Discord) 연계 및 웹후크 엔드포인트 검증",
        "script": "test_discord_integration.py",
        "description": "웹후크 상태/등록, 마스킹 보안, 전적 공유 마크다운, 듀오 구인글 알림 (네트워크 호출은 가짜로 대체)"
    },
    {
        "id": 5,
        "name": "텔레그램(Telegram) CLI 브리지 & 재무(추정치) 검증",
        "script": "test_telegram_and_finance.py",
        "description": "텔레그램 설정·메시지 포맷, 재무 추정치 API (관리자 전용)"
    },
    {
        "id": 6,
        "name": "보안 회귀 검증 (관리자 인증·XSS·도배·권한)",
        "script": "test_security_regressions.py",
        "description": "2026-10-24 보안 감사에서 발견된 공격 시나리오가 실제로 차단되는지 재현 검증"
    },
    {
        "id": 7,
        "name": "분석 엔진 회귀 검증 (관전 스크립트·듀오·스킬·공유 카드)",
        "script": "test_analytics_engines.py",
        "description": "SYNTHETIC_FEATURES=0에서도 열려 있는 엔진이 가짜 값을 만들지 않는지 검증"
    },
    {
        "id": 8,
        "name": "티어표·상성용 매치 수집기 검증",
        "script": "test_match_collector.py",
        "description": "압축 저장, 수집 주기, 속도 제한, 시드 관리, 백그라운드 루프, 관리자 상태 API 검증"
    },
    {
        "id": 9,
        "name": "수집 매치 기반 챔피언 티어표 검증",
        "script": "test_champion_stats.py",
        "description": "수집된 솔로랭크 매치 기반 승률·픽률·밴률, 티어 산정, 최소 표본 제외, 엔드포인트 응답 검증"
    }
]

def run_suite(suite: Dict[str, Any]) -> Dict[str, Any]:
    script_path = BASE_DIR / suite["script"]
    print("=" * 85)
    print(f"▶ [스위트 {suite['id']}/{len(TEST_SUITES)}] {suite['name']}")
    print(f"  • 스크립트: {suite['script']}")
    print(f"  • 검증 내용: {suite['description']}")
    print("-" * 85)

    if not script_path.exists():
        print(f"❌ [FAIL] 스크립트 파일이 존재하지 않습니다: {script_path}")
        return {
            "id": suite["id"],
            "name": suite["name"],
            "script": suite["script"],
            "passed": False,
            "duration": 0.0,
            "error": "File not found"
        }

    env = os.environ.copy()
    env["PYTHONPATH"] = str(BASE_DIR)
    env["PYTHONIOENCODING"] = "utf-8"

    # 테스트는 assert 로 실패를 알린다. PYTHONOPTIMIZE 가 설정돼 있으면 assert 가 사라져
    # 실패해도 종료 코드 0(PASS)이 되므로 제거한다.
    env.pop("PYTHONOPTIMIZE", None)

    start_time = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=SUITE_TIMEOUT_SEC
        )
    except subprocess.TimeoutExpired as e:
        # 멈춘 스위트는 실패로 처리 (러너 전체가 무한 대기하지 않도록)
        out = e.stdout or ""
        err = e.stderr or ""
        proc = subprocess.CompletedProcess(
            e.cmd, returncode=124,
            stdout=out.decode("utf-8", "replace") if isinstance(out, bytes) else out,
            stderr=(err.decode("utf-8", "replace") if isinstance(err, bytes) else err)
                   + f"\n시간 초과: {SUITE_TIMEOUT_SEC}초 안에 끝나지 않았습니다."
        )
    duration = time.perf_counter() - start_time
    passed = (proc.returncode == 0)

    # 출력 요약 (20줄 이하면 전부, 넘으면 앞 15줄 + 뒤 5줄)
    stdout_lines = proc.stdout.strip().splitlines()
    if len(stdout_lines) <= 20:
        for line in stdout_lines:
            print(f"   {line}")
    else:
        for line in stdout_lines[:15]:
            print(f"   {line}")
        print(f"   ... ({len(stdout_lines) - 20}줄 생략) ...")
        for line in stdout_lines[-5:]:
            print(f"   {line}")

    if not passed:
        print("\n❌ [STDERR 오류 출력]")
        stderr_lines = proc.stderr.strip().splitlines()
        for eline in stderr_lines[-20:]:
            print(f"   ! {eline}")

    status_str = "✅ PASS" if passed else "❌ FAIL"
    print(f"\n👉 판정: {status_str} (소요 시간: {duration:.2f}초)")
    print("=" * 85 + "\n")

    return {
        "id": suite["id"],
        "name": suite["name"],
        "script": suite["script"],
        "passed": passed,
        "duration": duration,
        "stdout": proc.stdout,
        "stderr": proc.stderr
    }

def main():
    total_start = time.perf_counter()
    print("\n" + "#" * 85)
    print("🚀 carry.gg 통합 자동화 테스트 마스터 러너 (Continuous Verifier Specialist)")
    print(f"   실행 일시: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   실행 환경: Python {sys.version.split()[0]} on {sys.platform}")
    print(f"   작업 디렉토리: {BASE_DIR}")
    print("#" * 85 + "\n")

    results: List[Dict[str, Any]] = []

    for suite in TEST_SUITES:
        res = run_suite(suite)
        results.append(res)

    total_duration = time.perf_counter() - total_start
    all_passed = all(r["passed"] for r in results)
    pass_count = sum(1 for r in results if r["passed"])
    total_count = len(results)
    pass_rate = (pass_count / total_count) * 100.0

    # 종합 리포트 테이블
    print("\n" + "=" * 85)
    print("📊 [종합 검증 성적표: Integrated Test Verification Summary]")
    print("=" * 85)
    print(f"{'No.':<4} | {'검증 스위트 명':<44} | {'소요 시간':<10} | {'결과'}")
    print("-" * 85)
    for r in results:
        status_text = "✅ PASS" if r["passed"] else "❌ FAIL"
        dur_text = f"{r['duration']:.2f}s"
        name_trunc = r["name"][:42]
        print(f"{r['id']:<4} | {name_trunc:<42} | {dur_text:<10} | {status_text}")
    print("-" * 85)
    print(f"총 소요 시간: {total_duration:.2f}초 | 검증 스위트: {pass_count}/{total_count} 합격 ({pass_rate:.1f}%)")
    print("=" * 85)

    if all_passed:
        print(f"\n결과: 위 {total_count}개 스위트 통과. (테스트가 다루지 않는 부분의 무결성을 뜻하지는 않습니다)\n")
        sys.exit(0)
    else:
        print(f"\n결과: {total_count - pass_count}개 스위트 실패. 위 로그를 확인하세요.\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
