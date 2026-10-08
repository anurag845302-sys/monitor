import requests
import time
import json
import os
import re
import hashlib
from datetime import datetime, timezone, timedelta

# ===================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID   = os.environ.get("CHAT_ID", "")
GH_TOKEN  = os.environ.get("GH_TOKEN", "")  # optional GitHub token
INTERVAL  = 900
SAVE_FILE = os.environ.get("SAVE_FILE", "/data/seen.json")
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

SEEN_LIMIT = 10000  # max keys to keep

# ===================================================
# UTILITIES
# ===================================================

def log(msg):
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}", flush=True)

def send(msg):
    if not BOT_TOKEN or not CHAT_ID:
        log("[SEND] TOKEN or CHAT missing")
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=15
        )
        if r.status_code != 200:
            log(f"[SEND FAIL] {r.status_code}")
    except Exception as e:
        log(f"[SEND ERR] {e}")

def load_data():
    default = {
        "seen_keys": [],
        "app_versions": {},
        "app_hashes": {},
        "github_repos": {},
        "github_releases": {},
        "last_scan": None,
        "first_run_done": False,
    }
    if os.path.exists(SAVE_FILE):
        try:
            with open(SAVE_FILE) as f:
                d = json.load(f)
                for k, v in default.items():
                    if k not in d:
                        d[k] = v
                return d
        except Exception as e:
            log(f"load_data err: {e}")
    return default

def save_data(d):
    try:
        os.makedirs(os.path.dirname(SAVE_FILE), exist_ok=True)
    except Exception:
        pass
    tmp = SAVE_FILE + ".tmp"
    with open(tmp, 'w') as f:
        json.dump(d, f)
    os.replace(tmp, SAVE_FILE)

def prune_seen(seen_list):
    if len(seen_list) > SEEN_LIMIT:
        return seen_list[-SEEN_LIMIT:]
    return seen_list

def human_size(b):
    if not b: return "?"
    return f"{round(b/1024/1024, 2)} MB"

def now_str():
    return datetime.now(timezone.utc).strftime('%d %b %H:%M UTC')

# ===================================================
# MODULE 1 — CLOUDFRONT TRACKER (detailed)
# ===================================================

def cf_head(url):
    """HEAD request — returns (status, size, last_modified)"""
    try:
        r = requests.head(url, headers=HEADERS, timeout=8, allow_redirects=True)
        size = int(r.headers.get('Content-Length', 0))
        lm = r.headers.get('Last-Modified', '')
        etag = r.headers.get('ETag', '').strip('"')
        return r.status_code, size, lm, etag
    except Exception:
        return 0, 0, '', ''

def cf_hash(url):
    """Download APK to compute SHA256 — only if changed. Limit 20MB."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=30, stream=True)
        if r.status_code != 200:
            return None
        h = hashlib.sha256()
        total = 0
        for chunk in r.iter_content(65536):
            h.update(chunk)
            total += len(chunk)
            if total > 25 * 1024 * 1024:
                break
        return h.hexdigest()[:16]
    except Exception:
        return None

def check_cloudfront(data):
    findings = []
    seen = set(data["seen_keys"])
    versions = data["app_versions"]
    hashes = data["app_hashes"]

    for domain, (app, base_ver) in APP_MAP.items():
        cur = versions.get(app, base_ver)
        # check cur and up to +10 versions
        for ver in range(cur, cur + 11):
            url = f"{CF_BASE}/{app}/{app}{ver}/app.apk"
            key = f"cf:{app}{ver}"

            status, size, lm, etag = cf_head(url)
            if status == 200:
                if ver > cur:
                    # version update
                    old_ver = cur
                    versions[app] = ver
                    old_hash = hashes.get(app, {}).get("hash")
                    new_hash = etag or None
                    hashes[app] = {"ver": ver, "hash": new_hash, "size": size, "lm": lm}
                    if key not in seen:
                        seen.add(key)
                        findings.append({
                            "type": "cf_update",
                            "app": app.upper(),
                            "domain": domain,
                            "old_ver": old_ver,
                            "new_ver": ver,
                            "url": url,
                            "size": size,
                            "lm": lm,
                            "old_hash": old_hash,
                            "new_hash": new_hash,
                        })
                else:
                    # same version, check if size or etag changed
                    prev = hashes.get(app, {})
                    prev_size = prev.get("size")
                    prev_hash = prev.get("hash")
                    changed = False
                    reasons = []
                    if prev_size and size and prev_size != size:
                        changed = True
                        reasons.append(f"size {human_size(prev_size)} → {human_size(size)}")
                    if prev_hash and etag and prev_hash != etag:
                        changed = True
                        reasons.append(f"hash {prev_hash[:8]} → {etag[:8]}")
                    hashes[app] = {"ver": ver, "hash": etag, "size": size, "lm": lm}
                    if changed and key not in seen:
                        seen.add(key)
                        findings.append({
                            "type": "cf_rehash",
                            "app": app.upper(),
                            "domain": domain,
                            "ver": ver,
                            "url": url,
                            "size": size,
                            "lm": lm,
                            "reasons": reasons,
                        })
                    elif key not in seen:
                        # first time — record baseline, don't spam
                        seen.add(key)
                versions[app] = ver
                break
            time.sleep(0.15)

    data["seen_keys"] = prune_seen(list(seen))
    data["app_versions"] = versions
    data["app_hashes"] = hashes
    return findings

# ===================================================
# MODULE 2 — DOMAIN DIRECT CHECK
# ===================================================

def check_domains(data):
    findings = []
    seen = set(data["seen_keys"])

    for domain, (app, _) in APP_MAP.items():
        try:
            r = requests.get(f"https://{domain}", headers=HEADERS, timeout=10,
                             allow_redirects=True)
            if r.status_code not in [200, 201]:
                continue
            apk_links = re.findall(r'https?://[^\s"\'<>]+\.apk', r.text)
            for link in apk_links:
                key = f"dom:{link}"
                if key in seen:
                    continue
                seen.add(key)
                findings.append({
                    "type": "domain_apk",
                    "app": app.upper(),
                    "domain": domain,
                    "url": link,
                })
        except Exception:
            pass
        time.sleep(0.3)

    data["seen_keys"] = prune_seen(list(seen))
    return findings

# ===================================================
# MODULE 3 — SSL CERT
# ===================================================

def check_ssl(data):
    findings = []
    seen = set(data["seen_keys"])
    since = datetime.now() - timedelta(days=3)

    for kw in CRT_KEYWORDS:
        try:
            r = requests.get(f"https://crt.sh/?q=%25{kw}%25&output=json", timeout=25)
            if r.status_code != 200:
                continue
            certs = r.json()
            for cert in certs:
                domain = cert.get('name_value', '').strip().split('\n')[0]
                date_s = cert.get('not_before', '')[:10]
                if not domain or domain.startswith('*'):
                    continue
                key = f"ssl:{domain}"
                if key in seen:
                    continue
                try:
                    d = datetime.strptime(date_s, '%Y-%m-%d')
                    if d >= since:
                        seen.add(key)
                        findings.append({
                            "type": "ssl",
                            "domain": domain,
                            "date": date_s,
                            "kw": kw,
                        })
                except Exception:
                    pass
        except Exception as e:
            log(f"crt err {kw}: {e}")
        time.sleep(1)

    data["seen_keys"] = prune_seen(list(seen))
    return findings

# ===================================================
# MODULE 4 — GITHUB
# ===================================================

def gh_headers():
    h = {"Accept": "application/vnd.github+json", "User-Agent": "tp-monitor"}
    if GH_TOKEN:
        h["Authorization"] = f"Bearer {GH_TOKEN}"
    return h

def gh_get(url):
    try:
        r = requests.get(url, headers=gh_headers(), timeout=12)
        return r.status_code, r.headers, (r.json() if r.status_code == 200 else None)
    except Exception as e:
        log(f"gh err: {e}")
        return 0, {}, None

def check_github(data):
    findings = []
    seen = set(data["seen_keys"])
    known_repos = data["github_repos"]
    known_releases = data["github_releases"]

    for user in GITHUB_USERS:
        status, hdrs, repos = gh_get(f"https://api.github.com/users/{user}/repos?per_page=100&sort=updated")
        if status == 404:
            log(f"[GH] {user}: not found")
            continue
        if status == 403:
            reset = hdrs.get("X-RateLimit-Reset", "?")
            log(f"[GH] {user}: rate limited, reset {reset}")
            continue
        if status != 200:
            log(f"[GH] {user}: status {status}")
            continue

        log(f"[GH] {user}: {len(repos)} repos")

        for repo in repos:
            full = repo['full_name']
            key = f"gh:{full}"
            updated = repo.get('updated_at', '')[:10]
            desc = repo.get('description') or ''
            prev = known_repos.get(full)

            if key not in seen:
                seen.add(key)
                known_repos[full] = {"updated": updated, "desc": desc}
                findings.append({
                    "type": "github_repo",
                    "user": user,
                    "name": full,
                    "url": repo['html_url'],
                    "date": updated,
                    "desc": desc,
                })
            elif prev and prev.get("updated") != updated:
                known_repos[full] = {"updated": updated, "desc": desc}
                findings.append({
                    "type": "github_repo_update",
                    "user": user,
                    "name": full,
                    "url": repo['html_url'],
                    "old_date": prev.get("updated", "?"),
                    "new_date": updated,
                    "desc": desc,
                })
                seen.add(key)

            # releases
            rel_status, _, releases = gh_get(
                f"https://api.github.com/repos/{full}/releases?per_page=5"
            )
            if rel_status == 200 and releases:
                for rel in releases:
                    tag = rel['tag_name']
                    rkey = f"ghrel:{full}:{tag}"
                    pub = rel.get('published_at', '')[:10]
                    if rkey in seen:
                        continue
                    seen.add(rkey)
                    known_releases[rkey] = {"pub": pub}
                    apks = [a for a in rel.get('assets', []) if a['name'].lower().endswith('.apk')]
                    findings.append({
                        "type": "github_release",
                        "user": user,
                        "repo": full,
                        "tag": tag,
                        "name": rel.get('name', tag),
                        "body": (rel.get('body') or '')[:300],
                        "date": pub,
                        "apks": [{"name": a['name'], "url": a['browser_download_url'],
                                  "size": a['size']} for a in apks],
                    })
            time.sleep(0.5)

    # search
    for q in GITHUB_SEARCH:
        status, _, result = gh_get(
            f"https://api.github.com/search/repositories?q={requests.utils.quote(q)}&sort=updated&per_page=10"
        )
        if status == 200 and result:
            for item in result.get('items', []):
                full = item['full_name']
                key = f"ghs:{full}"
                if key in seen:
                    continue
                seen.add(key)
                findings.append({
                    "type": "github_search",
                    "name": full,
                    "url": item['html_url'],
                    "date": item.get('updated_at', '')[:10],
                    "query": q,
                    "desc": item.get('description') or '',
                })
        time.sleep(2)

    data["seen_keys"] = prune_seen(list(seen))
    data["github_repos"] = known_repos
    data["github_releases"] = known_releases
    return findings

# ===================================================
# ALERT FORMATTING
# ===================================================

def fmt_apks(apks):
    if not apks:
        return "  (no APK asset)"
    lines = []
    for a in apks:
        lines.append(f"  📦 {a['name']} ({human_size(a['size'])})\n     {a['url']}")
    return "\n".join(lines)

def alert(f):
    t = f['type']
    ts = now_str()

    if t == "cf_update":
        return (
            f"🔄 <b>VERSION UPDATE</b>\n"
            f"📱 <b>{f['app']}</b>\n"
            f"📊 v{f['old_ver']} → <b>v{f['new_ver']}</b>\n"
            f"🌐 {f['domain']}\n"
            f"💾 {human_size(f['size'])}\n"
            f"🕐 {f['lm'] or 'unknown'}\n"
            f"🔗 <code>{f['url']}</code>\n"
            f"⏰ {ts}"
        )
    if t == "cf_rehash":
        return (
            f"♻️ <b>APK CHANGED (same version)</b>\n"
            f"📱 <b>{f['app']}</b> v{f['ver']}\n"
            f"📝 {'; '.join(f['reasons'])}\n"
            f"💾 {human_size(f['size'])}\n"
            f"🔗 <code>{f['url']}</code>\n"
            f"⏰ {ts}"
        )
    if t == "domain_apk":
        return (
            f"🌐 <b>DOMAIN APK</b>\n"
            f"📱 <b>{f['app']}</b>\n"
            f"🌐 {f['domain']}\n"
            f"🔗 <code>{f['url']}</code>\n"
            f"⏰ {ts}"
        )
    if t == "ssl":
        return (
            f"🔐 <b>NEW SSL CERT</b>\n"
            f"🌐 <code>{f['domain']}</code>\n"
            f"📅 {f['date']}\n"
            f"🔍 keyword: {f['kw']}\n"
            f"➡️ https://{f['domain']}\n"
            f"⏰ {ts}"
        )
    if t == "github_repo":
        return (
            f"🐙 <b>NEW GITHUB REPO</b>\n"
            f"👤 {f['user']}\n"
            f"📁 <b>{f['name']}</b>\n"
            f"📝 {f['desc'] or '(no description)'}\n"
            f"🔗 {f['url']}\n"
            f"📅 {f['date']}\n"
            f"⏰ {ts}"
        )
    if t == "github_repo_update":
        return (
            f"🐙 <b>GITHUB REPO UPDATED</b>\n"
            f"👤 {f['user']}\n"
            f"📁 <b>{f['name']}</b>\n"
            f"📅 {f['old_date']} → <b>{f['new_date']}</b>\n"
            f"📝 {f['desc'] or ''}\n"
            f"🔗 {f['url']}\n"
            f"⏰ {ts}"
        )
    if t == "github_release":
        body = f"\n📄 {f['body']}" if f['body'] else ""
        return (
            f"🚀 <b>NEW RELEASE / APK</b>\n"
            f"👤 {f['user']}\n"
            f"📁 <b>{f['repo']}</b>\n"
            f"🏷️ Tag: <b>{f['tag']}</b>\n"
            f"📅 {f['date']}{body}\n"
            f"{fmt_apks(f['apks'])}\n"
            f"⏰ {ts}"
        )
    if t == "github_search":
        return (
            f"🔎 <b>GITHUB SEARCH HIT</b>\n"
            f"🔍 query: <code>{f['query']}</code>\n"
            f"📁 <b>{f['name']}</b>\n"
            f"📝 {f['desc'] or ''}\n"
            f"🔗 {f['url']}\n"
            f"📅 {f['date']}\n"
            f"⏰ {ts}"
        )
    return f"❓ unknown: {f}"

# ===================================================
# MAIN
# ===================================================

def run(data):
    all_f = []
    log("CloudFront check...")
    cf = check_cloudfront(data)
    log(f"  cf findings: {len(cf)}")
    all_f.extend(cf)

    log("Domain check...")
    dm = check_domains(data)
    log(f"  domain findings: {len(dm)}")
    all_f.extend(dm)

    log("SSL check...")
    sl = check_ssl(data)
    log(f"  ssl findings: {len(sl)}")
    all_f.extend(sl)

    log("GitHub check...")
    gh = check_github(data)
    log(f"  github findings: {len(gh)}")
    all_f.extend(gh)

    return all_f

def heartbeat(data, scan_count, findings_count, started_at):
    uptime = str(datetime.now(timezone.utc) - started_at).split('.')[0]
    versions = data.get("app_versions", {})
    total_apps = len(versions)
    last = data.get("last_scan", "?")
    if findings_count == 0:
        return (
            f"💤 <b>Heartbeat — koi update nahi</b>\n"
            f"⏰ {now_str()}\n"
            f"🔁 Scan #{scan_count} | Uptime: {uptime}\n"
            f"📱 Tracked apps: {total_apps}\n"
            f"🔍 Last new finding: {last}\n"
            f"✅ Sab sources check kiye — kuch naya nahi mila."
        )
    return None

def startup_message(data):
    versions = data.get("app_versions", {})
    return (
        "🟢 <b>TailPay Monitor v5 ON</b>\n\n"
        f"📱 {len(APP_MAP)} apps tracked\n"
        f"🔄 CloudFront version + hash changes\n"
        f"🌐 Domain APK check\n"
        f"🔐 SSL certs\n"
        f"🐙 GitHub: {len(GITHUB_USERS)} accounts + {len(GITHUB_SEARCH)} search queries\n"
        f"💓 Heartbeat every {INTERVAL//60} min\n"
        f"📊 Baseline versions cached: {len(versions)}\n\n"
        f"Pehla scan chal raha hai..."
    )

def main():
    log("=" * 50)
    log("TailPay Monitor v5 START")
    log(f"BOT_TOKEN: {'SET' if BOT_TOKEN else 'MISSING'}")
    log(f"CHAT_ID:   {'SET' if CHAT_ID else 'MISSING'}")
    log(f"GH_TOKEN:  {'SET' if GH_TOKEN else 'not set (rate limit 60/h)'}")
    log(f"SAVE_FILE: {SAVE_FILE}")
    log("=" * 50)

    data = load_data()
    first_run = not data.get("first_run_done", False)

    send(startup_message(data))

    started_at = datetime.now(timezone.utc)
    scan_count = 0

    # First run: silent baseline, just report counts
    if first_run:
        log("First run: building baseline silently...")
        findings = run(data)
        data["first_run_done"] = True
        data["last_scan"] = now_str()
        save_data(data)

        cf_found = [f for f in findings if f['type'] == 'cf_update']
        gh_repo = [f for f in findings if f['type'] == 'github_repo']
        gh_rel = [f for f in findings if f['type'] == 'github_release']
        ssl_c = [f for f in findings if f['type'] == 'ssl']
        summary = (
            f"📊 <b>Baseline complete</b>\n\n"
            f"📦 CloudFront updates cached: {len(cf_found)}\n"
            f"🐙 GitHub repos: {len(gh_repo)}\n"
            f"🚀 GitHub releases: {len(gh_rel)}\n"
            f"🔐 SSL certs: {len(ssl_c)}\n\n"
            f"Ab monitoring active. Har {INTERVAL//60} min scan hoga."
        )
        send(summary)
    else:
        log("Resuming from saved state.")

    # Main loop
    while True:
        log(f"sleeping {INTERVAL//60} min...")
        time.sleep(INTERVAL)
        scan_count += 1
        log(f"=== scan #{scan_count} ===")

        try:
            findings = run(data)
        except Exception as e:
            log(f"scan err: {e}")
            send(f"⚠️ Scan error: <code>{e}</code>")
            continue

        data["last_scan"] = now_str()
        if findings:
            data["last_finding"] = now_str()
        save_data(data)

        if findings:
            log(f"findings: {len(findings)}")
            send(f"⚡ <b>{len(findings)} new finding(s)</b> — scan #{scan_count}")
            for f in findings:
                try:
                    send(alert(f))
                except Exception as e:
                    log(f"alert err: {e}")
                time.sleep(0.5)
        else:
            hb = heartbeat(data, scan_count, 0, started_at)
            if hb:
                send(hb)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Stopped.")
        send("🔴 Monitor v5 stopped.")
