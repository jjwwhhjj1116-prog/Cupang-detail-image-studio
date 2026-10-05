# 상세페이지 리드 영상의 로컬 렌더

Remotion 4.0.533으로 검수된 5초 무자막 영상에 Gmarket Sans Bold 모션 타이포를 합성하거나 영상만 출력한다. Flow를 호출하지 않는다.

설치: `npm ci`. 편집 화면: `npm run dev`. 코드 검사: `npm run lint`.

실제 제작은 저장소의 `scripts/remotion_render.py`를 사용한다. 이 도구가 원본 편집 구간, 선택한 자막 모드, 글꼴과 실제 렌더 증빙을 함께 기록한다. 직접 `npx remotion render`로 만든 파일을 QA 완료로 등록하지 않는다.

[실행 절차와 명령](../docs/remotion-local.md)을 따른다. `public/render-*/`에는 비공개 영상·폰트 입력이 저장되며 Git에서 제외한다. 의존성·빌드·출력도 공개 저장소에 올리지 않는다.

[공식 Remotion 문서](https://www.remotion.dev/docs)와 [라이선스](https://www.remotion.pro/license)를 참조한다.
