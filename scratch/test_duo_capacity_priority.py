import sys
import os
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.duo_finder_engine import get_duo_posts, is_room_full, toggle_duo_post_capacity

def test_duo_capacity_priority():
    print("======================================================================")
    print("🔍 [TEST] Duo Room Capacity Priority & Re-ordering Verification")
    print("======================================================================")

    # 1. 초기 전체 목록 조회
    posts = get_duo_posts(position="ALL", queue_type="ALL", tier="ALL", voice="ALL")
    assert len(posts) > 0, "Duo posts list must not be empty"

    open_posts = [p for p in posts if not is_room_full(p)]
    full_posts = [p for p in posts if is_room_full(p)]
    print(f"Total Posts: {len(posts)} | Open (미달): {len(open_posts)} | Full (마감/초과): {len(full_posts)}")

    # 검증 1: 피드 상단은 반드시 미달 방, 하단은 마감 방이어야 함
    first_full_idx = None
    for idx, p in enumerate(posts):
        if is_room_full(p):
            first_full_idx = idx
            break

    if first_full_idx is not None:
        for idx in range(first_full_idx, len(posts)):
            assert is_room_full(posts[idx]), f"Post at index {idx} should be full, but found open room: {posts[idx]}"
        print(f"✅ TC-DUO-01 통과: 0번부터 {first_full_idx-1}번까지 정원 미달 방 상단 노출, {first_full_idx}번부터 최하단까지 정원 초과 방 격리 확인!")
    else:
        print("모든 방이 정원 미달 상태입니다.")

    # 2. 토글 테스트 (TC-DUO-02)
    target_post = open_posts[0]
    target_id = target_post["id"]
    print(f"\nTarget Post ID {target_id} (Initial: Open) -> Toggling to Full...")
    toggled = toggle_duo_post_capacity(target_id)
    assert toggled is not None, "Toggled post should not be None"
    assert is_room_full(toggled), f"Post {target_id} should now be full"

    # 목록 재조회 후 위치 확인
    new_posts = get_duo_posts(position="ALL", queue_type="ALL", tier="ALL", voice="ALL")
    new_toggled_post = next(p for p in new_posts if p["id"] == target_id)
    new_idx = new_posts.index(new_toggled_post)
    print(f"Post {target_id} new position in feed: index {new_idx} (Total: {len(new_posts)})")
    assert new_idx >= len(open_posts) - 1, f"Toggled full post should move to bottom section, but was at {new_idx}"
    print(f"✅ TC-DUO-02-1 통과: 마감 토글 시 하단 영역으로 즉각 자동 이동 확인!")

    # 다시 미달로 복구 토글
    print(f"\nRe-toggling Post ID {target_id} back to Open...")
    re_toggled = toggle_duo_post_capacity(target_id)
    assert not is_room_full(re_toggled), f"Post {target_id} should now be open"
    re_posts = get_duo_posts(position="ALL", queue_type="ALL", tier="ALL", voice="ALL")
    re_idx = re_posts.index(next(p for p in re_posts if p["id"] == target_id))
    print(f"Post {target_id} re-opened position in feed: index {re_idx}")
    assert re_idx < len(open_posts), f"Re-opened post should move back to top section, but was at {re_idx}"
    print(f"✅ TC-DUO-02-2 통과: 재오픈 토글 시 상단 영역으로 즉각 승격 확인!")

    # 3. 다중 필터 적용 시 정렬 불변성 (TC-DUO-03)
    print("\n[TC-DUO-03] Testing multi-filters (MID, 솔로랭크, ON)...")
    filtered = get_duo_posts(position="MID", queue_type="솔로랭크", voice="ON")
    filtered_open = [p for p in filtered if not is_room_full(p)]
    filtered_full = [p for p in filtered if is_room_full(p)]
    print(f"Filtered Posts: {len(filtered)} (Open: {len(filtered_open)}, Full: {len(filtered_full)})")
    for idx in range(len(filtered_open)):
        assert not is_room_full(filtered[idx]), f"Filtered index {idx} must be open"
    for idx in range(len(filtered_open), len(filtered)):
        assert is_room_full(filtered[idx]), f"Filtered index {idx} must be full"
    print("✅ TC-DUO-03 통과: 다중 필터 적용 시에도 정원 미달 상단 ➔ 정원 초과 하단 정렬 불변성 100% 보장!")

    print("\n======================================================================")
    print("🏆 ALL DUO CAPACITY VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("======================================================================")

if __name__ == "__main__":
    test_duo_capacity_priority()
