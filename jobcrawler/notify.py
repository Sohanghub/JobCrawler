import html
import logging
import os

import requests

log = logging.getLogger(__name__)
LIMIT = 4000  # Telegram hard limit is 4096; leave headroom


def _messages(jobs):
    lines = []
    for j in jobs:
        tag = f" <i>[{html.escape(j.matched_by)}]</i>" if j.matched_by else ""
        lines.append(f'• <a href="{html.escape(j.url, quote=True)}">'
                     f'{html.escape(j.title)}</a> — {html.escape(j.company)}'
                     f' ({html.escape(j.location)}){tag}')
    text = f"<b>{len(jobs)} fresh job(s)</b>"
    for line in lines:
        if len(text) + len(line) + 1 > LIMIT:
            yield text
            text = line
        else:
            text += "\n" + line
    yield text


def _ai_summary(jobs):
    """Optional Claude-written intro for the digest. Flag-gated, off by
    default; any failure just skips the summary — never the notification."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        client = anthropic.Anthropic()
        listing = "\n".join(f"- {j.title} at {j.company} ({j.location})"
                            for j in jobs[:50])
        r = client.messages.create(
            model=os.environ.get("DIGEST_MODEL", "claude-opus-4-8"),
            max_tokens=300,
            messages=[{"role": "user", "content":
                       "Write a 2-3 sentence plain-text summary of today's "
                       "fresh job matches for a job seeker, highlighting the "
                       "most promising ones:\n" + listing}])
        return next((b.text for b in r.content if b.type == "text"), None)
    except Exception as e:
        log.warning("AI digest summary failed: %s", e)
        return None


def _post(msgs):
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


def send(jobs, alerts=(), ai_digest=False):
    msgs = []
    if ai_digest and jobs:
        summary = _ai_summary(jobs)
        if summary:
            msgs.append("✨ " + html.escape(summary.strip()))
    if jobs:
        msgs.extend(_messages(jobs))
    if alerts:
        msgs.append("⚠️ <b>Health alerts</b>\n"
                    + "\n".join(html.escape(a) for a in alerts))
    if msgs:
        _post(msgs)


def send_text(text):
    _post([html.escape(text)])
