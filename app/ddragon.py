"""
Data Dragon 정적 게임 데이터 단일 진입점

버전과 데이터는 scripts/update_game_data.py 가 app/data/ddragon/ 에 저장한 파일에서 읽는다.
이미지 URL은 하드코딩하지 말고 이 모듈의 함수/상수를 사용할 것.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

DATA_DIR = Path(__file__).resolve().parent / "data" / "ddragon"
FALLBACK_VERSION = "16.21.1"
CDN_ROOT = "https://ddragon.leagueoflegends.com/cdn"


def _load(name: str) -> Any:
    path = DATA_DIR / name
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


DDRAGON_VERSION: str = (_load("version.json") or {}).get("version", FALLBACK_VERSION)
DDRAGON_CDN: str = f"{CDN_ROOT}/{DDRAGON_VERSION}"
PERK_IMG_ROOT: str = f"{CDN_ROOT}/img/"

_ITEMS: Dict[str, Any] = (_load("item.json") or {}).get("data", {})
_SPELLS_BY_KEY: Dict[int, Dict[str, Any]] = {
    int(s["key"]): s for s in ((_load("summoner.json") or {}).get("data", {}) or {}).values()
}
_RUNE_STYLES: Dict[int, Dict[str, Any]] = {}
_RUNES: Dict[int, Dict[str, Any]] = {}
for _style in _load("runesReforged.json") or []:
    _RUNE_STYLES[_style["id"]] = _style
    for _slot in _style.get("slots", []):
        for _rune in _slot.get("runes", []):
            _RUNES[_rune["id"]] = {**_rune, "style_id": _style["id"]}


def champion_img(image_file: str) -> str:
    """'Ahri.png' 또는 'Ahri' -> 챔피언 정사각 아이콘 URL"""
    name = image_file if image_file.endswith(".png") else f"{image_file}.png"
    return f"{DDRAGON_CDN}/img/champion/{name}"


def item_img(item_id: int) -> str:
    return f"{DDRAGON_CDN}/img/item/{item_id}.png"


def profile_icon(icon_id: int) -> str:
    return f"{DDRAGON_CDN}/img/profileicon/{icon_id}.png"


def item_info(item_id: int) -> Optional[Dict[str, Any]]:
    item = _ITEMS.get(str(item_id))
    if not item:
        return None
    return {"id": item_id, "name": item.get("name", ""), "icon": item_img(item_id)}


def spell_info(spell_key: int) -> Dict[str, Any]:
    spell = _SPELLS_BY_KEY.get(int(spell_key or 0))
    if not spell:
        return {"id": spell_key, "name": "", "icon": ""}
    return {"id": spell_key, "name": spell["name"], "icon": f"{DDRAGON_CDN}/img/spell/{spell['image']['full']}"}


def rune_info(perk_id: int) -> Dict[str, Any]:
    rune = _RUNES.get(int(perk_id or 0))
    if not rune:
        return {"id": perk_id, "name": "", "icon": "", "style_id": None}
    return {"id": perk_id, "name": rune["name"], "icon": PERK_IMG_ROOT + rune["icon"], "style_id": rune["style_id"]}


def rune_tree(style_id: int, selected: Any, skip_keystone: bool = False) -> List[List[Dict[str, Any]]]:
    """룬 트리 전체(줄마다 룬 목록)와 선택 여부. 보조 트리는 핵심 룬 줄을 뺀다."""
    style = _RUNE_STYLES.get(int(style_id or 0))
    if not style:
        return []
    chosen = {int(x) for x in selected or []}
    slots = style.get("slots", [])[1 if skip_keystone else 0:]
    return [[{"id": r["id"], "name": r["name"], "icon": PERK_IMG_ROOT + r["icon"], "on": r["id"] in chosen}
             for r in slot.get("runes", [])] for slot in slots]


def rune_style_info(style_id: int) -> Dict[str, Any]:
    style = _RUNE_STYLES.get(int(style_id or 0))
    if not style:
        return {"id": style_id, "name": "", "name_en": "", "icon": ""}
    return {"id": style_id, "name": style["name"], "name_en": style["key"], "icon": PERK_IMG_ROOT + style["icon"]}
