import sys, time
sys.path.insert(0, '.')
from app.spectator_engine import predict_lane_matchups

blue = [{'champ_name': '아트록스', 'champ_id': 'Aatrox'}, {'champ_name': '세주아니', 'champ_id': 'Sejuani'}, {'champ_name': '아지르', 'champ_id': 'Azir'}, {'champ_name': '카이사', 'champ_id': 'Kaisa'}, {'champ_name': '노틸러스', 'champ_id': 'Nautilus'}]
red = [{'champ_name': '크산테', 'champ_id': 'KSante'}, {'champ_name': '마오카이', 'champ_id': 'Maokai'}, {'champ_name': '오리아나', 'champ_id': 'Orianna'}, {'champ_name': '자야', 'champ_id': 'Xayah'}, {'champ_name': '라칸', 'champ_id': 'Rakan'}]

t0 = time.perf_counter()
res = predict_lane_matchups(blue, red)
t1 = time.perf_counter()
print(f'predict_lane_matchups time: {(t1-t0)*1000:.3f}ms')

t0 = time.perf_counter()
res2 = predict_lane_matchups(blue, red)
t1 = time.perf_counter()
print(f'predict_lane_matchups time (cached): {(t1-t0)*1000:.3f}ms')
print(f'Matchups count: {len(res2)}')
