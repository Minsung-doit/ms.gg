"""
정식(Production) 키가 있어야 받을 수 있는 화면의 '샘플 데이터' (app/sample_data.py)

- 라이엇 추천 게임(Spectator-V5 featured-games)은 지금 키로 403이라 실제 목록을 받을 수 없다.
- 화면 모양을 보여주기 위해 생성 데이터를 쓰되, 실존 인물(프로·스트리머·소환사) 이름은 모두
  '샘플소환사N'으로 바꾸고 응답에 is_sample 표시를 단다. 화면은 이 표시가 있으면 샘플 배너를 띄운다.
- 정식 키를 받으면 이 모듈 대신 실제 API 응답으로 바꾼다. (목록: docs/PRODUCTION_KEY_SAMPLES.md)
"""
import copy
from typing import Any, Dict, List

SAMPLE_NOTICE = "샘플 데이터 (실제 게임 아님)"

_NAME_KEYS = ("game_name", "star_player", "star_title", "pro_name_kr", "pro_tag", "strm_tag")


def _collect_names(o: Any, names: List[str]) -> None:
    if isinstance(o, dict):
        for k, v in o.items():
            if k in _NAME_KEYS and isinstance(v, str) and v.strip() and v not in names:
                names.append(v)
            elif k == "riot_id" and isinstance(v, str) and "#" in v:
                n = v.split("#", 1)[0]
                if n.strip() and n not in names:
                    names.append(n)
            else:
                _collect_names(v, names)
    elif isinstance(o, list):
        for v in o:
            _collect_names(v, names)


def _replace(o: Any, mapping: Dict[str, str]) -> Any:
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            if k in ("tag_line", "star_tag"):
                out[k] = "SAMPLE"
            elif k in ("pro_tag", "strm_tag"):
                out[k] = None
            elif k in ("is_pro", "is_strm"):
                out[k] = False
            elif k == "team":
                out[k] = ""
            elif k == "is_live_riot_api":
                out[k] = False
            elif k.startswith("champ") or k.endswith(("image", "img", "icon")):
                # 챔피언 이름·이미지는 그대로 (프로 닉네임과 같은 챔피언 이름, 예: Karma 가 바뀌면 이미지가 깨진다)
                out[k] = v
            else:
                out[k] = _replace(v, mapping)
        return out
    if isinstance(o, list):
        return [_replace(v, mapping) for v in o]
    if isinstance(o, str):
        # 긴 이름부터 바꿔야 부분 일치로 깨지지 않는다
        for real in sorted(mapping, key=len, reverse=True):
            if real in o:
                o = o.replace(real, mapping[real])
        return o
    return o


def anonymize_featured(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """생성된 추천 게임에서 실존 인물 이름을 모두 샘플 이름으로 바꾸고 샘플 표시를 단다."""
    names: List[str] = []
    _collect_names(matches, names)
    mapping = {n: f"샘플소환사{i + 1}" for i, n in enumerate(names)}
    out = _replace(copy.deepcopy(matches), mapping)
    for i, m in enumerate(out):
        m["is_sample"] = True
        m["sample_notice"] = SAMPLE_NOTICE
        # 제목·설명 문구에는 팀명·인물명이 섞여 있어 챔피언 이름으로 새로 만든다
        blue = (m.get("blue_team") or [{}])[0].get("champ_name") or "블루팀"
        red = (m.get("red_team") or [{}])[0].get("champ_name") or "레드팀"
        m["headline"] = f"샘플 경기 {i + 1}: {blue} vs {red}"
        m["star_title"] = m.get("star_player", "")
        for team in ("blue_team", "red_team"):
            for p in m.get(team) or []:
                p["riot_id"] = f"{p.get('game_name', '')}#SAMPLE"
        _set_key(m, "headline", m["headline"])
    return out


def _set_key(o: Any, key: str, value: Any) -> None:
    if isinstance(o, dict):
        for k in o:
            if k == key:
                o[k] = value
            else:
                _set_key(o[k], key, value)
    elif isinstance(o, list):
        for v in o:
            _set_key(v, key, value)
