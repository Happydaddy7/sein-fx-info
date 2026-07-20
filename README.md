# sein-fx-info — 세인바이오 외환 정보 대시보드

외화 수급(매입·결제·하루 조달액) 현황과 외환시장 뉴스를 한 페이지로 보여주는 대시보드.
뉴스는 GitHub Actions가 평일 2시간마다 자동 수집한다.

## 구성
| 파일 | 역할 |
|---|---|
| `index.html` | 대시보드 본체 (GitHub Pages로 서빙) |
| `fetch_news.py` | Google News RSS에서 외환 뉴스 수집 → `news.json` 생성 |
| `news.json` | 뉴스 데이터 (Actions가 자동 갱신, 직접 수정 불필요) |
| `.github/workflows/update-news.yml` | 자동 실행 스케줄 (평일 KST 07~19시, 2시간 간격) |

## 최초 설정 (1회)
1. GitHub에서 새 레포 `sein-fx-info` 생성 (Public)
2. 이 폴더 내용 전체 업로드 (`.github` 폴더 포함 주의)
3. **Settings → Pages** → Branch: `main`, 폴더 `/ (root)` → Save
4. **Settings → Actions → General → Workflow permissions** → `Read and write permissions` 선택 → Save
5. **Actions 탭 → Update FX News → Run workflow** 로 첫 수집 실행
6. 접속: `https://happydaddy7.github.io/sein-fx-info/`

## 운영
- **뉴스 주제 변경**: `fetch_news.py` 상단 `QUERIES` 리스트 수정 (예: "팜유 가격", "메치오닌" 추가)
- **수집 시간 변경**: `update-news.yml`의 cron 수정 (UTC 기준 = KST − 9시간)
- **월별 수급 데이터 갱신**: 매달 통관·미불금 파일로 `index.html`의 `const D = [...]` 배열에 한 달치 추가
- 뉴스 표시는 제목·출처·원문 링크만 사용 (본문 미게재)

## 데이터 출처
- 매입: 26년 외화구매내역 (실행일 기준)
- 결제: 수입통관·미불금 스냅샷 5장 통합 (25.9~26.7, 중복 274건 제거, 신고번호 기준)
- 검증: 2025년 매입 $24.56M vs 결제 $24.36M (차이 0.8%)
