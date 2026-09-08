# 제주 숙박 공급 지도 (Phase 1)

제주 에어비앤비 호스팅 검토를 위한 **공급·경쟁 분석 파이프라인**.
공공 인허가 데이터만 사용하므로 **비용 0 · 법적 리스크 없음 · 수치는 추정이 아닌 실측**이다.

전체 기획은 [`../docs/jeju-airbnb-analysis-feasibility.md`](../docs/jeju-airbnb-analysis-feasibility.md) 참고.

## 무엇이 나오나

| 지표 | 설명 |
|---|---|
| 현재 영업중 업소 수 | 읍면동 × 업종(농어촌민박 / 숙박업 / 관광숙박업) |
| 월별 영업신고 유효 업소 수 | 누적 인허가 − 누적 폐업 시계열 |
| 최근 12개월 순증감 | 신규 − 폐업. 신규 진입이 몰리는 지역 식별 |
| 이탈률 | 최근 12개월 폐업 ÷ (현재 영업중 + 최근 12개월 폐업) |
| 중위 업력 | 영업중 업소의 인허가 이후 경과 연수 중앙값 |

Airbnb 리스팅과 1:1 매칭되지는 않지만, **공급량·경쟁강도·시장 진입 속도**는
어떤 상용 데이터보다 정확하다(추정이 아니라 행정 원본이므로).

## 요구사항

Python 3.9+ 만 있으면 된다. **외부 패키지 설치 없음.**

## 사용법

### 1. 데이터 넣기 (권장: 수동 다운로드, 무료·즉시)

[LOCALDATA 데이터 다운로드](https://www.localdata.go.kr/devcenter/dataDown.do)에서
아래 업종을 내려받아 압축을 풀고 CSV를 `data/raw/` 에 넣는다.

- **농어촌민박업** — 제주 에어비앤비의 주력 업종
- **숙박업** (일반/생활)
- **관광숙박업** (호텔·호스텔·콘도)

전국 파일이어도 된다. 빌드 시 주소로 제주만 걸러낸다.
[공공데이터포털](https://www.data.go.kr/)의 `행정안전부_문화_농어촌민박업`,
`제주특별자치도_관광숙박업현황` 파일도 그대로 인식한다.
CP949·UTF-8 인코딩과 한글·영문 헤더를 모두 자동 판별한다.

### 2. 빌드

```bash
python3 jeju-str/src/build.py
```

- `data/raw/` 가 비어 있으면 **합성 샘플**로 빌드하고 대시보드 상단에 경고 배너를 띄운다.
- 결과: `dist/index.html` (단일 파일 대시보드), `data/processed/regions.csv`
- 터미널에도 핵심 수치를 요약 출력한다.

옵션:

```bash
python3 jeju-str/src/build.py --since 2015-01          # 시계열 시작 월
python3 jeju-str/src/build.py --input <디렉터리>        # 다른 입력
python3 jeju-str/src/build.py --visitors <입도객.csv>   # 수요 계절성 차트 추가
```

`--visitors` 는 `연월`(YYYYMM)과 `관광객수` 성격의 컬럼을 가진 CSV면 된다.
[제주 관광 빅데이터 플랫폼](https://data.ijto.or.kr/) 또는
[제주관광공사 관광객 실태조사](https://www.data.go.kr/data/15007318/fileData.do)에서 받는다.

### 3. 보기

`dist/index.html` 을 브라우저로 열면 된다. 서버 불필요.
저장소 루트가 GitHub Pages로 배포되므로 `<Pages 주소>/jeju-str/dist/` 로도 접근된다.

## 월간 자동 갱신 (선택)

[LOCALDATA API 신청](https://www.localdata.go.kr/devcenter/applyGroupApi.do)에서 키를 무료 발급받은 뒤:

```bash
export LOCALDATA_AUTH_KEY=발급받은키
python3 jeju-str/src/fetch.py --service-id <업종코드> --service-id <업종코드>
python3 jeju-str/src/build.py
```

> **업종 코드(`opnSvcId`)는 반드시 LOCALDATA 사이트의 '그룹별 업종조회'에서 직접 확인**해 넣는다.
> 틀린 코드가 기본값으로 박혀 있으면 조용히 엉뚱한 데이터를 받게 되므로 기본값을 두지 않았다.
> `fetch.py` 는 이 저장소의 개발 환경에서 실제 API 응답으로 검증하지 못했다
> (네트워크 정책상 `localdata.go.kr` 접근 차단). 응답 껍데기가 다르면
> `--base-url` 로 엔드포인트를 바꾸거나 수동 다운로드 경로를 쓰면 된다.
> **수동 다운로드 경로는 실제 파일 구조로 검증되어 있다.**

## 구조

```
jeju-str/
├── src/
│   ├── common.py      CSV 로딩(인코딩·헤더 자동판별), 주소/업종/상태 파싱
│   ├── metrics.py     시계열·읍면동 집계·계절성
│   ├── build.py       빌드 진입점
│   ├── fetch.py       LOCALDATA Open API 수집기 (선택)
│   ├── gen_sample.py  합성 샘플 생성기 (동작 확인 전용)
│   └── template.html  대시보드 템플릿
├── data/raw/          ← 여기에 실데이터 CSV를 넣는다 (git 추적 안 함)
├── data/sample/       합성 샘플 (가짜)
├── data/processed/    regions.csv 산출물
└── dist/index.html    대시보드
```

## 알아둘 것

- **시계열은 '영업신고 유효 업소 수'다.** 휴업 기간은 원본에 남지 않아 분리할 수 없다.
  현재 시점 지표에서만 영업중/휴업을 구분한다.
- **인허가일자가 없는 레코드는 시계열에서 제외**된다(현재 시점 집계에는 포함).
- 2006년 이전 주소의 **북제주군/남제주군은 각각 제주시/서귀포시로 매핑**한다.
- 읍면동을 못 찾은 건은 `미상`으로 모이며 차트에서는 빠지고 표에는 남는다.

## 다음 단계

Phase 2는 **요일 지정 호가 패널**이다 — 검토서 §3-B 참고.
Phase 1의 읍면동 코드에 조인해 지역 × 요일 × 월 가격 분포를 붙인다.
