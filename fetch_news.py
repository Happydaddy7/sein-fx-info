#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
세인바이오 외환 대시보드 — 뉴스 자동 수집
Google News RSS에서 외환시장 관련 뉴스를 모아 news.json 생성.
외부 패키지 불필요 (표준 라이브러리만 사용) → GitHub Actions에서 바로 실행 가능.
"""
import json, re, html, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

KST = timezone(timedelta(hours=9))

# ── 수집 쿼리 (필요시 추가/수정) ──────────────────────────────
QUERIES = [
    "원달러 환율",
    "외환시장",
    "달러 강세 OR 달러 약세",
    "연준 금리 OR FOMC",
    "한국은행 기준금리",
]

# 중요도 가중 키워드 (제목에 있으면 상단 배치)
HOT = ["환율", "원/달러", "원달러", "1,4", "1,5", "연준", "FOMC", "금리 인상", "금리 인하",
       "한국은행", "달러", "외환보유", "위안", "엔화", "개입"]

# 제외 키워드 (환율 뉴스와 무관한 소음 제거)
SKIP = ["코인", "비트코인", "가상자산", "환율조작 영화", "게임"]

UA = {"User-Agent": "Mozilla/5.0 (compatible; SeinFXBot/1.0)"}


def fetch_rss(query: str):
    url = ("https://news.google.com/rss/search?q="
           + urllib.parse.quote(query) + "&hl=ko&gl=KR&ceid=KR:ko")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def clean_title(t: str):
    t = html.unescape(t or "")
    # Google News 제목 끝의 " - 언론사" 제거 (출처는 별도 필드 사용)
    return re.sub(r"\s+-\s+[^-]+$", "", t).strip()


def parse_items(xml_bytes: bytes):
    out = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return out
    for item in root.iter("item"):
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        pub = item.findtext("pubDate") or ""
        src_el = item.find("source")
        source = (src_el.text if src_el is not None else "") or ""
        try:
            dt = parsedate_to_datetime(pub).astimezone(KST)
        except Exception:
            continue
        out.append({"title": clean_title(title), "link": link,
                    "source": source.strip(), "dt": dt})
    return out


def norm(t: str):
    """제목 유사 중복 제거용 정규화 키"""
    return re.sub(r"[^\w가-힣]", "", t)[:30]


def main():
    now = datetime.now(KST)
    cutoff = now - timedelta(days=3)          # 최근 3일치만
    seen, items = set(), []

    for q in QUERIES:
        try:
            for it in parse_items(fetch_rss(q)):
                if it["dt"] < cutoff:
                    continue
                if any(k in it["title"] for k in SKIP):
                    continue
                key = norm(it["title"])
                if not key or key in seen:
                    continue
                seen.add(key)
                it["hot"] = sum(1 for k in HOT if k in it["title"])
                items.append(it)
        except Exception as e:
            print(f"[warn] '{q}' 수집 실패: {e}")

    # 정렬: 중요도 → 최신순, 상위 15건
    items.sort(key=lambda x: (-x["hot"], -x["dt"].timestamp()))
    top = items[:15]
    top.sort(key=lambda x: -x["dt"].timestamp())   # 최종 표시는 최신순

    data = {
        "updated": now.strftime("%Y-%m-%d %H:%M"),
        "items": [{"title": i["title"], "link": i["link"], "source": i["source"],
                   "time": i["dt"].strftime("%m/%d %H:%M"), "hot": i["hot"] >= 2}
                  for i in top],
    }
    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"news.json 생성: {len(top)}건 / 기준 {data['updated']} KST")


if __name__ == "__main__":
    main()
