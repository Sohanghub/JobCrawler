import requests

# ponytail: P2 adds per-domain throttling + ETag/hash page cache here
USER_AGENT = "JobCrawler/0.1 (personal job-search; contact: sohangandla20@gmail.com)"


def session():
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s
