"""합성 샘플 CSV 생성기 — 파이프라인 동작 확인 전용.

여기서 나오는 숫자는 전부 가짜다. 실제 시장 분석에 쓰면 안 된다.
LOCALDATA 숙박 인허가 CSV의 헤더 구조만 흉내 낸다.
"""

from __future__ import annotations

import csv
import os
import random
from datetime import date, timedelta

HEADER = [
    "번호", "개방서비스명", "개방서비스아이디", "개방자치단체코드", "관리번호",
    "인허가일자", "영업상태구분코드", "영업상태명", "상세영업상태코드", "상세영업상태명",
    "폐업일자", "상세영업상태변경일자", "소재지전체주소", "도로명전체주소",
    "사업장명", "업태구분명", "객실수",
]

REGIONS = {
    "제주시": ["애월읍", "한림읍", "구좌읍", "조천읍", "한경면", "노형동", "연동", "이도이동", "일도이동", "삼양동"],
    "서귀포시": ["성산읍", "대정읍", "안덕면", "표선면", "남원읍", "중문동", "서홍동", "동홍동", "대륜동"],
}
SERVICES = [("농어촌민박업", 0.55), ("숙박업", 0.33), ("관광숙박업", 0.12)]


def _pick_service(rng: random.Random) -> str:
    r, acc = rng.random(), 0.0
    for name, w in SERVICES:
        acc += w
        if r <= acc:
            return name
    return SERVICES[-1][0]


def generate(path: str, n: int = 1400, seed: int = 20260908) -> str:
    rng = random.Random(seed)
    today = date.today()
    start = date(2011, 1, 1)
    span = (today - start).days

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        for i in range(1, n + 1):
            sigungu = rng.choices(list(REGIONS), weights=[0.58, 0.42])[0]
            emd = rng.choice(REGIONS[sigungu])
            service = _pick_service(rng)
            # 개업은 최근으로 갈수록 잦아지도록 가중
            opened = start + timedelta(days=int(span * rng.random() ** 0.65))
            closed, status = "", "영업/정상"
            # 오래된 업소일수록 폐업 확률이 높다
            age_years = (today - opened).days / 365.25
            if rng.random() < min(0.06 * age_years, 0.5):
                gap = rng.randint(180, max(200, (today - opened).days))
                cd = opened + timedelta(days=gap)
                if cd < today:
                    closed, status = cd.strftime("%Y%m%d"), "폐업"
            elif rng.random() < 0.03:
                status = "휴업"
            w.writerow([
                i, service, "03_11_00_P", "6500000", f"SAMPLE-{i:05d}",
                opened.strftime("%Y%m%d"),
                "1" if status == "영업/정상" else "3",
                "영업/정상" if status != "폐업" else "폐업",
                "01", status, closed,
                closed or opened.strftime("%Y%m%d"),
                f"제주특별자치도 {sigungu} {emd} {rng.randint(1, 2000)}",
                f"제주특별자치도 {sigungu} 표본로 {rng.randint(1, 300)}",
                f"[샘플]{emd}숙소{i:04d}", "", rng.randint(1, 12),
            ])
    return path


if __name__ == "__main__":
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else "jeju-str/data/sample/SAMPLE_lodging.csv"
    print("생성:", generate(out))
