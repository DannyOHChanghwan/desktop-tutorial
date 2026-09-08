"""제주 숙박 공급 지표 산출.

시계열은 '영업신고 유효 업소 수'(누적 인허가 − 누적 폐업)로 정의한다.
휴업 이력은 원본 데이터에 기간이 남지 않으므로 시계열에서 분리하지 못한다.
현재 시점 지표에서만 영업중/휴업을 구분한다.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import date

from common import Lodging


def ym(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def month_range(start: str, end: str) -> list[str]:
    sy, sm = (int(x) for x in start.split("-"))
    ey, em = (int(x) for x in end.split("-"))
    out = []
    while (sy, sm) <= (ey, em):
        out.append(f"{sy:04d}-{sm:02d}")
        sm += 1
        if sm == 13:
            sy, sm = sy + 1, 1
    return out


def shift_months(anchor: str, delta: int) -> str:
    y, m = (int(x) for x in anchor.split("-"))
    total = y * 12 + (m - 1) + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _effective_close(rec: Lodging) -> date | None:
    """폐업으로 확정된 건에 한해 폐업일을 인정한다."""
    if rec.active or rec.dormant:
        return None
    return rec.closed


def monthly_series(
    records: list[Lodging], since: str, until: str, key=lambda r: r.service
) -> tuple[list[str], dict[str, list[int]]]:
    """월별 '영업신고 유효 업소 수' 시계열을 그룹별로 만든다."""
    months = month_range(since, until)
    index = {m: i for i, m in enumerate(months)}
    groups = sorted({key(r) for r in records})
    delta = {g: [0] * len(months) for g in groups}
    base = dict.fromkeys(groups, 0)  # since 이전에 이미 열려 있던 수

    for rec in records:
        g = key(rec)
        if rec.opened is None:
            continue
        om = ym(rec.opened)
        cm = ym(c) if (c := _effective_close(rec)) else None
        if cm and cm < since:
            continue  # 관측 구간 시작 전에 이미 폐업
        if om < since:
            base[g] += 1
        elif om in index:
            delta[g][index[om]] += 1
        else:
            continue  # 관측 구간 이후 개업
        if cm and cm in index:
            delta[g][index[cm]] -= 1

    series: dict[str, list[int]] = {}
    for g in groups:
        running = base[g]
        row = []
        for i in range(len(months)):
            running += delta[g][i]
            row.append(running)
        series[g] = row
    return months, series


def region_table(records: list[Lodging], until: str) -> list[dict]:
    """읍면동별 현재 공급과 최근 12개월 진입/이탈."""
    window_start = shift_months(until, -11)
    agg: dict[tuple[str, str], dict] = defaultdict(
        lambda: {
            "active": 0,
            "dormant": 0,
            "closed_total": 0,
            "new_12m": 0,
            "closed_12m": 0,
            "rooms": 0,
            "tenure": [],
            "by_service": Counter(),
        }
    )
    today = date.today()

    for rec in records:
        a = agg[(rec.sigungu, rec.emd)]
        close = _effective_close(rec)
        if rec.active:
            a["active"] += 1
            a["by_service"][rec.service] += 1
            if rec.rooms:
                a["rooms"] += rec.rooms
            if rec.opened:
                a["tenure"].append((today - rec.opened).days / 365.25)
        elif rec.dormant:
            a["dormant"] += 1
        else:
            a["closed_total"] += 1
        if rec.opened and window_start <= ym(rec.opened) <= until:
            a["new_12m"] += 1
        if close and window_start <= ym(close) <= until:
            a["closed_12m"] += 1

    rows = []
    for (sigungu, emd), a in agg.items():
        active = a["active"]
        rows.append(
            {
                "sigungu": sigungu,
                "emd": emd,
                "region": f"{sigungu} {emd}",
                "active": active,
                "dormant": a["dormant"],
                "closed_total": a["closed_total"],
                "new_12m": a["new_12m"],
                "closed_12m": a["closed_12m"],
                "net_12m": a["new_12m"] - a["closed_12m"],
                # 최근 12개월 이탈률: 기간 시작 시점 모집단 근사(현재 영업중 + 기간 내 폐업)
                "churn_12m": round(
                    a["closed_12m"] / (active + a["closed_12m"]) * 100, 1
                )
                if (active + a["closed_12m"])
                else 0.0,
                "rooms": a["rooms"],
                "median_tenure": round(statistics.median(a["tenure"]), 1)
                if a["tenure"]
                else None,
                "by_service": dict(a["by_service"]),
            }
        )
    rows.sort(key=lambda r: (-r["active"], r["region"]))
    return rows


def summarize(records: list[Lodging], until: str) -> dict:
    window_start = shift_months(until, -11)
    active = [r for r in records if r.active]
    by_service = Counter(r.service for r in active)
    by_sigungu = Counter(r.sigungu for r in active)
    new_12m = sum(
        1 for r in records if r.opened and window_start <= ym(r.opened) <= until
    )
    closed_12m = sum(
        1
        for r in records
        if (c := _effective_close(r)) and window_start <= ym(c) <= until
    )
    tenures = [
        (date.today() - r.opened).days / 365.25 for r in active if r.opened
    ]
    return {
        "total_records": len(records),
        "active": len(active),
        "dormant": sum(1 for r in records if r.dormant),
        "closed": sum(1 for r in records if not r.active and not r.dormant),
        "by_service": dict(by_service.most_common()),
        "by_sigungu": dict(by_sigungu.most_common()),
        "new_12m": new_12m,
        "closed_12m": closed_12m,
        "net_12m": new_12m - closed_12m,
        "median_tenure": round(statistics.median(tenures), 1) if tenures else None,
        "rooms_known": sum(r.rooms for r in active if r.rooms),
        "window": [window_start, until],
    }


def seasonality(rows: list[dict[str, str]]) -> dict[str, float] | None:
    """선택 입력: 월별 입도 관광객 CSV -> 월(1~12)별 계절성 지수(평균=100)."""
    month_col = next(
        (k for k in rows[0] if k and any(t in k for t in ("연월", "년월", "기준월", "month"))),
        None,
    )
    value_col = next(
        (
            k
            for k in rows[0]
            if k and any(t in k for t in ("관광객", "방문객", "입도", "합계", "계", "visitors"))
        ),
        None,
    )
    if not month_col or not value_col:
        return None

    buckets: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        raw_m, raw_v = (row.get(month_col) or ""), (row.get(value_col) or "")
        digits = "".join(ch for ch in raw_m if ch.isdigit())
        if len(digits) < 6:
            continue
        month = int(digits[4:6])
        num = "".join(ch for ch in raw_v if ch.isdigit())
        if not (1 <= month <= 12 and num):
            continue
        buckets[month].append(float(num))
    if len(buckets) < 12:
        return None
    means = {m: statistics.mean(v) for m, v in buckets.items()}
    overall = statistics.mean(means.values())
    return {str(m): round(means[m] / overall * 100, 1) for m in sorted(means)}
