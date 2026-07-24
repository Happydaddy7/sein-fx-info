#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
세인 FX — Slack #0-09-외환 채널의 [집계] 줄을 읽어 purchases.json 갱신

읽는 형식 (황유나 과장이 표 아래 한 줄로 게시):
  [집계] 2026-07-22 | 구매 120,000 | 환율 1483.50 | 사용 240,000 | 잔액 5,020,000

필요 환경변수:
  SLACK_BOT_TOKEN : Slack 앱 토큰 (xoxb-...) — 채널 읽기 권한(channels:history 또는 groups:history)
  SLACK_CHANNEL   : 채널 ID (기본값 C0B70ASGC84 = #0-09-외환)

동작:
  - 최근 30일치 메시지에서 [집계] 줄을 모두 수집
  - 이번 달(month) 것만 골라 log 재구성 (날짜 중복 시 최신 값 우선)
  - holdings = 가장 최근 날짜의 '잔액'
  - target = 이번 달 '사용' 합계 (실제 나간 돈). 단, MANUAL_TARGET 지정 시 그 값 우선
"""
import json, os, re, sys, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
CHANNEL = os.environ.get("SLACK_CHANNEL", "C0B70ASGC84")
TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
PURCHASES = "purchases.json"

# [집계] 줄 파싱: 항목 순서가 바뀌어도, 일부가 빠져도 인식
LINE_RE = re.compile(r"\[집계\]")
DATE_RE = re.compile(r"(\d{4})[-.\/](\d{1,2})[-.\/](\d{1,2})")


def num(text):
    """'120,000' / '1483.50' → 숫자"""
    t = text.replace(",", "").strip()
    try:
        return float(t)
    except ValueError:
        return None


def parse_line(text):
    """[집계] 줄 하나를 dict로. 실패 시 None"""
    if not LINE_RE.search(text):
        return None
    m = DATE_RE.search(text)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    date = f"{y:04d}-{mo:02d}-{d:02d}"

    out = {"date": date, "amount": None, "rate": None, "used": None, "balance": None}

    # 환율 먼저 (구매 환율 / 환율 모두 인식) — '구매'가 여러 번 나와도 헷갈리지 않게
    mm = re.search(r"환율\s*[:：]?\s*([\d,]+(?:\.\d+)?)", text)
    if mm:
        out["rate"] = num(mm.group(1))

    # 구매액: 달러 표기($ 있거나, 원화(₩)가 아닌 것) 우선
    #   "구매 $120,000" / "구매 120,000" 은 O,  "구매 ₩176,956,200" 은 제외
    for mm in re.finditer(r"구매\s*(?!환율)[:：]?\s*(₩|\$)?\s*([\d,]+(?:\.\d+)?)", text):
        cur, val = mm.group(1), num(mm.group(2))
        if cur == "₩":
            continue                     # 원화 금액은 건너뜀
        if val is not None:
            out["amount"] = val
            break                        # 첫 번째 달러 금액만 사용

    for key, kw in (("used", "사용"), ("balance", "잔액")):
        mm = re.search(kw + r"\s*[:：]?\s*[₩\$]?\s*([\d,]+(?:\.\d+)?)", text)
        if mm:
            out[key] = num(mm.group(1))

    if out["amount"] is None and out["balance"] is None:
        return None
    return out


def slack_history(days=30):
    """최근 N일 메시지 텍스트 목록"""
    if not TOKEN:
        print("[error] SLACK_BOT_TOKEN 미설정 — Slack 조회를 건너뜁니다.")
        return []
    oldest = (datetime.now(KST) - timedelta(days=days)).timestamp()
    url = "https://slack.com/api/conversations.history?" + urllib.parse.urlencode(
        {"channel": CHANNEL, "limit": 200, "oldest": f"{oldest:.6f}"})
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())
    if not data.get("ok"):
        print(f"[error] Slack API: {data.get('error')}")
        return []
    return [m.get("text", "") for m in data.get("messages", [])]


def main():
    texts = slack_history()
    records = {}
    for t in texts:
        for line in t.split("\n"):
            rec = parse_line(line)
            if rec:
                # 같은 날짜가 여러 번이면 나중(더 최신) 것 유지
                records.setdefault(rec["date"], rec)
    if not records:
        print("[집계] 줄을 찾지 못했습니다. purchases.json 변경 없음.")
        return

    # 기존 파일 로드 (month 기준)
    try:
        P = json.load(open(PURCHASES, encoding="utf-8"))
    except Exception:
        P = {"month": datetime.now(KST).strftime("%Y-%m"), "log": []}
    month = P.get("month") or datetime.now(KST).strftime("%Y-%m")

    # 이번 달 것만
    cur = sorted([r for d, r in records.items() if d.startswith(month)],
                 key=lambda r: r["date"])
    if not cur:
        print(f"{month} 해당 [집계] 줄 없음. 변경 없음.")
        return

    P["log"] = [{"date": r["date"],
                 "amount": int(r["amount"] or 0),
                 "rate": r["rate"] or 0,
                 "note": ""} for r in cur if r["amount"]]

    last = cur[-1]
    if last.get("balance"):
        P["holdings"] = int(last["balance"])
        P["holdings_note"] = f"{last['date']} 기준 선물환 잔액 (Slack 자동)"

    used_sum = sum(int(r["used"]) for r in cur if r.get("used"))
    if used_sum and not os.environ.get("MANUAL_TARGET"):
        P["target"] = used_sum
        P["target_note"] = f"{month} 사용액 누계 (Slack 자동)"
    elif os.environ.get("MANUAL_TARGET"):
        P["target"] = int(os.environ["MANUAL_TARGET"])

    P["updated_from_slack"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    with open(PURCHASES, "w", encoding="utf-8") as f:
        json.dump(P, f, ensure_ascii=False, indent=1)

    bought = sum(x["amount"] for x in P["log"])
    print(f"purchases.json 갱신: {len(P['log'])}건 / 매입누계 ${bought:,} / "
          f"목표 ${P.get('target',0):,} / 잔액 ${P.get('holdings',0):,}")


if __name__ == "__main__":
    main()
