#!/usr/bin/env python3
"""LOCALDATA Open API 수집기 (월간 갱신용).

수동 다운로드가 기본 경로다(README 참고). 이 스크립트는 매월 자동 갱신을 원할 때 쓴다.

  export LOCALDATA_AUTH_KEY=...            # localdata.go.kr 무료 발급
  python3 jeju-str/src/fetch.py --service-id 03_11_XX_P

주의: 업종 코드(opnSvcId)는 LOCALDATA 사이트의 '그룹별 업종조회'에서 직접 확인해 넣어야 한다.
      추측한 코드를 기본값으로 두지 않는다.
API 응답(영문 필드)은 벌크 CSV와 같은 한글 헤더로 변환해 저장하므로 build.py가 그대로 읽는다.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://www.localdata.go.kr/platform/rest/GR0/openDataApi"

# API 영문 필드 -> 벌크 CSV 한글 헤더
FIELD_MAP = {
    "opnSvcNm": "개방서비스명",
    "mgtNo": "관리번호",
    "apvPermYmd": "인허가일자",
    "trdStateNm": "영업상태명",
    "dtlStateNm": "상세영업상태명",
    "dcbYmd": "폐업일자",
    "lastModTs": "최종수정시점",
    "siteWhlAddr": "소재지전체주소",
    "rdnWhlAddr": "도로명전체주소",
    "bplcNm": "사업장명",
    "uptaeNm": "업태구분명",
    "roomCnt": "객실수",
}


def _rows_from(payload: dict) -> list[dict]:
    """LOCALDATA JSON에서 레코드 배열을 꺼낸다. 응답 껍데기가 버전마다 달라 방어적으로 훑는다."""
    node = payload
    for key in ("result", "body", "rows"):
        if isinstance(node, dict) and key in node:
            node = node[key]
    if isinstance(node, list):
        if node and isinstance(node[0], dict) and "row" in node[0]:
            return node[0]["row"]
        return node
    if isinstance(node, dict) and "row" in node:
        return node["row"]
    return []


def fetch(auth_key: str, service_id: str, local_code: str | None,
          page_size: int, base_url: str, max_pages: int) -> list[dict]:
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        params = {
            "authKey": auth_key, "opnSvcId": service_id,
            "pageIndex": page, "pageSize": page_size, "resultType": "json",
        }
        if local_code:
            params["localCode"] = local_code
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            print(f"[x] HTTP {exc.code} (page {page}) — 키·업종코드를 확인하세요.", file=sys.stderr)
            break
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"[!] 네트워크 오류 (page {page}): {exc} — 5초 후 1회 재시도", file=sys.stderr)
            time.sleep(5)
            continue
        rows = _rows_from(payload)
        if not rows:
            break
        out.extend(rows)
        print(f"    page {page}: {len(rows)}건 (누적 {len(out):,})", file=sys.stderr)
        if len(rows) < page_size:
            break
        time.sleep(0.3)  # 서버 예의
    return out


def save(rows: list[dict], path: str) -> int:
    if not rows:
        return 0
    header = [FIELD_MAP[k] for k in FIELD_MAP]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for r in rows:
            w.writerow([(r.get(k) or "") for k in FIELD_MAP])
    return len(rows)


def main() -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description="LOCALDATA 숙박 인허가 수집")
    ap.add_argument("--service-id", required=True, action="append",
                    help="LOCALDATA 업종 코드. 사이트에서 확인 후 지정. 여러 번 사용 가능")
    ap.add_argument("--auth-key", default=os.environ.get("LOCALDATA_AUTH_KEY"))
    ap.add_argument("--local-code", default="6500000",
                    help="지자체 코드. 제주특별자치도=6500000. 빈 값이면 전국 수집 후 build.py가 제주만 필터")
    ap.add_argument("--out-dir", default=os.path.join(root, "data", "raw"))
    ap.add_argument("--page-size", type=int, default=500)
    ap.add_argument("--max-pages", type=int, default=200)
    ap.add_argument("--base-url", default=BASE_URL)
    args = ap.parse_args()

    if not args.auth_key:
        print("[x] 인증키가 없습니다. LOCALDATA_AUTH_KEY 환경변수 또는 --auth-key 를 지정하세요.",
              file=sys.stderr)
        return 2

    total = 0
    for sid in args.service_id:
        print(f"[·] {sid} 수집 중…", file=sys.stderr)
        rows = fetch(args.auth_key, sid, args.local_code or None,
                     args.page_size, args.base_url, args.max_pages)
        path = os.path.join(args.out_dir, f"localdata_{sid}.csv")
        n = save(rows, path)
        total += n
        print(f"[✓] {sid}: {n:,}건 → {os.path.relpath(path, root)}", file=sys.stderr)
    if not total:
        print("[x] 수집 결과가 비었습니다. 업종 코드와 인증키를 확인하세요.", file=sys.stderr)
        return 1
    print(f"\n다음: python3 {os.path.relpath(os.path.join(root, 'src', 'build.py'))}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
