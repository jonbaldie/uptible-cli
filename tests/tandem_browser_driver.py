#!/usr/bin/env python3
"""Automated browser for tandem login: sign in, approve consent, follow redirect to CLI loopback.

Usage: tandem_browser_driver.py <authorize-url>
Env: TANDEM_EMAIL (default alpha@example.test), TANDEM_PASSWORD (default password123).
Stdlib only. Disposable test accounts only; never point at production.
"""
import http.cookiejar
import os
import re
import sys
import urllib.parse
import urllib.request

url = sys.argv[1]
email = os.environ.get("TANDEM_EMAIL", "alpha@example.test")
password = os.environ.get("TANDEM_PASSWORD", "password123")
parsed = urllib.parse.urlsplit(url)
origin = f"{parsed.scheme}://{parsed.netloc}"

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def fetch(u, data=None):
    req = urllib.request.Request(u, data=urllib.parse.urlencode(data).encode() if data else None)
    # Follows redirects by default, including to the CLI loopback callback.
    with opener.open(req, timeout=15) as r:
        return r.status, r.geturl(), r.read().decode("utf-8", "replace")


def csrf(html):
    m = re.search(r'name="_token"[^>]*value="([^"]+)"', html) or re.search(
        r'value="([^"]+)"[^>]*name="_token"', html
    )
    return m.group(1) if m else None


status, final, html = fetch(origin + "/login")
tok = csrf(html)
assert tok, "no CSRF token on login page"
status, final, html = fetch(origin + "/login", {"_token": tok, "email": email, "password": password})
assert "/login" not in final, f"login failed, remained at {final}"

status, final, html = fetch(url)
m = re.search(r'name="auth_token"[^>]*value="([^"]+)"', html) or re.search(
    r'value="([^"]+)"[^>]*name="auth_token"', html
)
assert m, "no auth_token in consent form"
data = {"auth_token": m.group(1)}
tok = csrf(html)
if tok:
    data["_token"] = tok
# Sensitive scopes (delete/email-change) require current-password proof.
if "current_password" in html:
    data["current_password"] = password
status, final, html = fetch(origin + "/oauth/authorize", data)
assert "code=" in final, f"no authorization code in redirect: {final}"
