# 제작 작업 형식과 로컬 검증

사용자는 하디의 최종 프롬프트를 전달합니다. 이 문서의 JSON 작성·CLI 실행·이미지/영상 생성·Figma 반영은 Codex가 이어서 처리합니다. 사용자가 각 명령을 직접 실행하는 절차가 아닙니다.

Python 3.11 이상과 표준 라이브러리만 사용합니다. `studio.py`는 원고 보존, 계획, 초 단위 자막, 진행 상태와 증빙 검사를 담당합니다. Image·Flow·Figma 호출은 저장소의 Codex 스킬이 담당하며, 이 CLI 자체에는 공급자 네트워크 호출이 없습니다.

## v1 데이터

`examples/demo-job.json`은 **가상의 형식 예제**입니다. 실제 제품 사진·원고·검증된 TYPE6 전체 템플릿을 제공하는 파일이 아닙니다. `input/demo-reference.png`를 동봉하지 않았으므로 형식 검사는 가능하지만 실제 제작 계획은 사진이 없으면 실패합니다.

| 필드 | 규칙 |
|---|---|
| `schema_version` | 정수 `1` |
| `job_id` | 영문 소문자·숫자·하이픈으로 된 고유 이름 |
| `brand` | `와이홉` 또는 `유앤채` |
| `type` | 정수 1~7 |
| `product.photos` | 작업 폴더 기준 상대 경로 배열. 실제 제작 전에 파일 존재 확인 |
| `product.confirmed_facts` | 확인된 사실만 담은 문자열 배열. 확인되지 않은 소재·규격·효능을 넣지 않음 |
| `source_prompt` | 원문 그대로 보존하는 선택 필드 |
| `sections` | 원래 번호를 보존하는 슬롯 배열. `id`, `kind`, `text` 필수 |
| 이미지 섹션 | `kind: image`; 단일 `asset_id`/`image_prompt` 또는 여러 개의 `assets` 배열 |
| `sections[].assets` | `{asset_id, image_prompt, slot_id?}` 배열. 슬롯마다 고유 ID와 개별 프롬프트 필수 |
| 영상 섹션 | `kind: video`, `asset_id: lead-1` 또는 `lead-2`; 각 리드를 정확히 한 번 연결 |
| `leads` | `lead-1`, `lead-2` 순서로 정확히 두 개 |
| `leads[].fps` | 정수 `30` |
| `leads[].seconds` | `second: 1`부터 `5`까지 순서대로 정확히 다섯 개 |
| 각 초 | `action`, `caption`, `image_prompt`, `video_prompt` 모두 필수 |

번호 1은 0.000~1.000초, 번호 5는 4.000~5.000초입니다. 각 구간은 30프레임이고 마지막 경계는 다음 구간에 속합니다. 리드 하나는 150프레임, 5초입니다. 두 리드를 합쳐 10초짜리 하나로 만들지 않습니다.

섹션 번호는 `6-0`, `6-1`처럼 선택한 타입으로 시작해야 합니다. 이 검사는 템플릿의 실제 노드 위치까지 검증하지 않으므로 Figma 매핑 검사도 별도로 수행합니다. 같은 Figma 프레임에 여러 원고 섹션이 들어갈 수 있습니다.

하나의 섹션에 이미지가 여러 개라면 모든 슬롯을 `assets`로 열거합니다. 예를 들어 활용 이미지 다섯 칸에는 다섯 항목, 사용법 네 칸에는 네 항목이 필요합니다. 실제 슬롯 수는 선택한 Figma 템플릿을 읽어 확인합니다. 단일 `asset_id` 형식과 배열 형식을 같은 섹션에서 섞지 않습니다.

```json
{
  "id": "6-8", "kind": "image", "text": "활용 장면 원고",
  "assets": [
    {"asset_id": "usage-01", "image_prompt": "첫 번째 활용 이미지 지시", "slot_id": "확인한 실제 Figma 노드 ID"},
    {"asset_id": "usage-02", "image_prompt": "두 번째 활용 이미지 지시", "slot_id": "다른 실제 Figma 노드 ID"}
  ]
}
```

위 예시의 두 항목은 배열 형식 설명용입니다. 실제 TYPE6 슬롯 수를 두 개로 규정하지 않습니다. `asset_id`는 작업 전체에서 고유하고, `slot_id`가 있다면 다른 이미지와 중복될 수 없습니다. 배열의 이미지 모두 개별 생성·검수 대상이며 일부만 제작해 완료할 수 없습니다.

원고에 포함된 원단·상품평·사은품·성과 수치가 사실인지는 Python이 판단하지 않습니다. Codex는 원본 사진·사용자 제공 사실과 대조하여 미확인 주장을 수정하거나 제외하고 그 판단을 QA에 기록합니다.

## 원고 수집과 계획

다음 명령의 경로는 저장소 루트에서 실행하는 예시입니다. 실제 상품은 `jobs/<job_id>/` 아래에서 관리합니다.

```powershell
python scripts/studio.py ingest jobs/sample/prompt.txt --output jobs/sample/job.json --job-id sample --brand 와이홉 --type 6
python scripts/studio.py validate jobs/sample/job.json --workspace jobs/sample
python scripts/studio.py plan jobs/sample/job.json --workspace jobs/sample --output jobs/sample/plan
```

`ingest`는 `6-1)` 같은 제목을 찾아 원문을 저장한 **초안**만 만듭니다. Codex가 원문을 읽고 이미지·영상·텍스트 슬롯, 사진 경로, 확인 사실, 10개 초 단위 장면을 채운 뒤 `validate`와 `plan`을 실행합니다. 분류가 끝나지 않은 초안을 준비 완료로 표시하지 않습니다.

계획 폴더에는 이미지 프롬프트, 섹션별 전체 이미지 목록 `image-tasks.json`, `lead-1.srt`, `lead-2.srt`, 프레임 경계를 담은 `timeline.json`, 필수 산출물을 추적하는 `state.json`이 생깁니다. 이미지 산출물은 일반 섹션 이미지와 영상용 시작 이미지 10개, 영상은 리드 2개입니다. `detail-page`는 완성 결과 묶음을 대표하는 artifact입니다.

같은 작업 파일로 다시 실행하면 기존 상태를 보존합니다. 작업 파일이 변경되면 새 계획 폴더를 사용합니다. 이미 생성한 결과물의 재사용은 이미지·원고·템플릿 버전이 여전히 일치하는지 Codex가 확인한 뒤 기록합니다.

## 1초 단위 영상 조립

Codex가 Flow에서 각 장면의 원본 영상을 생성한 다음, 영상마다 필요한 동작이 보이는 연속 1초 구간을 선택합니다. `--starts`는 그 시작 위치입니다. 움직임이 완성되지 않거나 제품 형태가 바뀌면 원본을 재생성합니다.

```powershell
python scripts/media.py jobs/sample/job.json --lead lead-1 --clips jobs/sample/flow/01.mp4 jobs/sample/flow/02.mp4 jobs/sample/flow/03.mp4 jobs/sample/flow/04.mp4 jobs/sample/flow/05.mp4 --starts 0 1.2 0.5 2 0 --output jobs/sample/assets/lead-1.mp4 --width 688 --height 400 --mute
```

위 크기는 사용법 예시입니다. 실제 크기는 Figma 영상 슬롯을 측정하여 비율을 보존하고 짝수 픽셀로 정합니다. 780px 전체 페이지 너비를 영상 슬롯 너비로 가정하지 않습니다. 화면 비율이 다르면 제품을 잘라내지 않고 여백을 추가합니다.

`ffmpeg`, `ffprobe` 실행 파일이 필요합니다. PATH에 없으면 `--ffmpeg <전체 경로> --ffprobe <전체 경로>`로 지정합니다. 스크립트가 설치하거나 다운로드하지 않습니다. FFmpeg 빌드는 H.264 인코더와 `subtitles`/libass 필터를 지원해야 하며, 한글 자막용 `Malgun Gothic` 글꼴이 있어야 합니다.

음성 정책은 명령에 명시합니다. `--mute`로 무음, `--audio <파일>`로 별도 확인한 사운드트랙을 사용합니다. 원본 Flow 음성은 자동으로 유지하지 않습니다. 별도 음원은 5초에 맞춰 잘라내거나 무음으로 채웁니다.

각 구간을 30fps·30프레임으로 정규화하고, 합친 150프레임에 ASS 자막을 씁니다. 출력은 MP4와 ASS, 기계 검사 결과인 `.probe.json`입니다. 짧아서 30프레임을 확보할 수 없는 소스는 실패 처리합니다. 기존 출력 파일은 덮어쓰지 않습니다.

기계 검사는 30fps·150프레임·해상도와 컨테이너 길이 오차 0.04초 이내를 확인합니다. **영상의 시각적 길이는 정확히 150/30=5초**이며 컨테이너 오차 허용은 오디오 패킷 등에 대한 검사 허용치입니다. `.probe.json`만으로 제품 보존·자막 위치·한글 표시·각 초의 동작까지 통과했다고 표시하지 않습니다. Codex가 실제 프레임을 확인한 증빙을 추가합니다.

## 산출물과 QA

`record`는 실제 파일과 해당 파일 SHA-256에 연결된 QA 파일이 있어야 성공합니다. QA 예시의 증빙 문구를 복사해 통과시켜서는 안 됩니다. 실제 관찰한 내용과 프레임·이미지·Figma 노드 근거를 작성합니다.

```json
{
  "artifact_sha256": "실제 산출물의 SHA-256",
  "checks": [
    {"name": "product_fidelity", "status": "pass", "evidence": "실제 비교 결과 및 참고 이미지 식별자"},
    {"name": "prompt_match", "status": "pass", "evidence": "해당 슬롯과 실제 결과의 대조 결과"}
  ]
}
```

필수 검사 이름은 이미지 `product_fidelity`, `prompt_match`; 영상 `product_fidelity`, `duration`, `frame_count`, `subtitle_timing`; 완성 결과 `template_mapping`, `product_fidelity`, `text_layout`, `brand`입니다. 모든 검사는 `pass`이고 증빙 문자열이 있어야 합니다. 이 형식 검사만으로 시각적 품질을 판정할 수 없으므로 실행 스킬의 실제 결과 확인이 필수입니다.

```powershell
python scripts/studio.py record jobs/sample/plan/state.json hero assets/hero.png qa/hero.json
python scripts/studio.py record jobs/sample/plan/state.json detail-page delivery-manifest.json qa/delivery.json
python scripts/studio.py complete jobs/sample/plan/state.json
```

`record`의 산출물·QA 경로는 `--workspace`로 지정했던 작업 폴더 기준입니다. 완성 결과는 편집 가능한 Figma 링크, 순서가 있는 정적 섹션 이미지, 리드 영상 2개와 자막, 미리보기, QA를 담은 `delivery-manifest.json`으로 등록합니다. 전달 묶음의 내부 파일도 delivery 검증을 통과해야 합니다. 검증기에 원본 작업 전체를 전달하여 텍스트를 포함한 모든 섹션의 내보내기 연결과 모든 구성 이미지의 포함 여부를 대조합니다. 여러 섹션이 같은 출력 이미지에 들어가면 해당 이미지의 `section_ids`에 함께 기록합니다.

완료 검사에서는 모든 필수 산출물과 QA의 해시를 다시 확인합니다. 누락·수정·실패가 발견되면 상태는 `needs_review`가 됩니다. 생성·검수 없는 계획 파일만으로는 완료 처리할 수 없습니다. 소스 작업 자체가 변경되었다면 새 계획이 필요합니다.

## 검증 실행

```powershell
python -m unittest discover -s tests -v
python scripts/studio.py validate examples/demo-job.json
```

테스트는 경로 이탈, 잘못된 브랜드/타입, 초 번호 누락·중복·순서, 미검수 완료 차단, 파일/증빙 해시와 정확한 타임라인을 검사합니다. 테스트용 내용은 실제 제품이나 제공자 성공 결과를 의미하지 않습니다. FFmpeg가 없는 환경에서는 실제 인코딩·한글 렌더링·Flow 생성·Figma 배치를 시험했다고 주장하지 않습니다.

