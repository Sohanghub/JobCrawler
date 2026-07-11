import html
import logging
import os

import requests

log = logging.getLogger(__name__)
LIMIT = 4000  # Telegram hard limit is 4096; leave headroom


def _messages(jobs):
    lines = [f'• <a href="{html.escape(j.url, quote=True)}">'
             f'{html.escape(j.title)}</a> — {html.escape(j.company)}'
             f' ({html.escape(j.location)})' for j in jobs]
    text = f"<b>{len(jobs)} fresh job(s)</b>"
    for line in lines:
        if len(text) + len(line) + 1 > LIMIT:
            yield text
            text = line
        else:
            text += "\n" + line
    yield text


def send(jobs, alerts=()):
    msgs = list(_messages(jobs)) if jobs else []
    if alerts:
        msgs.append("⚠️ <b>Health alerts</b>\n"
                    + "\n".join(html.escape(a) for a in alerts))
    if not msgs:
        return
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.warning("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set; "
                    "printing digest to stdout instead")
        for msg in msgs:
            print(msg)
        return
    for msg in msgs:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=30)
        r.raise_for_status()
