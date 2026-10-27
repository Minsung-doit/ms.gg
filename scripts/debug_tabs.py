import asyncio
import websockets
import urllib.request
import json
import subprocess
import time
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

async def run():
    proc = subprocess.Popen([
        r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        '--headless=new',
        '--remote-debugging-port=9222',
        '--disable-gpu',
        '--no-sandbox',
        'http://localhost:3000/'
    ])
    time.sleep(3)
    try:
        targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json').read().decode())
        target = next(t for t in targets if t.get('type') == 'page')
        async with websockets.connect(target['webSocketDebuggerUrl']) as ws:
            async def eval_js(expr):
                await ws.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate', 'params': {'expression': expr, 'returnByValue': True, 'awaitPromise': True}}))
                while True:
                    m = json.loads(await ws.recv())
                    if m.get('id') == 1:
                        return m.get('result', {}).get('result', {}).get('value')
            
            print('Initial active tab:', await eval_js("document.querySelector('.nav-tab.active')?.getAttribute('data-tab')"))
            print('Calling window.switchMainTab("leaderboard")...')
            await eval_js("window.switchMainTab('leaderboard')")
            await asyncio.sleep(2)
            
            print('viewLeaderboard display:', await eval_js("window.getComputedStyle(document.getElementById('viewLeaderboard')).display"))
            print('leaderboardBody html len:', await eval_js("document.getElementById('leaderboardBody')?.innerHTML.length"))
            print('lb-tier-cell outerHTML:', await eval_js("document.querySelector('.lb-tier-cell')?.outerHTML"))
            print('tier-emblem-img outerHTML:', await eval_js("document.querySelector('.tier-emblem-img')?.outerHTML"))
            print('tier-emblem-img computed display:', await eval_js("window.getComputedStyle(document.querySelector('.tier-emblem-img')).display"))
            print('tier-emblem-img naturalWidth:', await eval_js("document.querySelector('.tier-emblem-img')?.naturalWidth"))
            print('window._tabLoaders keys:', await eval_js("Object.keys(window._tabLoaders)"))
            print('typeof window.loadLeaderboard:', await eval_js("typeof window.loadLeaderboard"))
            print('typeof loadLeaderboard:', await eval_js("typeof loadLeaderboard"))
    finally:
        proc.kill()

asyncio.run(run())
