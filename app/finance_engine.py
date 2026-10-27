"""
carry.gg Finance & Accounting Division Engine (재무회계본부 핵심 재무 분석 엔진)
- Riot API 및 클라우드 인프라 TCO (총 소유 비용) 산출
- Google AdSense 광고 수익성 및 트래픽 기반 매출 모델링
- 월간 손익계산서(P&L), 영업이익률(Operating Margin), 손익분기점(BEP) 분석
"""

from typing import Dict, Any, List

def calculate_financial_summary(dau: int = 45000) -> Dict[str, Any]:
    """
    일일 활성 유저수(DAU) 기준 carry.gg 전사 재무 모델 및 월간 손익 계산
    """
    # 1. 트래픽 및 광고 노출 지표
    mau = int(dau * 5.8)  # DAU to MAU 승수 (~261,000 MAU)
    avg_pageviews_per_user = 6.4
    monthly_pageviews = int(mau * avg_pageviews_per_user)  # 약 1,670,400 PV
    ads_per_page = 2.5  # 상단 리더보드 + 인아티클 + 사이드 레일
    monthly_ad_impressions = int(monthly_pageviews * ads_per_page)  # 약 4,176,000 회

    # 2. 수익 모델 (Google AdSense)
    # 한국 롤/게임 카테고리 평균 eCPM: 약 1,750원 / 1,000회 노출
    ecpm_krw = 1750
    monthly_ad_revenue_krw = int((monthly_ad_impressions / 1000) * ecpm_krw)  # 약 7,308,000원

    # 3. 비용 모델 (OPEX - 월간 운영 인프라 비용)
    costs = {
        "cloud_server_compute": 480000,      # 고성능 CPU/RAM VPS 인스턴스 (FastAPI ASGI)
        "ssd_wal_storage": 120000,           # 고속 NVMe SQLite WAL 전적 DB 스토리지
        "cdn_bandwidth": 350000,             # DataDragon 챔피언 에셋 및 정적 파일 CDN 전송료
        "riot_api_service": 0,               # Riot Developer Portal 공식 키 (비상업적 연구/공식 승인 무료)
        "domain_ssl_security": 45000,        # 도메인 네임서버 및 엔터프라이즈 와일드카드 SSL 인증서
        "monitoring_discord_tg": 25000       # 텔레그램/디스코드 봇 호스팅 및 로그 감사 스토리지
    }
    monthly_infra_cost_krw = sum(costs.values())  # 1,020,000원

    # 4. 손익 및 재무 건전성 지표
    monthly_net_profit_krw = monthly_ad_revenue_krw - monthly_infra_cost_krw
    operating_margin_pct = round((monthly_net_profit_krw / monthly_ad_revenue_krw) * 100, 1) if monthly_ad_revenue_krw > 0 else 0.0

    # 손익분기점 (Break-Even Point MAU)
    # 유저 1인당 월간 광고 수익 = (6.4 PV * 2.5 ads * 1.75원) / 1000 = 약 28.0원
    rev_per_mau = (avg_pageviews_per_user * ads_per_page * ecpm_krw) / 1000.0
    bep_mau = int(monthly_infra_cost_krw / rev_per_mau) if rev_per_mau > 0 else 0

    return {
        "status": "ESTIMATE",
        "is_estimate": True,
        "basis_note": f"실측 매출이 아닌 가정치 기반 시뮬레이션 (DAU {dau:,}명, eCPM {ecpm_krw:,}원, 페이지당 광고 {ads_per_page}개 가정)",
        "currency": "KRW",
        "traffic_metrics": {
            "daily_active_users_dau": dau,
            "monthly_active_users_mau": mau,
            "avg_pageviews_per_visit": avg_pageviews_per_user,
            "monthly_total_pageviews": monthly_pageviews,
            "monthly_ad_impressions": monthly_ad_impressions
        },
        "revenue_breakdown": {
            "google_adsense_ecpm_krw": ecpm_krw,
            "monthly_ad_revenue_krw": monthly_ad_revenue_krw,
            "annualized_revenue_krw": monthly_ad_revenue_krw * 12
        },
        "cost_breakdown": {
            "items": costs,
            "monthly_infra_cost_krw": monthly_infra_cost_krw,
            "annualized_infra_cost_krw": monthly_infra_cost_krw * 12
        },
        "profitability": {
            "monthly_net_profit_krw": monthly_net_profit_krw,
            "annualized_net_profit_krw": monthly_net_profit_krw * 12,
            "operating_margin_pct": operating_margin_pct,
            "bep_monthly_active_users": bep_mau,
            "is_profitable": monthly_net_profit_krw > 0
        }
    }
