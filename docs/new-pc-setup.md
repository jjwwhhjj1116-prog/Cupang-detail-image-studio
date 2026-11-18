# 다른 Windows PC에서 등록하고 시작하기

각 PC의 Codex가 같은 GitHub 작업본·하디 입력 절차·승인 모델·Figma TYPE 템플릿·4종 납품 기준을 사용한다. 기본 정적 제작은 아래 설치기로 스킬을 등록한다. 영상 요청이 있을 때 기존 `scripts/setup-studio.ps1`로 Remotion/Flow 환경을 추가 준비한다.

## 새 PC의 첫 새 채팅 지시문

다음 문구를 그대로 Codex 새 채팅에 붙여 넣는다.

```text
https://github.com/jjwwhhjj1116-prog/Cupang-detail-image-studio.git

이 PC에서 하디 상세페이지 제작 스킬을 등록해줘.
기존 작업본이 있으면 확인하고 재사용하고, 없으면 새 폴더로 저장소를 복제해줘.
AGENTS.md, .agents/skills/detail-page-production/SKILL.md,
config/hadi-four-set.json, docs/new-pc-setup.md를 읽어줘.
scripts/install-hadi-skill.ps1을 실행해 이 PC 사용자 스킬로 등록하고
repo-location.json에 현재 작업본 경로가 맞는지 확인해줘.
사용 가능한 Python으로 scripts/setup_portability.py --repo <이 PC 작업본>을 실행해
PC 식별자와 연결 초안을 초기화하고 기존 설정을 보존해줘.
이 저장소를 Codex 프로젝트로 열어 .codex/agents의 총괄·이미지·Figma 역할을 사용해줘.

실제 제작은 내가 상품 URL이나 사진을 주면 시작해.
Codex가 ChatGPT의 하디 무한상세페이지 프롬포트 GPT에 자료를 넣고
'끝' → TYPE 비교표 → 지정 TYPE 또는 적합한 추천 TYPE 선택 → 최종 원고를 받아줘.
원고를 실제 Figma 템플릿 작업 사본에 적용해서 다음 4종을 완성해줘.
1. 흰색 배경 제품 단독 대표이미지 PNG
2. 편집 가능한 Figma 상세페이지 작업 링크
3. Figma에서 내보낸 전체 상세페이지 PNG
4. 같은 제품정보의 별도 라벨 PNG. 제품정보는 상세페이지 안에도 포함해줘.

F01/M01 승인 모델과 실제 제품 사진을 함께 참조하고 의상·헤어·색은 제품에 맞춰줘.
최신 판매자 정정을 반영하고 모르는 치수는 행을 빼줘.
기본 작업에 영상 제작을 추가하지 말고 영상 요청이 있을 때만 기존 영상 워크플로를 적용해줘.
Aside·ChatGPT·내장 이미지 도구·Figma 연결은 이 PC의 실제 상태로 확인해줘.
최초 로그인이나 권한이 필요하면 해당 항목만 안내하고 설치와 실사용 검증을 구분해줘.
하디 GPT의 이전/종료 안내가 있으니 현재 GPT 또는 제작자 후속 플러그인이 동작하는지 확인해줘.
```

## 직접 실행할 설치 명령

이미 로컬 작업본이 있으면 그 루트에서 실행한다. 사용자가 설치를 Codex에 맡기면 Codex가 이 명령을 수행한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-hadi-skill.ps1
```

설치 대상은 `$CODEX_HOME/skills/detail-page-production`이며 CODEX_HOME이 없으면 `~/.codex/skills/detail-page-production`이다. 스킬 옆 `repo-location.json`에 이 PC의 실제 작업본 경로를 저장한다. 이 로컬 경로 파일은 GitHub 배포본에 포함하지 않는다.

기존 관리 설치는 백업 후 갱신한다. 백업은 스킬 검색 폴더 밖의 `~/.codex/skill-install-backups/`에 보관해 중복 발견을 피한다. 다른 출처의 동일 이름 사용자 스킬은 보존하고 충돌을 알린다. 저장소 원본의 스킬 디렉터리 자체를 설치 대상으로 쓰지 않는다. 프로젝트의 에이전트 역할은 `.codex/agents/`에 있으므로 이 저장소를 Codex 프로젝트로 열어 사용한다. 사용자 전역 `config.toml`은 설치기가 바꾸지 않는다.

등록 후 **다음 턴**부터 `$detail-page-production`을 사용할 수 있다. 발견되지 않으면 새 채팅에서 설치 경로를 확인하고 스킬을 명시한다. 현재 설치 성공은 다른 PC 설치·실제 제작 연결까지 통과했다는 뜻은 아니다.

사용 가능한 Python으로 `python scripts/setup_portability.py --repo .`를 실행하면 `.local/machine.json`의 PC 식별자와 Figma·하디 연결 초안이 생성된다. 기존 값은 보존한다. 이 초기화는 영상 도구를 설치하지 않는다. Python 명령이 없으면 Codex의 실제 런타임 경로를 먼저 확인한다.

## 설정 후 제작 시작 문구

```text
$detail-page-production
브랜드는 유앤채. 아래 상품 URL과 첨부 사진으로 상세페이지 4종을 제작해줘.
TYPE은 하디 GPT의 추천 중 제품에 가장 맞는 것으로 골라서 진행해줘.
[상품 URL 또는 사진]
```

TYPE·브랜드가 이미 지정됐으면 다시 묻지 않는다. 제품 정보에서 브랜드가 불명확할 때만 확인한다. 스킬은 하디 원고 작성부터 최종 다운로드까지 맡으며 사용자가 하디 원고를 별도로 받아 올 필요가 없다.

## 연결과 검증

- ChatGPT에서 고정된 **하디 무한상세페이지 프롬포트**를 실제로 확인한다. 관찰 당시 GPT 선택 뒤 루트 URL이 유지돼 공유 URL은 공통 설정에 null이다. 제목·제작자 안내·입력 흐름을 확인하고 정상 연결된 직접 주소가 있으면 PC 로컬 설정에 저장한다.
- 2026-11-18 화면에 12월 11일 GPT 종료와 제작자 플러그인 이전 안내가 있었다. 실행 시 현재 GPT/후속 연결 상태를 확인하며 장래 서비스 가용성을 보장하지 않는다.
- Figma는 `config/studio-portability.json`의 사용자 소유 마스터에 접근 가능한 플러그인 계정을 사용한다. 새 PC에서 편집·복제·내보내기를 실제 확인한다. 원본 유료 .fig와 타인 공유 권한은 변경하지 않는다.
- 이미지 생성은 Codex 내장 도구를 우선 사용한다. 사용할 수 있는 모델·품질은 현재 도구 응답으로 기록한다.
- Python/Pillow가 없는 PC는 Codex의 사용 가능한 런타임을 확인하고 필요한 경우 저장소 `requirements.txt`를 설치한다. `.local/runtime.json`의 PC별 경로가 있으면 사용한다.
- 쿠키·비밀번호·토큰을 옮기지 않는다. 각 PC의 정상 최초 로그인과 접근 권한을 확인한 뒤 해당 세션을 재사용한다.
- 파일 검수는 `scripts/static_delivery.py`, 실제 Figma 편집·화보·한글·라벨 검수는 연결 도구와 이미지 확인으로 한다. 설치 검사만으로 실서비스를 통과시키지 않는다.

## PC 간 공유

GitHub에는 스킬·설치기·역할·TYPE 구조·공통 설정·승인 모델 참조만 포함한다. `jobs/`, `.local/`, 원본 .fig, 고객 이미지와 개별 결과는 비공개 로컬 자료다. 각 PC는 독립 작업 ID를 사용하고 한 작업의 하디 제출과 Figma 쓰기는 한 PC가 맡는다. 이어갈 때는 비공개 전체 작업 폴더와 상태·원고·이미지·해시를 별도로 전달하고 실제 결과를 확인해 재개한다.

## 영상 추가 요청

영상 요청이 있으면 기존 `scripts/setup-studio.ps1`을 실행해 PC별 도구·공식 Remotion 스킬·렌더러를 준비하고 `docs/production-workflow.md`, `docs/remotion-local.md`를 따른다. 기존 영상 CLI의 검증·예약·5초 편집·자막 있음/없음 규칙을 유지한다. 영상 설치 검사와 실제 Flow/Figma 영상 재생 검증은 별도다.
