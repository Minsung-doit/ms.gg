import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent.parent
index_html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
style_css = (ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")
app_js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")

errors = []

print("=" * 70)
print("🔍 [carry.gg Admin Separation & Stealth Verification]")
print("=" * 70)

# 1. Check stealth elements
hidden_elements = [
    "btnOpenApiKeyModal",
    "apiExpiryBanner",
    "headerSyncIndicator",
    "syncDashboardPopover",
    "btnSyncRealLadder",
    "btnSpecPathSettings",
    "expiryFloatingToast"
]

print("\n1. Hidden/Stealth Elements Inspection:")
for el in hidden_elements:
    in_html = el in index_html
    in_css = f"#{el}" in style_css
    if not in_html:
        errors.append(f"Element #{el} not found in index.html")
    if not in_css:
        errors.append(f"CSS hiding rule #{el} not found in style.css")
    print(f"  - #{el:25} -> HTML: {'OK' if in_html else 'FAIL'} | CSS Hidden: {'OK' if in_css else 'FAIL'}")

# 2. Check Admin Hub controls
admin_controls = [
    "adminHubModal",
    "adminApiKeyInput",
    "btnAdminSaveApiKey",
    "btnAdminTestApiKey",
    "btnAdminSyncLadder",
    "btnAdminRefreshStats",
    "btnAdminFlushCache",
    "adminLolPathInput",
    "btnAdminSaveLolPath",
    "btnAdminResetLolPath",
    "btnCloseAdminHub"
]

print("\n2. Admin & Operations Hub Controls Inspection:")
for ctrl in admin_controls:
    in_html = ctrl in index_html
    if not in_html:
        errors.append(f"Admin control #{ctrl} missing from index.html")
    print(f"  - #{ctrl:25} -> Present in HTML: {'OK' if in_html else 'FAIL'}")

# 3. Check Triggers & Functions in app.js
js_requirements = [
    ("initAdminOperationsHub", "Admin Hub Initializer Module"),
    ("openAdminHub", "openAdminHub function"),
    ("closeAdminHub", "closeAdminHub function"),
    ("toggleAdminHub", "toggleAdminHub function"),
    ("ctrlKey && e.shiftKey", "Ctrl + Shift + A Keydown Listener"),
    ("adminParam", "URL ?admin=1 / ?admin=true Query Listener"),
    ("openLolPathModal()", "Spectator Modal Mini Gear Shortcut"),
    ("/api/settings/api-key", "API Key Update Endpoint Call"),
    ("/api/leaderboard/sync", "Leaderboard Sync Endpoint Call"),
    ("/api/cache/clear", "Cache Clear Endpoint Call"),
    ("/api/cache/stats", "Cache Stats Endpoint Call"),
    ("/api/system/metrics", "System Metrics Endpoint Call")
]

print("\n3. JS Trigger & Interaction Logic Inspection:")
for req, desc in js_requirements:
    found = req in app_js
    if not found:
        errors.append(f"Required JS pattern '{req}' ({desc}) missing from app.js")
    print(f"  - {desc:40} -> Found: {'OK' if found else 'FAIL'}")

# 4. Check HTML comments
import re
comments = re.findall(r'<!--(?!\s*Pretendard).*?-->', index_html, flags=re.DOTALL)
print("\n4. Temporary Development Comments Inspection:")
print(f"  - Remaining non-Pretendard HTML comments: {len(comments)}")
if comments:
    for c in comments:
        errors.append(f"Unwanted comment found: {c.strip()[:60]}")

print("=" * 70)
if errors:
    print(f"❌ Verification Failed with {len(errors)} errors:")
    for err in errors:
        print(f"   - {err}")
    sys.exit(1)
else:
    print("✅ All Admin Separation & Stealth checks PASSED successfully!")
print("=" * 70)
