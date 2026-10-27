#!/usr/bin/env python3
"""
Data Dragon 게임 데이터 갱신기

라이엇 공식 Data Dragon에서 최신 패치의 챔피언/아이템/소환사 주문/룬 데이터를 받아
app/data/ddragon/ 에 저장하고, 기존 코드가 읽는 app/champions.json, app/champion_full_data.json 도 갱신한다.

사용법:
    python scripts/update_game_data.py            # 최신 버전으로 갱신
    python scripts/update_game_data.py 16.20.1    # 특정 버전으로 갱신
갱신 후 서버를 재시작해야 반영된다.
"""
import json
import sys
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
OUT_DIR = APP_DIR / "data" / "ddragon"
CDN = "https://ddragon.leagueoflegends.com"
LOCALE = "ko_KR"


def fetch_json(client: httpx.Client, url: str):
    res = client.get(url, timeout=30.0)
    res.raise_for_status()
    return res.json()


def write_json(path: Path, data, pretty: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(data, ensure_ascii=False, indent=2) if pretty else json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    with httpx.Client(headers={"User-Agent": "carry.gg-data-updater"}) as client:
        version = sys.argv[1] if len(sys.argv) > 1 else fetch_json(client, f"{CDN}/api/versions.json")[0]
        print(f"Data Dragon 버전: {version}")
        base = f"{CDN}/cdn/{version}/data/{LOCALE}"

        champion = fetch_json(client, f"{base}/champion.json")
        champion_full = fetch_json(client, f"{base}/championFull.json")
        items = fetch_json(client, f"{base}/item.json")
        summoners = fetch_json(client, f"{base}/summoner.json")
        runes = fetch_json(client, f"{base}/runesReforged.json")

    write_json(OUT_DIR / "item.json", items)
    write_json(OUT_DIR / "summoner.json", summoners)
    write_json(OUT_DIR / "runesReforged.json", runes)

    # 기존 엔진이 읽는 간단 챔피언 목록 (id, key, name, title, image)
    champions = sorted(
        (
            {"id": c["id"], "key": c["key"], "name": c["name"], "title": c["title"], "image": c["image"]["full"]}
            for c in champion["data"].values()
        ),
        key=lambda c: c["name"],
    )
    write_json(APP_DIR / "champions.json", champions, pretty=True)
    write_json(APP_DIR / "champion_full_data.json", champion_full)

    # 버전 파일은 마지막에 기록 (중간 실패 시 이전 버전 정보 유지)
    write_json(OUT_DIR / "version.json", {"version": version, "locale": LOCALE})

    print(f"챔피언 {len(champions)}명, 아이템 {len(items['data'])}개, 소환사 주문 {len(summoners['data'])}개, 룬 계열 {len(runes)}개 저장 완료")
    print("서버를 재시작하면 새 데이터가 반영됩니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
