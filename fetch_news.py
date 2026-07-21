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

# ── 공신력 매체 화이트리스트 (이 매체들만 표시) ──
# 통신사·경제지·주요 일간지 중심. 부분일치로 판정.
TRUSTED = [
    "연합뉴스", "연합인포맥스", "인포맥스", "뉴시스", "뉴스1",
    "한국경제", "매일경제", "서울경제", "머니투데이", "이데일리",
    "파이낸셜뉴스", "헤럴드경제", "아시아경제", "조선비즈",
    "KBS", "MBC", "SBS", "YTN", "연합뉴스TV",
    "조선일보", "중앙일보", "동아일보", "한겨레", "경향신문", "한국일보",
    "블룸버그", "로이터", "Bloomberg", "Reuters",
]
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
                # 3) 공신력 매체만 (source에 신뢰 매체명이 포함돼야)
                src = it["source"]
                if not any(t in src for t in TRUSTED):
                    continue
                # 4) 중복 제거
                key = norm(title)
                if not key or key in seen:
                    continue
                seen.add(key)
                # 5) 방향 분류
                direction, strength = classify(title)
                it["dir"] = direction
                it["strength"] = strength
                items.append(it)
        except Exception as e:
            print(f"[warn] '{q}' 수집 실패: {e}")

    # 정렬: 방향성 뚜렷한 것(강도↑) 우선, 그다음 최신
    items.sort(key=lambda x: (-x["strength"], -x["dt"].timestamp()))
    top = items[:10]
    top.sort(key=lambda x: -x["dt"].timestamp())

    up_n = sum(1 for i in top if i["dir"] == "up")
    down_n = sum(1 for i in top if i["dir"] == "down")
    up_str = sum(i["strength"] for i in top if i["dir"] == "up")
    down_str = sum(i["strength"] for i in top if i["dir"] == "down")

    # 뉴스 기반 방향 요약 (예측이 아닌, 뉴스가 어느 쪽으로 기울었는지)
    net = (up_n + up_str) - (down_n + down_str)
    reasons_up = [i["title"] for i in top if i["dir"] == "up"][:2]
    reasons_down = [i["title"] for i in top if i["dir"] == "down"][:2]
    if net >= 3:
        outlook_dir = "up"
        line1 = f"상승요인 우세 (상승 {up_n} vs 하락 {down_n})."
        line2 = "원화 약세·달러 강세 압력 → 조달비용 상승 방향."
        line3 = "환율 오름세 대비, 필요분 조기 확보 검토."
    elif net <= -3:
        outlook_dir = "down"
        line1 = f"하락요인 우세 (하락 {down_n} vs 상승 {up_n})."
        line2 = "달러 약세·원화 강세 흐름 → 조달비용 하락 방향."
        line3 = "환율 하락 시 매입 유리, 저점 분할 매수 유효."
    else:
        outlook_dir = "neutral"
        line1 = f"상승·하락 요인 혼재 (상승 {up_n} vs 하락 {down_n})."
        line2 = "뚜렷한 방향성 없이 등락 반복 가능성."
        line3 = "평소 페이스 유지하며 지표 발표 주시."

    data = {
        "updated": now.strftime("%Y-%m-%d %H:%M"),
        "summary": {"up": up_n, "down": down_n, "neutral": len(top) - up_n - down_n},
        "outlook": {"dir": outlook_dir, "lines": [line1, line2, line3]},
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
