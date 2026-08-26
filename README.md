# LOVESICK 상세페이지

공개 주소: https://spbagggg-boop.github.io/lovesick/

## 구조

| 경로 | 설명 |
|---|---|
| `index.html` | 실제 서빙되는 페이지 (46KB) |
| `fonts/` | Pretendard 9종, 이 페이지에 쓰인 글자만 남긴 서브셋 (각 ~50KB) |
| `img/cover.webp` | 커버 이미지 |
| `js/` | 렌더링 런타임 + React |
| `download.html` | 원본 단일파일 export (25MB). 오프라인 배포용 |
| `tools/unbundle.py` | export를 위 구조로 변환하는 스크립트 |

## 다시 만들 때

제작 도구에서 새로 export 하면 다시 25MB 단일 파일이 나온다.
그대로 올리면 느려지므로 변환해서 올린다.

```bash
pip install "fonttools[woff]" pillow
python tools/unbundle.py "LOVESICK 상세페이지 (다운로드용).html" .
```

스크립트가 하는 일:

- 폰트 서브셋 — Pretendard 전체 글자(~11,000자)에서 실제 쓰는 546자만 남김. 7.1MB → 453KB
- woff 제거 — woff2와 중복된 구형 포맷. 10MB 삭제
- 커버 이미지 PNG → WebP. 1.7MB → 120KB
- 뷰포트를 `width=720`으로 — 디자인이 720px 고정 폭이라, 이걸 선언해야 모바일에서 화면 폭에 맞게 축소된다
- 하단 CTA 버튼에 주문 링크 연결
- `<title>` / `description` 삽입

결과: **25MB → 831KB**

새 export의 CTA 문구나 커버 이미지가 바뀌면 `tools/unbundle.py` 상단 상수를 확인할 것.
