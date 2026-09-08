#!/usr/bin/env python3
"""제주 숙박 공급 지도 빌드.

  python3 jeju-str/src/build.py                      # data/raw 사용
  python3 jeju-str/src/build.py --input <dir>        # 다른 입력
  python3 jeju-str/src/build.py --visitors <csv>     # 월별 입도객 CSV 추가

data/raw 가 비어 있으면 합성 샘플로 빌드하고 대시보드에 경고 배너를 띄운다.
표준 라이브러리만 사용한다.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import metrics  # noqa: E402
from common import load_dir, read_rows  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def write_processed(rows: list[dict], path: str) -> None:
    import csv

    if not rows:
        return
    cols = [k for k in rows[0] if k != "by_service"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="제주 숙박 공급 지도 빌드")
    ap.add_argument("--input", default=os.path.join(ROOT, "data", "raw"))
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    ap.add_argument("--since", default="2013-01", help="시계열 시작 월 (YYYY-MM)")
    ap.add_argument("--visitors", default=None, help="월별 입도 관광객 CSV (선택)")
    args = ap.parse_args()

    src_dir, is_sample = args.input, False
    if not glob.glob(os.path.join(src_dir, "**", "*.csv"), recursive=True):
        sample_dir = os.path.join(ROOT, "data", "sample")
        sample_csv = os.path.join(sample_dir, "SAMPLE_lodging.csv")
        if not os.path.exists(sample_csv):
            from gen_sample import generate

            generate(sample_csv)
        print(f"[!] {src_dir} 에 CSV가 없습니다 → 합성 샘플로 빌드합니다.", file=sys.stderr)
        src_dir, is_sample = sample_dir, True

    records, notes = load_dir(src_dir)
    if not records:
        print("[x] 제주 레코드를 한 건도 읽지 못했습니다. 로그를 확인하세요:", file=sys.stderr)
        for n in notes:
            print("   -", n, file=sys.stderr)
        return 1

    today = date.today()
    until = f"{today.year:04d}-{today.month:02d}"
    months, by_service = metrics.monthly_series(records, args.since, until)
    regions = metrics.region_table(records, until)
    summary = metrics.summarize(records, until)

    season = None
    if args.visitors and os.path.exists(args.visitors):
        rows = read_rows(args.visitors)
        season = metrics.seasonality(rows) if rows else None
        notes.append(
            f"{os.path.basename(args.visitors)}: 계절성 "
            + ("산출 완료" if season else "산출 실패 — 연월/관광객수 컬럼을 찾지 못함")
        )

    payload = {
        "meta": {
            "generated": today.isoformat(),
            "until": until,
            "since": args.since,
            "source": "합성 샘플 (가짜)" if is_sample else os.path.relpath(src_dir, ROOT),
            "is_sample": is_sample,
            "window": summary["window"],
            "notes": notes,
        },
        "summary": summary,
        "series": {"months": months, "byService": by_service},
        "regions": regions,
        "seasonality": season,
    }

    with open(os.path.join(HERE, "template.html"), encoding="utf-8") as fh:
        html = fh.read()
    blob = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    html = html.replace("/*__DATA__*/", blob)

    os.makedirs(args.out, exist_ok=True)
    out_html = os.path.join(args.out, "index.html")
    with open(out_html, "w", encoding="utf-8") as fh:
        fh.write(html)
    write_processed(regions, os.path.join(ROOT, "data", "processed", "regions.csv"))

    print("─" * 58)
    for n in notes:
        print("  ", n)
    print("─" * 58)
    print(f"  현재 영업중          {summary['active']:>7,}")
    print(f"  휴업 / 누적 폐업     {summary['dormant']:>7,} / {summary['closed']:,}")
    print(f"  최근 12개월 신규     {summary['new_12m']:>7,}")
    print(f"  최근 12개월 폐업     {summary['closed_12m']:>7,}  (순증감 {summary['net_12m']:+,})")
    print(f"  영업중 중위 업력     {summary['median_tenure']:>7} 년")
    print(f"  업종 구성            " + " · ".join(f"{k} {v:,}" for k, v in summary["by_service"].items()))
    print("─" * 58)
    print("  상위 읍면동 (영업중)")
    for r in [r for r in regions if r["emd"] != "미상"][:8]:
        print(f"    {r['region']:<14} {r['active']:>5,}   최근12M {r['net_12m']:+3d}"
              f"   이탈률 {r['churn_12m']:>4}%")
    print("─" * 58)
    if is_sample:
        print("  ⚠ 합성 샘플 기준입니다. 위 숫자는 전부 가짜입니다.")
    print(f"  → {os.path.relpath(out_html)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
