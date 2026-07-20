#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
세인바이오 외환 대시보드 — 뉴스 자동 수집 (v2)
Google News RSS에서 외환에 영향을 주는 뉴스만 골라, 환율 상승/하락 요인으로 분류해 news.json 생성.
- 원/달러 '상승' = 원화 약세 = 달러 강세 → 수입회사엔 불리(조달비용↑) → up
- 원/달러 '하락' = 원화 강세 = 달러 약세 → 수입회사엔 유리(조달비용↓) → down
외부 패키지 불필요 (표준 라이브러리만 사용).
"""
import json, re, html, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

KST = timezone(timedelta(hours=9))

# ── 수집 쿼리 ─────────────────────────────────────────────
QUERIES = [
    "원달러 환율",
    "환율 전망",
    "달러 강세 OR 달러 약세",
    "연준 금리 OR FOMC",
    "한국은행 기준금리",
    "위안화 환율",
]

# ── FX 관련성 필터: 아래 중 하나라도 제목에 있어야 '외환 뉴스'로 인정 ──
FX_CORE = ["환율", "원/달러", "원달러", "달러화", "달러", "연준", "FOMC", "한국은행",
           "기준금리", "외환", "위안", "엔화", "외국인", "원화", "킹달러", "외화"]

# ── 환율 상승요인 (원화 약세 / 달러 강세) — 수입회사엔 불리 ──
UP = ["달러 강세", "달러 상승", "달러 급등", "원화 약세", "원화 하락", "환율 상승",
      "환율 급등", "환율 오름", "환율 연고점", "환율 고점", "연준 매파", "매파",
      "금리 인상", "긴축", "안전자산 선호", "위험회피", "위험 회피", "달러 사재기",
      "무역적자", "경상수지 적자", "외국인 매도", "자본 유출", "지정학", "전쟁",
      "1,5", "1,6", "고환율", "킹달러", "위안화 약세", "엔화 약세", "수입물가 상승",
      "달러 매수", "환율 방어", "외환보유액 감소"]

# ── 환율 하락요인 (원화 강세 / 달러 약세) — 수입회사엔 유리 ──
DOWN = ["달러 약세", "달러 하락", "달러 급락", "원화 강세", "원화 상승", "환율 하락",
        "환율 급락", "환율 내림", "환율 안정", "연준 비둘기", "비둘기", "금리 인하",
        "완화", "위험선호", "위험 선호", "외국인 매수", "자본 유입", "무역흑자",
        "경상수지 흑자", "수출 호조", "달러 매도", "저환율", "위안화 강세",
        "엔화 강세", "외환보유액 증가", "환율 하향"]

SKIP = ["코인", "비트코인", "가상자산", "영화", "게임", "드라마", "스포츠"]
UA = {"User-Agent": "Mozilla/5.0 (compatible; SeinFXBot/2.0)"}


def fetch_rss(query):
    url = ("https://news.google.com/rss/search?q="
           + urllib.parse.quote(query) + "&hl=ko&gl=KR&ceid=KR:ko")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def clean_title(t):
    t = html.unescape(t or "")
    return re.sub(r"\s+-\s+[^-]+$", "", t).strip()


def classify(title):
    """상승/하락/중립 분류 + 강도"""
    u = sum(1 for k in UP if k in title)
    d = sum(1 for k in DOWN if k in title)
    if u > d:
        return "up", u - d
    if d > u:
        return "down", d - u
    return "neutral", 0


def parse_items(xml_bytes):
    out = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return out
    for item in root.iter("item"):
        title = clean_title(item.findtext("title") or "")
        link = item.findtext("link") or ""
        pub = item.findtext("pubDate") or ""
        src_el = item.find("source")
        source = (src_el.text if src_el is not None else "") or ""
        try:
            dt = parsedate_to_datetime(pub).astimezone(KST)
        except Exception:
            continue
        out.append({"title": title, "link": link, "source": source.strip(), "dt": dt})
    return out


def norm(t):
    return re.sub(r"[^\w가-힣]", "", t)[:30]


def main():
    now = datetime.now(KST)
    cutoff = now - timedelta(days=3)
    seen, items = set(), []

    for q in QUERIES:
        try:
            for it in parse_items(fetch_rss(q)):
                if it["dt"] < cutoff:
                    continue
                title = it["title"]
                # 1) 소음 제거
                if any(k in title for k in SKIP):
                    continue
                # 2) FX 관련성 필터 — 핵심 단어 없으면 제외
                if not any(k in title for k in FX_CORE):
                    continue
                # 3) 중복 제거
                key = norm(title)
                if not key or key in seen:
                    continue
                seen.add(key)
                # 4) 방향 분류
                direction, strength = classify(title)
                it["dir"] = direction
                it["strength"] = strength
                items.append(it)
        except Exception as e:
            print(f"[warn] '{q}' 수집 실패: {e}")

    # 정렬: 방향성 뚜렷한 것(강도↑) 우선, 그다음 최신
    items.sort(key=lambda x: (-x["strength"], -x["dt"].timestamp()))
    top = items[:18]
    top.sort(key=lambda x: -x["dt"].timestamp())

    up_n = sum(1 for i in top if i["dir"] == "up")
    down_n = sum(1 for i in top if i["dir"] == "down")

    data = {
        "updated": now.strftime("%Y-%m-%d %H:%M"),
        "summary": {"up": up_n, "down": down_n, "neutral": len(top) - up_n - down_n},
        "items": [{"title": i["title"], "link": i["link"], "source": i["source"],
                   "time": i["dt"].strftime("%m/%d %H:%M"),
                   "dir": i["dir"], "strength": i["strength"]}
                  for i in top],
    }
    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"news.json: 총 {len(top)}건 (상승요인 {up_n} / 하락요인 {down_n} / 중립 {len(top)-up_n-down_n}) @ {data['updated']} KST")


if __name__ == "__main__":
    main()
