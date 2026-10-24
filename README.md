# ms.gg

A small, non-commercial Korean-language League of Legends summoner lookup site
for me and a few friends. Not public.

## Features
- Riot ID search: current Solo/Flex rank (League-V4)
- Recent matches: champion, KDA, items, runes, spells, team composition (Match-V5)
- Live game view (Spectator-V5)
- Korean Challenger ladder (League-V4, Account-V1)

## Riot API usage
- Match details are cached locally so each match is requested only once
- Ladder refresh: at most once per 5 minutes
- Per-user refreshes are rate limited
- All statistics come only from Riot API data
