import requests
import time
import json
import os
import re
from datetime import datetime, timedelta

# ===================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID   = os.environ.get("CHAT_ID", "")
INTERVAL  = 900
SAVE_FILE = "seen.json"
CF_BASE   = "https://d6d2sg7as7xll.cloudfront.net"
# ===================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 12; Redmi) "
                  "AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36"
}

APP_MAP = {
    "wypay168.com":         ("wy",    503),
    "jpgpay.top":           ("jpg",   103),
    "okpay365.win":         ("ok",    104),
    "comeappdown.com":      ("come",  121),
    "dd-pay.net":           ("dd",    130),
    "diwadown.net":         ("diwa",  165),
    "wynnpay24.com":        ("wynn",  105),
    "dowapp.uday.ink":      ("nova",  103),
    "install.vlinkapp.net": ("link",  126),
    "dowapp.ffcpay.ink":    ("ffc",   105),
    "qqvip.beer":           ("qq",    106),
    "kkdow.com":            ("kk",    100),
    "miodow.link":          ("mio",   100),
    "bittaro.net":          ("658",   100),
    "neoappdow.com":        ("neo",   103),
    "install.r7vpd3.com":   ("zoro",  122),
    "install.ktkpay.cc":    ("ktk",   106),
    "dtdow.link":           ("dt",    106),
    "alphad.net":           ("alpha", 100),
    "one-pay.ink":          ("one",   100),
    "shaktipay.app":        ("shakti",100),
}

CRT_KEYWORDS = [
    "tailpay","diwapay","diwacore","nexways",
    "etnanets","tailshaofu","dtpay","dtdow",
    "qqvip","kkdow","miodow","bittaro","wypay",
    "jpgpay","okpay","comeapp","wynnpay"
]

GITHUB_USERS  = ["tailshaofu005-cmd","tailpaytech"]
GITHUB_SEARCH = ["tailshaofu apk","tailpay payment","diwapay release"]

# ===================================================
# UTILITIES
# ===================================================

def send(msg):
    """Telegram pe message bhejo"""
    print(f"[SEND] Attempting... chat={CHAT_ID[:6]}...")
    try:
        if not BOT_TOKEN or not CHAT_ID:
            print("[SEND ERROR] BOT_TOKEN ya CHAT_ID missing!")
            return
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id":    CHAT_ID,
                "text":       msg,
                "parse_mode": "HTML"
            },
            timeout=15
        )
        if r.status_code == 200:
            print(f"[SEND] OK — message_id: {r.json().get('result',{}).get('message_id')}")
        else:
            print(f"[SEND ERROR] {r.status_code}: {r.text[:150]}")
    except Exception as e:
        print(f"[SEND EXCEPTION] {e}")

def load_data():
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE) as f:
            d = json.load(f)
            if "seen_keys" not in d:
                d["seen_keys"] = []
            if "app_versions" not in d:
                d["app_versions"] = {}
            return d
    return {"seen_keys": [], "app_versions": {}}

def save_data(d):
    with open(SAVE_FILE, 'w') as f:
        json.dump(d, f, indent=2)

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

# ===================================================
# MODULE 1 — CLOUDFRONT TRACKER
# ===================================================

def cf_check(app, ver):
    url = f"{CF_BASE}/{app}/{app}{ver}/app.apk"
    try:
        r = requests.head(url, headers=HEADERS, timeout=8)
        if r.status_code == 200:
            size = int(r.headers.get('Content-Length', 0))
            return url, size
    except:
        pass
    return None, None

def check_cloudfront(data):
    findings = []
    seen     = set(data["seen_keys"])
    versions = data["app_versions"]

    # Known apps — version update check
    for domain, (app, base_ver) in APP_MAP.items():
        cur = versions.get(app, base_ver)
        for ver in range(cur, cur + 15):
            key = f"cf:{app}{ver}"
            if key in seen:
                continue
            url, size = cf_check(app, ver)
            if url:
                seen.add(key)
                mb = round(size/1024/1024, 1) if size else 0
                if ver > cur:
                    old = versions.get(app, base_ver)
                    versions[app] = ver
                    findings.append({
                        "type":"cf_update","app":app.upper(),
                        "domain":domain,"old":old,"new":ver,
                        "url":url,"mb":mb
                    })
                    log(f"  [UPDATE] {app} v{old}→v{ver}")
                else:
                    versions[app] = ver
                    findings.append({
                        "type":"cf_found","app":app.upper(),
                        "ver":ver,"url":url,"mb":mb
                    })
            time.sleep(0.2)

    # New unknown apps scan
    extra = [
        "star","gold","win","top","ace","pro","max",
        "flash","super","mega","tiger","lion","eagle",
        "wolf","king","cash","coin","rupee","gpay",
        "epay","xpay","zpay","pay2","pay3","wallet",
        "swift","speed","quick","rapid","turbo"
    ]
    known = {v[0] for v in APP_MAP.values()}
    for app in extra:
        if app in known or app in versions:
            continue
        for ver in range(100, 115):
            key = f"cf:{app}{ver}"
            if key in seen:
                break
            url, size = cf_check(app, ver)
            if url:
                seen.add(key)
                mb = round(size/1024/1024,1) if size else 0
                versions[app] = ver
                findings.append({
                    "type":"cf_new","app":app.upper(),
                    "ver":ver,"url":url,"mb":mb
                })
                log(f"  [NEW APP] {app} v{ver}")
                break
        time.sleep(0.15)

    data["seen_keys"]    = list(seen)
    data["app_versions"] = versions
    return findings

# ===================================================
# MODULE 2 — DOMAIN DIRECT CHECK
# ===================================================

def check_domains(data):
    findings = []
    seen     = set(data["seen_keys"])

    for domain, (app, _) in APP_MAP.items():
        try:
            r = requests.get(
                f"https://{domain}",
                headers=HEADERS,
                timeout=10,
                allow_redirects=True
            )
            if r.status_code not in [200,201]:
                continue
            apk_links = re.findall(r'https?://[^\s"\'<>]+\.apk', r.text)
            for link in apk_links:
                key = f"dom:{link}"
                if key in seen:
                    continue
                seen.add(key)
                findings.append({
                    "type":"domain_apk","app":app.upper(),
                    "domain":domain,"url":link
                })
                log(f"  [DOM APK] {domain}")
        except:
            pass
        time.sleep(0.3)

    data["seen_keys"] = list(seen)
    return findings

# ===================================================
# MODULE 3 — SSL CERTIFICATE
# ===================================================

def check_ssl(data):
    findings = []
    seen     = set(data["seen_keys"])
    since    = datetime.now() - timedelta(hours=24)

    for kw in CRT_KEYWORDS:
        try:
            r = requests.get(
                f"https://crt.sh/?q=%25{kw}%25&output=json",
                timeout=20
            )
            if r.status_code != 200:
                continue
            for cert in r.json():
                domain = cert.get('name_value','').strip()
                date_s = cert.get('not_before','')
                if not domain or domain.startswith('*'):
                    continue
                key = f"ssl:{domain}"
                if key in seen:
                    continue
                try:
                    d = datetime.strptime(date_s[:10],'%Y-%m-%d')
                    if d >= since:
                        seen.add(key)
                        findings.append({
                            "type":"ssl","domain":domain,
                            "date":date_s[:10],"kw":kw
                        })
                        log(f"  [SSL] {domain}")
                except:
                    pass
        except Exception as e:
            log(f"  crt.sh err ({kw}): {e}")
        time.sleep(1)

    data["seen_keys"] = list(seen)
    return findings

# ===================================================
# MODULE 4 — GITHUB
# ===================================================

def check_github(data):
    findings = []
    seen     = set(data["seen_keys"])
    hdrs     = {
        "Accept":     "application/vnd.github.v3+json",
        "User-Agent": "Mozilla/5.0"
    }

    for user in GITHUB_USERS:
        try:
            r = requests.get(
                f"https://api.github.com/users/{user}/repos"
                f"?per_page=100&sort=updated",
                headers=hdrs, timeout=12
            )
            if r.status_code == 200:
                for repo in r.json():
                    key = f"gh:{repo['full_name']}"
                    if key in seen:
                        continue
                    seen.add(key)
                    findings.append({
                        "type":"github",
                        "name":repo['full_name'],
                        "url":repo['html_url'],
                        "date":repo.get('updated_at','')[:10]
                    })
                    log(f"  [GH] {repo['full_name']}")
        except Exception as e:
            log(f"  GitHub err ({user}): {e}")
        time.sleep(1)

    for q in GITHUB_SEARCH:
        try:
            r = requests.get(
                f"https://api.github.com/search/repositories"
                f"?q={q}&sort=updated&per_page=10",
                headers=hdrs, timeout=12
            )
            if r.status_code == 200:
                for item in r.json().get('items',[]):
                    key = f"ghs:{item['full_name']}"
                    if key in seen:
                        continue
                    seen.add(key)
                    findings.append({
                        "type":"github",
                        "name":item['full_name'],
                        "url":item['html_url'],
                        "date":item.get('updated_at','')[:10]
                    })
        except Exception as e:
            log(f"  GH search err: {e}")
        time.sleep(2)

    data["seen_keys"] = list(seen)
    return findings

# ===================================================
# ALERT FORMAT
# ===================================================

def alert(f):
    t = f['type']
    ts = datetime.now().strftime('%d %b %H:%M')

    if t == "cf_update":
        return (
            f"🔄 <b>VERSION UPDATE!</b>\n"
            f"📱 <b>{f['app']}</b>\n"
            f"📊 v{f['old']} → <b>v{f['new']}</b>\n"
            f"🌐 {f['domain']}\n"
            f"🔗 <code>{f['url']}</code>\n"
            f"💾 {f['mb']} MB | ⏰ {ts}"
        )
    elif t == "cf_new":
        return (
            f"🆕 <b>NAYA APP MILA!</b>\n"
            f"📱 <b>{f['app']}</b> v{f['ver']}\n"
            f"🔗 <code>{f['url']}</code>\n"
            f"💾 {f['mb']} MB | ⏰ {ts}"
        )
    elif t == "cf_found":
        return (
            f"📦 <b>APK CONFIRMED</b>\n"
            f"📱 <b>{f['app']}</b> v{f['ver']}\n"
            f"🔗 <code>{f['url']}</code>\n"
            f"💾 {f['mb']} MB"
        )
    elif t == "domain_apk":
        return (
            f"🌐 <b>DOMAIN APK!</b>\n"
            f"📱 <b>{f['app']}</b>\n"
            f"🔗 <code>{f['url']}</code>"
        )
    elif t == "ssl":
        return (
            f"🔐 <b>NAYA DOMAIN!</b>\n"
            f"🌐 <code>{f['domain']}</code>\n"
            f"📅 {f['date']} | 🔍 {f['kw']}\n"
            f"➡️ https://{f['domain']}"
        )
    elif t == "github":
        return (
            f"🐙 <b>GITHUB REPO!</b>\n"
            f"📁 <b>{f['name']}</b>\n"
            f"🔗 {f['url']}\n"
            f"📅 {f['date']}"
        )
    return str(f)

# ===================================================
# MAIN
# ===================================================

def run(data):
    all_f = []
    log("CloudFront check...")
    all_f.extend(check_cloudfront(data))
    log("Domain check...")
    all_f.extend(check_domains(data))
    log("SSL check...")
    all_f.extend(check_ssl(data))
    log("GitHub check...")
    all_f.extend(check_github(data))
    return all_f

def main():
    log("="*40)
    log("TailPay Monitor v3 START")
    log(f"BOT_TOKEN set: {bool(BOT_TOKEN)}")
    log(f"CHAT_ID set:   {bool(CHAT_ID)}")
    log("="*40)

    # Startup test message
    send("🟢 <b>TailPay Monitor v3 ON</b>\n\n"
         f"📱 {len(APP_MAP)} apps track ho rahe hain\n"
         "🔄 CloudFront version updates\n"
         "🆕 Naye apps detect\n"
         "🔐 SSL certificates\n"
         "🐙 GitHub repos\n\n"
         f"⏰ Har {INTERVAL//60} min check hoga!")

    data = load_data()

    log("Pehla scan shuru...")
    findings = run(data)
    save_data(data)

    if findings:
        send(f"📋 <b>Pehle scan mein {len(findings)} cheezein mili!</b>")
        for f in findings:
            send(alert(f))
            time.sleep(0.5)
    else:
        log("Pehla scan complete — kuch naya nahi mila")
        send("✅ Pehla scan complete!\nKoi naya app nahi mila abhi.\nAb monitoring shuru — alert aayega jab kuch mile!")

    while True:
        log(f"Next check in {INTERVAL//60} min...")
        time.sleep(INTERVAL)
        log("Checking all sources...")
        findings = run(data)
        save_data(data)
        if findings:
            for f in findings:
                send(alert(f))
                log(f"Sent: {f['type']}")
                time.sleep(0.5)
        else:
            log("Kuch naya nahi")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Band kiya.")
        send("🔴 Monitor band ho gaya.")
