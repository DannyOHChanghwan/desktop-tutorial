"""LOCALDATA 숙박 인허가 CSV 공통 처리.

표준 라이브러리만 사용한다 (설치 비용 0).
LOCALDATA / 공공데이터포털의 숙박 관련 인허가 파일은 배포처에 따라
인코딩(CP949·UTF-8)과 컬럼 순서가 조금씩 다르므로, 헤더 이름으로 관대하게 매핑한다.
"""

from __future__ import annotations

import csv
import glob
import os
import re
from dataclasses import dataclass
from datetime import date

# ---------------------------------------------------------------- 인코딩

ENCODINGS = ("utf-8-sig", "cp949", "euc-kr", "utf-8")


def read_rows(path: str) -> list[dict[str, str]]:
    """CSV를 딕셔너리 리스트로 읽는다. 인코딩은 순서대로 시도."""
    last = None
    for enc in ENCODINGS:
        try:
            with open(path, newline="", encoding=enc) as fh:
                rows = list(csv.DictReader(fh))
            if rows and any(k and "�" not in k for k in rows[0]):
                return rows
        except (UnicodeDecodeError, LookupError) as exc:
            last = exc
    if last:
        raise last
    return []


# ---------------------------------------------------------------- 컬럼 매핑

# 원하는 필드 -> 헤더에 나타날 수 있는 이름들(부분일치, 앞에 있을수록 우선)
# LOCALDATA는 벌크 CSV(한글 헤더)와 Open API(영문 필드) 헤더가 다르므로 둘 다 받는다.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "service": ("개방서비스명", "업종명", "서비스명", "opnSvcNm"),
    "name": ("사업장명", "업소명", "상호명", "상호", "bplcNm"),
    "status": ("상세영업상태명", "영업상태명", "영업상태구분명", "dtlStateNm", "trdStateNm"),
    "opened": ("인허가일자", "신고일자", "허가일자", "등록일자", "apvPermYmd"),
    "closed": ("폐업일자", "dcbYmd"),
    "status_changed": ("상세영업상태변경일자", "영업상태변경일자", "최종수정시점", "lastModTs"),
    "addr_jibun": ("소재지전체주소", "지번주소", "소재지주소", "siteWhlAddr"),
    "addr_road": ("도로명전체주소", "도로명주소", "rdnWhlAddr"),
    "rooms": ("객실수", "객실 수", "roomCnt"),
}


def build_colmap(header: list[str]) -> dict[str, str]:
    """실제 헤더에서 필드 -> 컬럼명 매핑을 만든다."""
    colmap: dict[str, str] = {}
    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            hit = next((h for h in header if h and alias in h), None)
            if hit:
                colmap[field] = hit
                break
    return colmap


# ---------------------------------------------------------------- 값 파서

_DATE_RE = re.compile(r"(\d{4})\D?(\d{2})\D?(\d{2})")


def parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    m = _DATE_RE.search(raw.strip())
    if not m:
        return None
    y, mo, d = (int(g) for g in m.groups())
    if not (1900 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31):
        return None
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def parse_int(raw: str | None) -> int | None:
    if not raw:
        return None
    digits = re.sub(r"[^0-9]", "", raw)
    return int(digits) if digits else None


# ---------------------------------------------------------------- 업종 분류

SERVICE_CANON: tuple[tuple[str, str], ...] = (
    ("농어촌민박", "농어촌민박"),
    ("관광숙박", "관광숙박업"),
    ("외국인관광도시민박", "외국인관광도시민박"),
    ("호스텔", "관광숙박업"),
    ("숙박업", "숙박업"),
)


def canon_service(raw: str | None, fallback: str = "기타숙박") -> str:
    text = (raw or "").strip()
    for needle, canon in SERVICE_CANON:
        if needle in text:
            return canon
    return text or fallback


# ---------------------------------------------------------------- 주소 파싱

# 2006년 이전 주소에는 폐지된 북제주군/남제주군이 남아 있다.
SIGUNGU_MAP = {
    "제주시": "제주시",
    "서귀포시": "서귀포시",
    "북제주군": "제주시",
    "남제주군": "서귀포시",
}
_EMD_RE = re.compile(r"^[가-힣]{1,8}[0-9]?(읍|면|동)$")
_JEJU_RE = re.compile(r"제주(특별자치)?도|제주시|서귀포시")


def is_jeju(*addrs: str | None) -> bool:
    return any(_JEJU_RE.search(a) for a in addrs if a)


def parse_region(*addrs: str | None) -> tuple[str, str]:
    """(시군구, 읍면동)을 뽑는다. 못 찾으면 '미상'."""
    for addr in addrs:
        if not addr:
            continue
        tokens = addr.replace("　", " ").split()
        sigungu = ""
        for i, tok in enumerate(tokens):
            if not sigungu and tok in SIGUNGU_MAP:
                sigungu = SIGUNGU_MAP[tok]
                continue
            if sigungu and _EMD_RE.match(tok):
                return sigungu, tok
        if sigungu:
            return sigungu, "미상"
    return "미상", "미상"


# ---------------------------------------------------------------- 레코드

ACTIVE_STATUS = ("영업", "정상")
DORMANT_STATUS = ("휴업",)


@dataclass(frozen=True, slots=True)
class Lodging:
    name: str
    service: str
    sigungu: str
    emd: str
    opened: date | None
    closed: date | None
    active: bool
    dormant: bool
    rooms: int | None

    @property
    def region(self) -> str:
        return f"{self.sigungu} {self.emd}"


def _status_flags(status: str) -> tuple[bool, bool]:
    """(영업중, 휴업) 판정. 폐업·취소·말소는 둘 다 False."""
    if any(k in status for k in DORMANT_STATUS):
        return False, True
    if "폐업" in status or "취소" in status or "말소" in status or "만료" in status:
        return False, False
    if any(k in status for k in ACTIVE_STATUS):
        return True, False
    return False, False


def row_to_lodging(row: dict[str, str], colmap: dict[str, str]) -> Lodging | None:
    def get(field: str) -> str:
        col = colmap.get(field)
        return (row.get(col) or "").strip() if col else ""

    addr_jibun, addr_road = get("addr_jibun"), get("addr_road")
    if not is_jeju(addr_jibun, addr_road):
        return None

    status = get("status")
    active, dormant = _status_flags(status)

    closed = parse_date(get("closed"))
    if closed is None and not active and not dormant:
        # 폐업일자가 비어 있으면 상태변경일자로 대체한다.
        closed = parse_date(get("status_changed"))

    sigungu, emd = parse_region(addr_jibun, addr_road)
    return Lodging(
        name=get("name") or "(무명)",
        service=canon_service(get("service")),
        sigungu=sigungu,
        emd=emd,
        opened=parse_date(get("opened")),
        closed=closed,
        active=active,
        dormant=dormant,
        rooms=parse_int(get("rooms")),
    )


def load_dir(path: str) -> tuple[list[Lodging], list[str]]:
    """디렉터리 안의 모든 CSV를 읽어 제주 숙박 레코드로 변환한다."""
    files = sorted(glob.glob(os.path.join(path, "**", "*.csv"), recursive=True))
    records: list[Lodging] = []
    notes: list[str] = []
    for fp in files:
        rows = read_rows(fp)
        if not rows:
            notes.append(f"{os.path.basename(fp)}: 빈 파일 — 건너뜀")
            continue
        colmap = build_colmap(list(rows[0].keys()))
        missing = [f for f in ("status", "addr_jibun") if f not in colmap]
        if missing:
            notes.append(f"{os.path.basename(fp)}: 필수 컬럼 없음{missing} — 건너뜀")
            continue
        got = [r for r in (row_to_lodging(r, colmap) for r in rows) if r]
        notes.append(f"{os.path.basename(fp)}: {len(rows):,}행 중 제주 {len(got):,}건")
        records.extend(got)
    return records, notes
