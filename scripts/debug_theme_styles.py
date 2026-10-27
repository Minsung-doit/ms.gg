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
            
            print("=== DARK MODE STYLES ===")
            print('navbar-top bg:', await eval_js("window.getComputedStyle(document.querySelector('.navbar-top')).backgroundColor"))
            print('navbar-bottom bg:', await eval_js("window.getComputedStyle(document.querySelector('.navbar-bottom, .nav-tabs')).backgroundColor"))
            print('brand-title color:', await eval_js("window.getComputedStyle(document.querySelector('.brand-title')).color"))
            print('nav-tab color:', await eval_js("window.getComputedStyle(document.querySelector('.nav-tab:not(.active)')).color"))

            # Toggle to light mode
            await eval_js("document.getElementById('btnThemeToggle').click()")
            await asyncio.sleep(0.5)

            print("\n=== LIGHT MODE STYLES ===")
            print('data-theme:', await eval_js("document.documentElement.getAttribute('data-theme')"))
            print('navbar-top bg:', await eval_js("window.getComputedStyle(document.querySelector('.navbar-top')).backgroundColor"))
            print('navbar-bottom bg:', await eval_js("window.getComputedStyle(document.querySelector('.navbar-bottom, .nav-tabs')).backgroundColor"))
            print('brand-title color:', await eval_js("window.getComputedStyle(document.querySelector('.brand-title')).color"))
            print('nav-tab (inactive) color:', await eval_js("window.getComputedStyle(document.querySelector('.nav-tab:not(.active)')).color"))
            print('body bg:', await eval_js("window.getComputedStyle(document.body).backgroundColor"))
            print('btnThemeToggle color:', await eval_js("window.getComputedStyle(document.getElementById('btnThemeToggle')).color"))
            print('btnThemeToggle bg:', await eval_js("window.getComputedStyle(document.getElementById('btnThemeToggle')).backgroundColor"))
    finally:
        proc.kill()

asyncio.run(run())
