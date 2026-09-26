import requests
import time
import json
import os
import re
from datetime import datetime, timedelta

# ===== APNA DATA DAAL =====
BOT_TOKEN  = os.environ.get("BOT_TOKEN", "")
CHAT_ID    = os.environ.get("CHAT_ID", "")
INTERVAL   = 900
SAVE_FILE  = "seen.json"
# ==========================

CF_BASE = "https://d6d2sg7as7xll.cloudfront.net"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 12; Redmi) "
                  "AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36"
}

# ============================================================
# DOMAIN → APP NAME + CURRENT VERSION MAPPING
# Tune jo data diya — yahan sab hai
# ============================================================

APP_MAP = {
    # domain: (app_short_name, current_version)
    "wypay168.com":          ("wy",   503),
    "jpgpay.top":            ("jpg",  103),
    "okpay365.win":          ("ok",   104),
    "comeappdown.com":       ("come", 121),
    "dd-pay.net":            ("dd",   130),
    "diwadown.net":          ("diwa", 165),
    "wynnpay24.com":         ("wynn", 105),
    "dowapp.uday.ink":       ("nova", 103),
    "install.vlinkapp.net":  ("link", 126),
    "dowapp.ffcpay.ink":     ("ffc",  105),
    "qqvip.beer":            ("qq",   106),
    "kkdow.com":             ("kk",   100),
    "miodow.link":           ("mio",  100),
    "bittaro.net":           ("658",  100),
    "neoappdow.com":         ("neo",  103),
    "install.r7vpd3.com":    ("zoro", 122),
    "install.ktkpay.cc":     ("ktk",  106),
    # Extra known domains
    "dtdow.link":            ("dt",   106),
    "diwacore.com":          ("diwa", 165),
    "alphad.net":            ("alpha",100),
    "omnicloud-down.com":    ("omni", 100),
    "one-pay.ink":           ("one",  100),
    "shaktipay.app":         ("shakti",100),
    "yiwalletpay.com":       ("yiwa", 100),
}

# crt.sh keywords
CRT_KEYWORDS = [
    "tailpay", "diwapay", "diwacore", "nexways",
    "etnanets", "tailshaofu", "dtpay", "dtdow",
    "qqvip", "kkdow", "miodow", "bittaro", "wypay",
    "jpgpay", "okpay", "comeapp", "wynnpay"
]

# GitHub
GITHUB_USERS   = ["tailshaofu005-cmd", "tailpaytech"]
GITHUB_SEARCH  = ["tailshaofu apk", "tailpay payment", "diwapay release"]

# ============================================================
# UTILITIES
# ============================================================

def send(msg):
    try:
        token = os.environ.get("BOT_TOKEN", "")
        chat  = os.environ.get("CHAT_ID", "")
        
        # Debug — log mein print karo
        print(f"[SEND] token length: {len(token)}, chat_id: {chat}")
        
        if not token or not chat:
            print("[SEND ERROR] BOT_TOKEN ya CHAT_ID empty hai!")
            return
            
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
        print(f"[SEND] Response: {r.status_code} — {r.text[:100]}")
    except Exception as e:
        print(f"[SEND ERROR] {e}")

# ============================================================
# MODULE 1 — CLOUDFRONT VERSION TRACKER
# Existing apps ke naye versions detect karo
# ============================================================

def check_cf_version_exists(app, version):
    """Ek specific version exist karta hai?"""
    url = f"{CF_BASE}/{app}/{app}{version}/app.apk"
    try:
        r = requests.head(url, headers=HEADERS, timeout=6)
        if r.status_code == 200:
            size = int(r.headers.get('Content-Length', 0))
            return url, size
    except:
        pass
    return None, None

def check_cloudfront_updates(data):
    """
    Har known app ke liye:
    1. Current version se upar check karo
    2. Naya version mila = alert
    3. Naya app (unknown) bhi scan karo
    """
    findings = []
    seen_keys = set(data["seen_keys"])
    app_versions = data["app_versions"]

    # Known apps — version update check
    for domain, (app, known_ver) in APP_MAP.items():
        if app not in app_versions:
            app_versions[app] = known_ver

        current_ver = app_versions[app]

        # Agle 10 versions check karo
        for ver in range(current_ver, current_ver + 11):
            key = f"cf:{app}{ver}"
            if key in seen_keys:
                continue

            url, size = check_cf_version_exists(app, ver)
            if url:
                seen_keys.add(key)
                size_mb = round(size / 1024 / 1024, 1) if size else 0
                is_new_version = ver > current_ver
                is_new_app     = ver == current_ver

                if is_new_version:
                    # Version update!
                    old_ver = app_versions[app]
                    app_versions[app] = ver
                    findings.append({
                        "type":    "cf_update",
                        "app":     app.upper(),
                        "domain":  domain,
                        "old_ver": old_ver,
                        "new_ver": ver,
                        "url":     url,
                        "size_mb": size_mb
                    })
                    log(f"  [VERSION UPDATE] {app} v{old_ver}→v{ver}")
                else:
                    findings.append({
                        "type":    "cf_existing",
                        "app":     app.upper(),
                        "domain":  domain,
                        "ver":     ver,
                        "url":     url,
                        "size_mb": size_mb
                    })
            time.sleep(0.2)

    # Unknown apps bhi scan karo — naya app detect
    extra_names = [
        "star","gold","win","top","ace","pro","max","plus",
        "lite","go","fast","flash","super","mega","ultra",
        "tiger","lion","eagle","wolf","fox","bear","king",
        "club","zone","hub","plus","cash","coin","rupee",
        "india","bharat","desi","dev","pay2","pay3","gpay",
        "epay","xpay","zpay","apay","bpay","cpay","dpay",
        "epay","fpay","hpay","ipay","jpay","kpay","lpay",
        "mpay","npay","opay","ppay","rpay","spay","tpay",
        "upay","vpay","wpay","ypay","wallet","purse","fund"
    ]
    known_apps = {v[0] for v in APP_MAP.values()}

    for app in extra_names:
        if app in known_apps:
            continue
        for ver in range(100, 115):
            key = f"cf:{app}{ver}"
            if key in seen_keys:
                break
            url, size = check_cf_version_exists(app, ver)
            if url:
                seen_keys.add(key)
                size_mb = round(size / 1024 / 1024, 1) if size else 0
                app_versions[app] = ver
                findings.append({
                    "type":    "cf_new_app",
                    "app":     app.upper(),
                    "ver":     ver,
                    "url":     url,
                    "size_mb": size_mb
                })
                log(f"  [NEW APP] {app} v{ver}")
                break
        time.sleep(0.2)

    data["seen_keys"]    = list(seen_keys)
    data["app_versions"] = app_versions
    return findings

# ============================================================
# MODULE 2 — DOMAIN APK DIRECT CHECK
# Har domain ka download page check karo
# ============================================================

def check_domain_apk(data):
    findings = []
    seen_keys = set(data["seen_keys"])

    for domain, (app, known_ver) in APP_MAP.items():
        try:
            r = requests.get(
                f"https://{domain}",
                headers=HEADERS,
                timeout=8,
                allow_redirects=True
            )
            if r.status_code not in [200, 201]:
                continue

            # APK link dhundho
            apk_links = re.findall(
                r'https?://[^\s"\'<>]+\.apk', r.text
            )
            # Version number dhundho page mein
            versions = re.findall(r'[vV]?(\d{3,4})', r.text)

            for apk_url in apk_links:
                key = f"domain_apk:{apk_url}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                findings.append({
                    "type":   "domain_apk",
                    "domain": domain,
                    "app":    app.upper(),
                    "url":    apk_url,
                })
                log(f"  [DOMAIN APK] {domain} → {apk_url}")

        except:
            pass
        time.sleep(0.3)

    data["seen_keys"] = list(seen_keys)
    return findings

# ============================================================
# MODULE 3 — SSL CERTIFICATE MONITOR
# ============================================================

def check_crt(data):
    findings = []
    seen_keys = set(data["seen_keys"])
    yesterday = datetime.now() - timedelta(hours=24)

    for kw in CRT_KEYWORDS:
        try:
            url = f"https://crt.sh/?q=%25{kw}%25&output=json"
            r = requests.get(url, timeout=20)
            if r.status_code != 200:
                continue

            for cert in r.json():
                domain   = cert.get('name_value', '').strip()
                date_str = cert.get('not_before', '')
                issuer   = cert.get('issuer_name', '')

                if not domain or domain.startswith('*'):
                    continue

                key = f"crt:{domain}"
                if key in seen_keys:
                    continue

                try:
                    cert_date = datetime.strptime(date_str[:10], '%Y-%m-%d')
                    if cert_date >= yesterday:
                        seen_keys.add(key)
                        findings.append({
                            "type":    "ssl",
                            "domain":  domain,
                            "date":    date_str[:10],
                            "keyword": kw,
                            "issuer":  issuer[:60]
                        })
                        log(f"  [SSL] {domain}")
                except:
                    pass

        except Exception as e:
            log(f"crt.sh error ({kw}): {e}")
        time.sleep(1)

    data["seen_keys"] = list(seen_keys)
    return findings

# ============================================================
# MODULE 4 — GITHUB MONITOR
# ============================================================

def check_github(data):
    findings  = []
    seen_keys = set(data["seen_keys"])
    gh_headers = {
        "Accept":     "application/vnd.github.v3+json",
        "User-Agent": "Mozilla/5.0"
    }

    for user in GITHUB_USERS:
        try:
            url = (f"https://api.github.com/users/{user}"
                   f"/repos?per_page=100&sort=updated")
            r = requests.get(url, headers=gh_headers, timeout=10)
            if r.status_code == 200:
                for repo in r.json():
                    key = f"gh:{repo['full_name']}"
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    findings.append({
                        "type":      "github",
                        "full_name": repo['full_name'],
                        "url":       repo['html_url'],
                        "updated":   repo.get('updated_at','')[:10]
                    })
                    log(f"  [GITHUB] {repo['full_name']}")
        except Exception as e:
            log(f"GitHub error ({user}): {e}")
        time.sleep(1)

    for query in GITHUB_SEARCH:
        try:
            url = (f"https://api.github.com/search/repositories"
                   f"?q={query}&sort=updated&per_page=10")
            r = requests.get(url, headers=gh_headers, timeout=10)
            if r.status_code == 200:
                for item in r.json().get('items', []):
                    key = f"gh_s:{item['full_name']}"
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    findings.append({
                        "type":      "github",
                        "full_name": item['full_name'],
                        "url":       item['html_url'],
                        "updated":   item.get('updated_at','')[:10]
                    })
        except Exception as e:
            log(f"GitHub search error: {e}")
        time.sleep(2)

    data["seen_keys"] = list(seen_keys)
    return findings

# ============================================================
# ALERT FORMATTER
# ============================================================

def format_alert(f):
    t = f['type']

    if t == "cf_update":
        return (
            f"🔄 <b>VERSION UPDATE!</b>\n\n"
            f"📱 App: <b>{f['app']}</b>\n"
            f"📊 Version: v{f['old_ver']} → <b>v{f['new_ver']}</b>\n"
            f"🌐 Domain: {f['domain']}\n"
            f"🔗 <code>{f['url']}</code>\n"
            f"💾 Size: {f['size_mb']} MB\n"
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

    elif t == "cf_new_app":
        return (
            f"🆕 <b>BILKUL NAYA APP!</b>\n\n"
            f"📱 App: <b>{f['app']}</b>\n"
            f"🔢 Version: v{f['ver']}\n"
            f"🔗 <code>{f['url']}</code>\n"
            f"💾 Size: {f['size_mb']} MB\n"
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

    elif t == "cf_existing":
        return (
            f"📦 <b>APK CONFIRMED</b>\n\n"
            f"📱 App: <b>{f['app']}</b> v{f['ver']}\n"
            f"🔗 <code>{f['url']}</code>\n"
            f"💾 {f['size_mb']} MB"
        )

    elif t == "domain_apk":
        return (
            f"🌐 <b>DOMAIN PE NAYA APK!</b>\n\n"
            f"📱 App: <b>{f['app']}</b>\n"
            f"🌐 Domain: {f['domain']}\n"
            f"🔗 <code>{f['url']}</code>"
        )

    elif t == "ssl":
        return (
            f"🔐 <b>NAYA SSL CERT / DOMAIN!</b>\n\n"
            f"🌐 <code>{f['domain']}</code>\n"
            f"📅 Date: {f['date']}\n"
            f"🔍 Keyword: {f['keyword']}\n"
            f"➡️ https://{f['domain']}"
        )

    elif t == "github":
        return (
            f"🐙 <b>GITHUB REPO!</b>\n\n"
            f"📁 <b>{f['full_name']}</b>\n"
            f"🔗 {f['url']}\n"
            f"📅 Updated: {f['updated']}"
        )

    return str(f)

# ============================================================
# MAIN
# ============================================================

def run_checks(data):
    all_findings = []

    log("→ CloudFront version check...")
    all_findings.extend(check_cloudfront_updates(data))

    log("→ Domain APK check...")
    all_findings.extend(check_domain_apk(data))

    log("→ SSL/crt.sh check...")
    all_findings.extend(check_crt(data))

    log("→ GitHub check...")
    all_findings.extend(check_github(data))

    return all_findings

def main():
    log("TailPay Complete Monitor v2 chalu...")
    data = load_seen()

    # Pehli baar run karo toh app_versions initialize karo
    if "app_versions" not in data:
        data["app_versions"] = {}
    if "seen_keys" not in data:
        data["seen_keys"] = []

    send(
        "🟢 <b>TailPay Monitor v2 ON</b>\n\n"
        "Kya track ho raha hai:\n"
        f"📱 {len(APP_MAP)} known apps (version updates)\n"
        "🆕 CloudFront pe naye apps\n"
        "🌐 17 download domains\n"
        "🔐 SSL certificates\n"
        "🐙 GitHub repos\n\n"
        f"⏰ Har {INTERVAL//60} min check\n"
        "Har update — version bhi, naya app bhi — alert aayega!"
    )

    # Pehla scan
    log("Pehla scan...")
    findings = run_checks(data)
    save_seen(data)

    if findings:
        send(f"📋 <b>Pehle scan mein {len(findings)} cheezein mili:</b>")
        for f in findings:
            send(format_alert(f))
            time.sleep(0.5)
    else:
        send("✅ Scan complete. Monitoring shuru!")

    # Main loop
    while True:
        time.sleep(INTERVAL)
        log("Checking all sources...")
        findings = run_checks(data)
        save_seen(data)

        if findings:
            for f in findings:
                alert = format_alert(f)
                send(alert)
                log(f"Alert: {f['type']}")
                time.sleep(0.5)
        else:
            log("Kuch naya nahi")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Band kiya.")
        send("🔴 Monitor band ho gaya.")
