# Cupang Detail Image Studio

상품 URL·이미지를 받으면 Codex가 실제 **하디 무한상세페이지 프롬포트** GPT에 제출하고 원고를 받아 Figma TYPE 템플릿으로 상세페이지를 제작한다.

최종 결과는 다음 네 종류다.

1. 흰색 배경에 제품만 보이는 대표이미지 PNG. 필요한 판매 옵션별로 제공.
2. 실제 편집 가능한 Figma 상세페이지 작업 링크.
3. Figma에서 내보낸 전체 상세페이지 PNG.
4. 상세페이지에도 들어 있는 제품정보를 별도 내보낸 라벨 PNG.

## 이 PC에 등록

저장소 루트에서 실행한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-hadi-skill.ps1
```

스킬은 사용자 Codex 스킬 디렉터리에 설치되고, `repo-location.json`으로 이 PC의 작업본을 찾는다. 다음 턴부터 `$detail-page-production`으로 호출한다. 다른 PC는 저장소를 복제하고 같은 설치기를 실행한다. [첫 새 채팅용 지시문과 설치](docs/new-pc-setup.md)를 참조한다. 프로젝트 에이전트는 이 저장소를 Codex 프로젝트로 열어 사용한다.

```text
$detail-page-production
브랜드 유앤채. 아래 URL/사진으로 하디 원고부터 상세페이지 4종 제작해줘.
TYPE은 적합한 추천 타입으로 선택해줘.
[상품 URL 또는 첨부 이미지]
```

## 제작 흐름

원본 제품 수집 → 실제 하디 GPT 업로드 → '끝' → TYPE 선택 → 원고 보존 → TYPE별 Figma 작업 사본 → 이미지와 편집 가능한 문구·표 배치 → 실제 검수 → 최종 4종 링크 제공.

판매자가 확인한 최신 사실·혼용률·색상을 우선한다. 모르는 치수는 행을 생략한다. 승인한 F01/M01 얼굴과 제품 원본을 함께 참조하고 옷·헤어·색·포즈는 제품과 사용 상황에 맞춘다. 표는 편집 가능한 텍스트로 만들며 제품정보는 전체 페이지와 별도 라벨을 함께 수정한다.

현재 하디 GPT는 로그인된 ChatGPT의 고정 항목에서 찾는다. 2026-11-18 확인한 화면에 12월 11일 종료와 제작자 플러그인 이전 안내가 있어 실행 시 현재 연결을 확인한다. 공개 GPT URL은 확보되지 않아 설정은 null이며 직접 확인한 URL이 있으면 PC 로컬 설정에 기록한다. 실제 원고 수령 전에는 해당 단계를 완료로 보고하지 않는다.

## 업무 자료

- [제작 스킬](.agents/skills/detail-page-production/SKILL.md)
- [실제 하디 GPT 연결·원고 인수](docs/hadi-prompt-intake.md)
- [4종 계약·manifest·검수](docs/hadi-four-set-workflow.md)
- [다른 PC의 등록·첫 채팅 문구](docs/new-pc-setup.md)
- [고정 모델·의상 규칙](docs/fixed-models.md)
- [Figma TYPE 구조와 매핑](docs/template-map.md)
- [총괄 에이전트](.codex/agents/detail_production_coordinator.toml)
- [배포 검증 기록](docs/hadi-four-set-validation.md)

영상은 요청 시 추가한다. 기존 [영상 제작 절차](docs/production-workflow.md), [Remotion](docs/remotion-local.md), [Flow 단일 생성·편집](docs/fullbleed-v2.md), [Figma 영상 삽입](docs/figma-media.md)과 CLI는 영상 추가 제작에서 사용한다.

공통 코드·스킬·TYPE 구조와 승인 모델 참조 6개를 GitHub로 공유한다. 고객 제품·원고·생성물은 `jobs/`, PC 경로와 계정 연결은 `.local/`에 보관한다. 원본 유료 .fig와 비밀번호·쿠키·토큰은 저장소에 넣지 않는다. 기본 스킬 설치는 브라우저·Figma 플러그인의 로그인·접근 권한을 대신하지 않는다.
