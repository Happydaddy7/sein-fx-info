#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
세인 FX — 예측 기록 & 채점
매일 실행되어:
  1) 오늘의 예측(범위·방향)을 계산해 forecast_log.json에 추가
  2) 아직 실제값이 비어 있는 과거 예측에 실제 환율을 채우고 적중 판정

예측 로직은 대시보드(index.html)와 동일:
  - 최근 2주 일평균 등락폭으로 밴드 폭
  - news.json의 outlook.dir 로 상단/하단 치우침
데이터는 Frankfurter(ECB) USD/KRW 종가 사용.
표준 라이브러리만 사용.
"""
import json, os, math, urllib.request
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
FX = "https://api.frankfurter.dev/v1"
LOG = "forecast_log.json"
NEWS = "news.json"


def krw_series(days=20):
    """최근 N일 USD/KRW 종가 [(date, rate), ...] 오름차순"""
    end = datetime.now(KST).date()
    start = end - timedelta(days=days)
    url = f"{FX}/{start}..{end}?from=USD&to=KRW"
    with urllib.request.urlopen(url, timeout=20) as r:
        d = json.loads(r.read())
    rates = d.get("rates", {})
    return sorted(((dt, v["KRW"]) for dt, v in rates.items()), key=lambda x: x[0])


def news_dir():
    try:
        d = json.load(open(NEWS, encoding="utf-8"))
        return (d.get("outlook") or {}).get("dir", "neutral")
    except Exception:
        return "neutral"


def make_band(today, vol, direction, days):
    half = vol * math.sqrt(days)
    if direction == "up":
        lo, hi = today - half * 0.5, today + half * 1.3
    elif direction == "down":
        lo, hi = today - half * 1.3, today + half * 0.5
    else:
        lo, hi = today - half, today + half
    return round(lo), round(hi)


def load_log():
    try:
        return json.load(open(LOG, encoding="utf-8"))
    except Exception:
        return {"records": []}


def main():
    series = krw_series(20)
    if len(series) < 3:
        print("환율 데이터 부족, 종료")
        return
    rate_by_date = dict(series)
    today_date, today_rate = series[-1]

    # 변동성: 하루 평균 등락폭
    vals = [v for _, v in series]
    moves = [abs(vals[i] - vals[i - 1]) for i in range(1, len(vals))]
    vol = sum(moves) / len(moves)

    direction = news_dir()
    t_lo, t_hi = make_band(today_rate, vol, direction, 1)   # 오늘(익일) 범위
    w_lo, w_hi = make_band(today_rate, vol, direction, 5)   # 주간 범위

    log = load_log()
    recs = log["records"]

    # 1) 오늘 예측 추가 (같은 기준일이 이미 있으면 갱신)
    entry = {
        "made_on": today_date,          # 예측을 만든 날(기준 환율일)
        "base_rate": round(today_rate, 2),
        "dir": direction,
        "today_band": [t_lo, t_hi],     # 다음 거래일 예상
        "week_band": [w_lo, w_hi],
        "actual": None,                 # 다음 거래일 실제 (나중에 채움)
        "hit": None,                    # 적중 여부
        "dir_hit": None                 # 방향 적중
    }
    recs = [r for r in recs if r["made_on"] != today_date]
    recs.append(entry)

    # 2) 과거 예측 채점: actual 이 비어 있고, 그 다음 거래일 환율이 존재하면 채움
    dates_sorted = [d for d, _ in series]
    for r in recs:
        if r["actual"] is not None:
            continue
        base = r["made_on"]
        # made_on 다음으로 존재하는 거래일
        later = [d for d in dates_sorted if d > base]
        if not later:
            continue
        nxt = later[0]
        actual = rate_by_date[nxt]
        r["actual_on"] = nxt
        r["actual"] = round(actual, 2)
        lo, hi = r["today_band"]
        r["hit"] = bool(lo <= actual <= hi)
        # 방향 적중: 기준 대비 실제가 오르면 up, 내리면 down
        moved = "up" if actual > r["base_rate"] else ("down" if actual < r["base_rate"] else "flat")
        if r["dir"] == "neutral":
            r["dir_hit"] = None
        else:
            r["dir_hit"] = bool(moved == r["dir"])

    # 최근 60개만 유지
    recs = sorted(recs, key=lambda r: r["made_on"])[-60:]
    log["records"] = recs
    log["updated"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    # 요약 통계 (채점된 것만)
    scored = [r for r in recs if r["actual"] is not None]
    if scored:
        hit = sum(1 for r in scored if r["hit"])
        dscored = [r for r in scored if r["dir_hit"] is not None]
        dhit = sum(1 for r in dscored if r["dir_hit"])
        log["summary"] = {
            "scored": len(scored),
            "hit": hit,
            "hit_rate": round(hit / len(scored) * 100),
            "dir_scored": len(dscored),
            "dir_hit": dhit,
            "dir_rate": round(dhit / len(dscored) * 100) if dscored else None,
        }

    json.dump(log, open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    s = log.get("summary", {})
    print(f"forecast_log.json: 기록 {len(recs)}건 / 채점 {s.get('scored',0)}건 / "
          f"범위적중 {s.get('hit_rate','-')}% / 방향적중 {s.get('dir_rate','-')}%")


if __name__ == "__main__":
    main()
