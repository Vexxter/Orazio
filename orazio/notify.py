"""Sends one notification to every channel the user turned on: desktop, Telegram, webhook, email.

One channel failing never stops the others; send() returns {channel: "ok" or the reason} so the settings tab's Test
button can say exactly what went wrong. Message text reaches the desktop notifier through environment variables,
never the command line, so a headline or filing title can't inject a command.
"""
import os
import smtplib
import subprocess
import sys
from email.message import EmailMessage

import requests

from . import user_settings

_WIN_TOAST = """
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$x = $t.GetElementsByTagName('text')
$x.Item(0).AppendChild($t.CreateTextNode($env:ORAZIO_TITLE)) > $null
$x.Item(1).AppendChild($t.CreateTextNode($env:ORAZIO_BODY)) > $null
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($t))
"""
_MAC_NOTE = 'display notification (system attribute "ORAZIO_BODY") with title (system attribute "ORAZIO_TITLE")'


def _desktop(title, body, _s):
    env = {**os.environ, "ORAZIO_TITLE": title, "ORAZIO_BODY": body}
    if sys.platform == "win32":
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", _WIN_TOAST]
    elif sys.platform == "darwin":
        cmd = ["osascript", "-e", _MAC_NOTE]
    else:
        cmd = ["notify-send", "--", title, body]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=20, check=False)
    if r.returncode:
        raise RuntimeError((r.stderr or "the desktop notifier failed").strip()[:200])


def _telegram(title, body, s):
    r = requests.post(f"https://api.telegram.org/bot{s['telegramToken']}/sendMessage",
                      json={"chat_id": s["telegramChat"], "text": f"{title}\n{body}"}, timeout=10)
    if r.status_code != 200:
        raise RuntimeError(f"Telegram answered HTTP {r.status_code}: check the token and chat ID")


def _webhook(title, body, s):
    r = requests.post(s["webhookUrl"], json={"title": title, "body": body, "source": "orazio"}, timeout=10)
    r.raise_for_status()


def _email(title, body, s):
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = title, s["smtpUser"] or s["emailTo"], s["emailTo"]
    msg.set_content(body)
    with smtplib.SMTP(s["smtpHost"], s["smtpPort"], timeout=15) as smtp:
        smtp.starttls()
        if s["smtpUser"]:
            smtp.login(s["smtpUser"], s["smtpPassword"])
        smtp.send_message(msg)


def _channels(s):
    if s["desktop"]:
        yield "desktop", _desktop
    if s["telegramToken"] and s["telegramChat"]:
        yield "telegram", _telegram
    if s["webhookUrl"]:
        yield "webhook", _webhook
    if s["smtpHost"] and s["emailTo"]:
        yield "email", _email


def send(title, body):
    s = user_settings.load()
    out = {}
    for name, fn in _channels(s):
        try:
            fn(title, body, s)
            out[name] = "ok"
        except (OSError, RuntimeError, subprocess.SubprocessError, smtplib.SMTPException, requests.RequestException) as e:
            # The token is part of the Telegram URL, so a requests error must never be echoed back as written.
            out[name] = str(e).replace(s["telegramToken"] or "\0", "***")[:200]
    return out
