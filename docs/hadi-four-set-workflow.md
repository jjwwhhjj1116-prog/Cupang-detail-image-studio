# 하디 상세페이지 4종 제작 계약

기본 실행 프로필은 `hadi-four-set`이다. URL·이미지에서 실제 하디 GPT 원고를 수령하고, 선택 TYPE의 Figma 템플릿을 채워 네 종류를 제공한다. 영상은 요청한 작업에서 추가한다. 기존 영상 CLI의 명령·상태·테스트는 영상 작업용으로 유지한다.

| 항목 | 책임 | 완료 근거 |
|---|---|---|
| E1 상품 → 하디 원고 | 총괄 에이전트 | 제출 자료와 실제 최종 응답 파일, TYPE 선택 기록 |
| E2 원고 → Figma | 이미지 감독·단일 Figma 조립 담당 | live 프레임 복제, 실제 이미지/편집 텍스트 배치, 렌더 검수 |
| E3 최종 4종 | 총괄·검수 담당 | 대표 PNG, 정확한 Figma 링크, 전체 PNG, 동일 제품정보 별도 PNG |
| E4 다른 PC 설치 | 설치기·현장 Codex | 로컬 설치/원본 경로 발견, 실제 도구 연결 상태 |

## 입력에서 결과까지

1. 상품 URL과 실제 상품 이미지를 확보하고 옵션·최신 판매자 정정을 출처와 저장한다.
2. `hadi-prompt-intake.md`대로 실제 하디 GPT에 제출하고 '끝', TYPE 선택, 최종 원고 수령까지 진행한다.
3. `template-map.md`와 live Figma에서 TYPE 구조를 확인한다. 마스터를 보존해 작업 프레임/파일을 복제하고 선택 근거와 노드를 기록한다.
4. 실제 제품에 맞춘 흰배경 대표이미지와 슬롯별 사진을 제작한다. 착용 화보는 승인 얼굴 참조를 사용하고 옷·색·장소·동작을 상품과 맞춘다. 브랜드·카피·Q&A·제품정보는 편집 가능한 Figma 텍스트로 채운다.
5. 완성된 Figma 전체와 제품정보 프레임을 각각 PNG로 내보낸다. 표는 상세페이지 안에도 포함한다.
6. 제품/얼굴/인체/배색/소재/오류/잔존 예시를 검수하고 아래 manifest를 작성해 검증한다.
7. 사용자에게 네 종류 실제 링크를 제공한다. 선택 TYPE과 제작 중 실제 제한도 알린다.

## 전달 파일과 manifest

작업 루트를 기준으로 다음 구조를 사용한다. 기존 작업을 갱신하면 이전 결과는 별도 버전으로 보존한다.

```text
jobs/<job-id>/
  input/
  prompt/hadi-final.md
  prompt/intake.json
  delivery/representative-black.png
  delivery/detail-page.png
  delivery/product-information.png
  delivery/manifest.json
  qa.json
```

`delivery/manifest.json`의 파일 경로는 **manifest가 있는 폴더를 기준**으로 쓴다. 원고·QA는 작업 루트에 있으므로 검사 시 `--job-root`를 명시한다. 아래 SHA 값은 해당 실제 파일에서 계산해 채운다.

```json
{
  "schema_version": 1,
  "profile": "hadi-four-set",
  "job_id": "20261118-pc-example-product",
  "brand": "유앤채",
  "type": 2,
  "template_width": 780,
  "prompt": {
    "file": "prompt/hadi-final.md",
    "sha256": "실제 원고 SHA-256",
    "source": "hadi-gpt"
  },
  "figma": {
    "url": "https://www.figma.com/design/실제파일키/?node-id=실제노드ID",
    "file_key": "실제파일키",
    "node_id": "실제:노드ID",
    "product_info_node_id": "실제:정보노드ID"
  },
  "representatives": [
    {"file": "representative-black.png", "sha256": "실제 PNG SHA-256"}
  ],
  "detail": {"file": "detail-page.png", "sha256": "실제 PNG SHA-256"},
  "label": {"file": "product-information.png", "sha256": "실제 PNG SHA-256"},
  "qa": {"file": "qa.json", "sha256": "실제 QA SHA-256"}
}
```

`qa.json`에는 실제 검수를 아래 형태로 기록한다. 각 검수의 `evidence`는 본 실제 노드·파일·사진·관찰을 설명하고 검수한 파일의 현재 해시를 `artifacts`에 기록한다. 다른 출력에 대한 오래된 PASS를 재사용하지 않는다.

```json
{
  "artifacts": ["실제 대표 SHA", "실제 전체 SHA", "실제 라벨 SHA"],
  "checks": [
    {"name": "representative", "status": "passed", "evidence": "실제 파일에서 흰배경 제품 단독 및 색상을 확인"},
    {"name": "product_identity", "status": "passed", "evidence": "실제 제품 사진과 생성컷의 형태·색·부품·실착을 비교"},
    {"name": "figma_editability", "status": "passed", "evidence": "live 작업 노드와 실제 TextNode, 이미지 슬롯을 확인"},
    {"name": "figma_render", "status": "passed", "evidence": "전체 렌더에서 슬롯·줄바꿈·잘림·잔존 예시를 확인"},
    {"name": "label_consistency", "status": "passed", "evidence": "제품정보 원본 노드와 두 PNG의 표 내용을 확인"},
    {"name": "claims", "status": "passed", "evidence": "최신 판매자 정정과 제품정보·소구 카피를 대조"}
  ]
}
```

```powershell
python scripts/static_delivery.py --manifest jobs/<job-id>/delivery/manifest.json --job-root jobs/<job-id>
```

검사기는 PNG 실파일·해시·폭·경로·Figma file/node 일치·4종 구비·검수 증빙 연결을 확인한다. 실행 결과는 파일 검사다. 모델 얼굴·제품 정합성·실제 Figma 편집 권한·하디 응답 출처는 도구와 화면을 본 검수자가 확인한다. 로컬 작성 원고는 명시적으로 허용된 경우 source를 `seller-approved-local`로 기록하고 그 결정 근거를 `prompt/intake.json`에 남긴다.

## 단계와 복구

`intake` → `hadi-prompt` → `template` → `assets` → `figma` → `qa` → `delivered` 순으로 상태와 근거를 작업에 저장한다. 중단 뒤에는 실제 출력·원고·이미지·live 노드와 해시를 확인해 재개한다. 단순 스킬 설치, 원고 작성, 빈 복제 프레임은 납품 완료가 아니다. 공유 원본·유료 템플릿·작업 원고·고객 사진·인증 자료는 공개 GitHub에 올리지 않는다.
