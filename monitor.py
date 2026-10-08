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

# 4 naye accounts add kiye
GITHUB_USERS = [
    "tailshaofu005-cmd",
    "tailpaytech",
    "649152551",
    "jqkxcdgpkh",
    "286375632",
    "boxcking"
]

GITHUB_SEARCH = [
    "tailshaofu apk",
    "tailpay payment",
    "diwapay release",
    "jpgpay apk",
    "qqpay payment app"
]

# ===================================================
# UTILITIES
# ===================================================

def send(msg):
    print(f"[SEND] token={BOT_TOKEN[:8]}... chat={CHAT_ID}")
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
            print(f"[SEND OK] msg_id={r.json().get('result',{}).get('message_id')}")
        else:
            print(f"[SEND FAIL] {r.status_code}: {r.text[:150]}")
    except Exception as e:
        print(f"[SEND ERR] {e}")

def load_data():
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE) as f:
            d = json.load(f)
            if "seen_keys"    not in d: d["seen_keys"]    = []
            if "app_versions" not in d: d["app_versions"] = {}
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
                    log(f"  [UPDATE] {app} v{old}->v{ver}")
                else:
                    versions[app] = ver
                    findings.append({
                        "type":"cf_found","app":app.upper(),
                        "ver":ver,"url":url,"mb":mb
                    })
            time.sleep(0.2)

    extra = [
        "star","gold","win","top","ace","pro","max",
        "flash","super","mega","tiger","lion","eagle",
        "wolf","king","cash","coin","rupee","gpay",
        "epay","xpay","zpay","pay2","pay3","wallet",
        "swift","speed","quick","rapid","turbo","lite","go"
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
                mb = round(size/1024/1024, 1) if size else 0
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
            if r.status_code not in [200, 201]:
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
                domain = cert.get('name_value', '').strip()
                date_s = cert.get('not_before', '')
                if not domain or domain.startswith('*'):
                    continue
                key = f"ssl:{domain}"
                if key in seen:
                    continue
                try:
                    d = datetime.strptime(date_s[:10], '%Y-%m-%d')
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
# MODULE 4 — GITHUB (6 accounts + search)
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
                repos = r.json()
                log(f"  [GH] {user}: {len(repos)} repos")
                for repo in repos:
                    key = f"gh:{repo['full_name']}"
                    if key in seen:
                        continue
                    seen.add(key)
                    findings.append({
                        "type":   "github",
                        "name":   repo['full_name'],
                        "url":    repo['html_url'],
                        "date":   repo.get('updated_at','')[:10],
                        "user":   user
                    })

                    # Releases bhi check karo
                    try:
                        rel = requests.get(
                            f"https://api.github.com/repos/{repo['full_name']}/releases?per_page=5",
                            headers=hdrs, timeout=10
                        )
                        if rel.status_code == 200:
                            for release in rel.json():
                                rkey = f"ghrel:{repo['full_name']}:{release['tag_name']}"
                                if rkey in seen:
                                    continue
                                seen.add(rkey)
                                # APK asset dhundho
                                for asset in release.get('assets', []):
                                    if asset['name'].endswith('.apk'):
                                        findings.append({
                                            "type":    "github_release",
                                            "repo":    repo['full_name'],
                                            "tag":     release['tag_name'],
                                            "apk":     asset['browser_download_url'],
                                            "size_mb": round(asset['size']/1024/1024, 1),
                                            "date":    release.get('published_at','')[:10],
                                            "user":    user
                                        })
                                        log(f"  [GH RELEASE] {repo['full_name']} {release['tag_name']}")
                    except:
                        pass
                    time.sleep(0.3)

            elif r.status_code == 404:
                log(f"  [GH] {user}: not found")
            else:
                log(f"  [GH] {user}: {r.status_code}")
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
                for item in r.json().get('items', []):
                    key = f"ghs:{item['full_name']}"
                    if key in seen:
                        continue
                    seen.add(key)
                    findings.append({
                        "type": "github",
                        "name": item['full_name'],
                        "url":  item['html_url'],
                        "date": item.get('updated_at','')[:10],
                        "user": "search"
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
    t  = f['type']
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
            f"🆕 <b>NAYA APP CLOUDFRONT PE!</b>\n"
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
            f"🌐 {f['domain']}\n"
            f"🔗 <code>{f['url']}</code>"
        )
    elif t == "ssl":
        return (
            f"🔐 <b>NAYA DOMAIN/SSL!</b>\n"
            f"🌐 <code>{f['domain']}</code>\n"
            f"📅 {f['date']} | 🔍 {f['kw']}\n"
            f"➡️ https://{f['domain']}"
        )
    elif t == "github":
        return (
            f"🐙 <b>GITHUB REPO!</b>\n"
            f"👤 Account: <b>{f['user']}</b>\n"
            f"📁 {f['name']}\n"
            f"🔗 {f['url']}\n"
            f"📅 {f['date']}"
        )
    elif t == "github_release":
        return (
            f"🚀 <b>GITHUB RELEASE / NEW APK!</b>\n"
            f"👤 Account: <b>{f['user']}</b>\n"
            f"📁 {f['repo']}\n"
            f"🏷️ Tag: <b>{f['tag']}</b>\n"
            f"🔗 <code>{f['apk']}</code>\n"
            f"💾 {f['size_mb']} MB | 📅 {f['date']}"
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
    log("=" * 40)
    log("TailPay Monitor v4 START")
    log(f"BOT_TOKEN: {'SET (' + str(len(BOT_TOKEN)) + ' chars)' if BOT_TOKEN else 'MISSING!'}")
    log(f"CHAT_ID:   {'SET' if CHAT_ID else 'MISSING!'}")
    log(f"GitHub accounts: {len(GITHUB_USERS)}")
    log("=" * 40)

    send(
        "🟢 <b>TailPay Monitor v4 ON</b>\n\n"
        f"📱 {len(APP_MAP)} apps track ho rahe hain\n"
        "🔄 CloudFront version updates\n"
        "🆕 Naye CloudFront apps\n"
        "🔐 SSL certificates\n"
        f"🐙 GitHub: {len(GITHUB_USERS)} accounts monitor\n"
        "  ├ tailshaofu005-cmd\n"
        "  ├ tailpaytech\n"
        "  ├ 649152551\n"
        "  ├ jqkxcdgpkh\n"
        "  ├ 286375632\n"
        "  └ boxcking\n\n"
        f"⏰ Har {INTERVAL//60} min check hoga!\n"
        "Koi bhi release/update — seedha alert!"
    )

    data = load_data()

    log("Pehla scan shuru...")
    findings = run(data)
    save_data(data)

    cf_found  = [f for f in findings if f['type'] == 'cf_found']
    updates   = [f for f in findings if f['type'] == 'cf_update']
    new_apps  = [f for f in findings if f['type'] == 'cf_new']
    gh_repos  = [f for f in findings if f['type'] == 'github']
    gh_rel    = [f for f in findings if f['type'] == 'github_release']
    ssl_certs = [f for f in findings if f['type'] == 'ssl']

    summary = (
        f"📊 <b>Pehla scan complete!</b>\n\n"
        f"📦 Existing APKs confirmed: {len(cf_found)}\n"
        f"🔄 Version updates: {len(updates)}\n"
        f"🆕 Naye apps: {len(new_apps)}\n"
        f"🐙 GitHub repos: {len(gh_repos)}\n"
        f"🚀 GitHub releases: {len(gh_rel)}\n"
        f"🔐 SSL certs: {len(ssl_certs)}\n\n"
        f"Ab monitoring shuru — alert aayega jab kuch naya mile!"
    )
    send(summary)

    # Sirf important alerts bhejo — cf_found skip karo (bahut zyada hogi)
    important = [f for f in findings if f['type'] in
                 ['cf_update','cf_new','github','github_release','ssl','domain_apk']]
    if important:
        send(f"⚡ <b>{len(important)} important findings:</b>")
        for f in important:
            send(alert(f))
            time.sleep(0.5)

    while True:
        log(f"Next check {INTERVAL//60} min mein...")
        time.sleep(INTERVAL)
        log("Checking all sources...")
        findings = run(data)
        save_data(data)
        if findings:
            for f in findings:
                send(alert(f))
                log(f"Alert sent: {f['type']}")
                time.sleep(0.5)
        else:
            log("Kuch naya nahi mila")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Band kiya.")
        send("🔴 Monitor band ho gaya.")
