# 제작 작업 형식과 로컬 검증

사용자는 하디의 최종 프롬프트를 전달합니다. 이 문서의 JSON 작성·CLI 실행·이미지/영상 생성·Figma 반영은 Codex가 이어서 처리합니다. 사용자가 각 명령을 직접 실행하는 절차가 아닙니다.

Python 3.11 이상과 표준 라이브러리만 사용합니다. `studio.py`는 원고 보존, 계획, 초 단위 자막, 진행 상태와 증빙 검사를 담당합니다. Image·Flow·Figma 호출은 저장소의 Codex 스킬이 담당하며, 이 CLI 자체에는 공급자 네트워크 호출이 없습니다.

## 입력 데이터와 영상 모드

`examples/demo-job.json`은 **가상의 형식 예제**입니다. 실제 제품 사진·원고·검증된 TYPE6 전체 템플릿을 제공하는 파일이 아닙니다. `input/demo-reference.png`를 동봉하지 않았으므로 형식 검사는 가능하지만 실제 제작 계획은 사진이 없으면 실패합니다.

| 필드 | 규칙 |
|---|---|
| `schema_version` | 정수 `1` |
| `video_mode` | 새 계획 기본 `single-source-v2`. 이전 계획 재개 전용 `legacy-five-source-v1` |
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
| `leads[].reference_images` | 선택: 리드당 상대 경로 1~5개. 리드끼리 재사용 가능. 미지정 시 product.photos 앞 다섯 개 |
| `leads[].storyboard_prompt` | 선택: 다섯 장면을 담은 단일 Flow 프롬프트. 없으면 초별 원고로 결합 |
| `leads[].seconds` | `second: 1`부터 `5`까지 순서대로 정확히 다섯 개 |
| 각 초 | `action`, `caption`, `image_prompt`, `video_prompt` 모두 필수 |
| 각 초의 `overlay` | 선택: 승인된 타이포 카피·위치. editorial이면 keyword/support/copy_change_reason을 기록하고 원 caption은 보존 |

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

새 계획 폴더에는 정적 이미지용 `image-tasks.json`, 리드별 단일 `*-storyboard.txt`, 두 요청을 담은 `flow-tasks.json`, 표시 SRT와 원문 `*.source-captions.srt`, 10개 편집 구간의 `timeline.json`, 산출물·요청 상태의 `state.json`이 생깁니다. `image_prompt`는 장면 설계 자료이며 시작 이미지 열 장을 자동 생성하는 명령이 아닙니다. `detail-page`는 전체 결과 묶음을 대표하는 artifact입니다.

입력 job 스키마는 `1`을 유지하며 v2 실행 상태는 `schema_version:2`, `video_mode:single-source-v2`입니다. 같은 파일로 다시 실행하면 상태와 이미 예약한 요청을 보존합니다. 이전 상태에 video_mode가 없으면 legacy로 읽고 변환하지 않습니다. 기존 상태의 모드를 바꾸는 요청은 실패합니다. 작업 파일을 변경할 때 새 계획 폴더를 사용하되 이미 제출한 Flow 결과를 먼저 대조하며 새 폴더가 추가 생성 승인을 뜻하지는 않습니다.

## 생성 요청 한 번을 예약하고 기록

리드마다 참조 이미지 최대 다섯 개를 선택·재사용하고, 다섯 장면의 타임스탬프 스토리보드를 한 번 제출합니다. 5초 생성이 없으면 현재 UI에서 지원하는 길이의 원본 하나를 생성합니다. 최종 5초의 정확한 타이밍은 로컬에서 편집합니다. 출력은 x1이며 장면별 다섯 생성이나 자동 재요청은 하지 않습니다.

제출 전 실제 Flow 화면을 확인하고 다음 형식의 증빙을 작업 폴더에 저장합니다. 아래 값은 형식 설명이며 실제 비용·모델을 대신하지 않습니다.

```json
{
  "provider": "Google Flow",
  "model": "현재 UI에 표시된 모델",
  "output_count": 1,
  "source_duration_seconds": 8,
  "credit_cost_ui": "현재 UI에 표시된 비용 문구 그대로",
  "ui_evidence_file": "qa/lead-1-flow-settings.png",
  "ui_evidence_sha256": "위 실제 스크린샷의 SHA-256"
}
```

```powershell
python scripts/studio.py generation-start jobs/sample/sample-plan/state.json lead-1 qa/lead-1-flow-settings.json
```

성공하면 `lead-1-generation-01`은 `reserved`가 됩니다. 그 뒤 실제 UI에서 한 번 생성합니다. 같은 요청은 다시 예약할 수 없으며 결과가 불명확하면 기존 Flow 카드·다운로드부터 확인합니다. `flow-tasks.json`만 보고 다시 제출하면 안 됩니다. 이 CLI는 공급자를 호출하지 않으며 실제 요청 횟수는 공급자 결과 기록과 함께 검수합니다.

## 리드 영상 두 개만 먼저 검증

사용자가 리드 샘플을 먼저 요청하면 `--scope lead-sample`로 실행합니다. 이 범위는 일반 상세 이미지 생성, Figma 전체 배치, 전체 납품을 시작하지 않습니다. 브랜드와 원본 제품 사진은 샘플에서도 필수입니다. 미지정 브랜드를 임의 선택하거나 채팅 화면의 작은 썸네일을 원본 제품 사진으로 대신하지 않습니다.

```powershell
python scripts/studio.py plan jobs/sample/sample-job.json --workspace jobs/sample --output jobs/sample/sample-plan --scope lead-sample
```

새 샘플의 필수 산출물은 **여섯 개**입니다: `lead-1-source`, `lead-1-subtitles`, `lead-1`, `lead-2-source`, `lead-2-subtitles`, `lead-2`. 각각 Flow 원본·표시 자막·최종 MP4이며 원본과 최종 파일을 덮어쓰거나 같은 파일로 등록할 수 없습니다. 원문 자막은 표시 SRT 옆 `*.source-captions.srt`로 함께 검증합니다. 원본 사진·선택 참조·작업 파일은 해시를 확인하며 샘플에서 사용하지 않는 정적 이미지 프롬프트는 출력하지 않습니다.

원본 QA는 `product_fidelity`, `scene_action`, `source_trace`와 함께 `generation_request_id`, 실제 `provider_result_id`, `request_count:1`, `output_count:1`을 기록합니다. 예약 없이 원본을 등록할 수 없습니다. 등록한 요청은 `source_verified`가 됩니다. SRT는 `subtitle_timing`, `caption_match`로 원문 또는 명시된 editorial 카피와 정확히 대조합니다. 화면 카피를 숨기는 `overlay.enabled:false`도 사유를 기록해야 하며 그 초의 표시 cue만 생략하고 원문은 보존합니다. 카피를 줄이면서 제품 주장·효능을 추가하지 않습니다.

```powershell
python scripts/studio.py record jobs/sample/sample-plan/state.json lead-1-source flow/lead-1-storyboard.mp4 qa/lead-1-source.json
python scripts/studio.py record jobs/sample/sample-plan/state.json lead-1-subtitles assets/lead-1.srt qa/lead-1-subtitles.json
python scripts/studio.py complete jobs/sample/sample-plan/state.json
```

모든 샘플 파일과 QA를 기록한 뒤 `complete`를 실행하면 두 편집 영상 모두를 ffprobe로 다시 검사합니다. `.tools/media-tools.json`의 ffprobe 경로를 사용하며 설정이 없으면 PATH에서 찾습니다. 30fps·150프레임·5초 검사와 파일/QA 무결성을 모두 통과한 상태는 **`sample_verified`, `page_complete: false`**입니다. 샘플을 전체 페이지 `complete`로 기록하면 검증이 실패합니다. 기계 검사가 제품 보존·초별 동작·자막 위치의 실제 프레임 검토를 대신하지 않습니다.

전체 페이지 재개 시에는 `sample-job.json`을 수정하지 않고 `full-job.json`을 만들어 상세 섹션을 채웁니다.

```powershell
python scripts/studio.py plan jobs/sample/full-job.json --workspace jobs/sample --output jobs/sample/full-plan --scope full --reuse-sample jobs/sample/sample-plan/state.json
```

같은 작업 폴더·job ID·브랜드·타입·원본 사진·리드 원고인 경우에만 다시 검증한 여섯 산출물과 소비한 요청 슬롯을 재사용합니다. 재개된 전체 계획은 `in_progress`, `page_complete:false`이며 정적 상세 이미지와 납품 검수를 계속합니다. 리드 문구·선택 참조·사진이 바뀌면 기존 샘플을 통과 결과로 재사용하지 않습니다.

이전 24개 산출물 샘플은 `legacy-five-source-v1`입니다. 기존 상태 파일은 그대로 재개할 수 있고 당시 원본 10개·시작 이미지·QA는 보존됩니다. 과거 형식을 재현해야 할 때만 `--video-mode legacy-five-source-v1`을 명시합니다. 이것은 새 작업에서 열 개 영상을 생성하라는 기본값이 아닙니다.

## 단일 원본의 1초 단위 편집

한 Flow 원본에서 실제로 검수한 다섯 연속 구간의 시작점·길이를 edit-map의 `segments`에 기록합니다. 각 구간은 최종 1초가 되고 선택 구간 밖 프레임은 사용하지 않습니다. 전체 구조·원본 회전·느린 동작·타이포 계약은 [fullbleed-v2.md](fullbleed-v2.md)에 있습니다.

```powershell
python scripts/media.py jobs/sample/job.json --lead lead-1 --source jobs/sample/flow/lead-1-storyboard.mp4 --edit-map jobs/sample/edit/lead-1.json --output jobs/sample/assets/lead-1.mp4 --width 768 --height 432 --style fullbleed-motion --caption-band 0 --font .tools/fonts/gmarket-sans/GmarketSansTTFBold.ttf --mute
```

위 크기는 사용법 예시입니다. 실제 Figma 슬롯 비율과 생성 구도를 함께 맞추고 짝수 픽셀로 정합니다. 780px 페이지 너비를 영상 슬롯 너비로 가정하지 않습니다. fullbleed는 화면을 채우기 위해 비율 유지 확대·중앙 크롭을 사용하므로 제품이 잘리지 않는지 검수합니다. 검은 여백으로 제품 잘림을 해결하지 않습니다.

새 스타일은 **Gmarket Sans Bold·검은 하단바 없음·caption_band 0**입니다. 제품을 피해 표시 카피 위치와 크기를 정하며 글꼴 대체를 허용하지 않습니다. `ffmpeg`, `ffprobe`가 PATH에 없으면 전체 경로로 지정합니다. FFmpeg에는 H.264와 libass가 필요합니다. `media.py` 자체는 설치·다운로드하지 않습니다.

이전 `--clips` 다섯 파일·`--starts`·`--caption-band 76`·`--style kinetic`·Malgun 글꼴은 v1 재개를 위해 남아 있습니다. 새 v2 QA는 검은 자막띠·다중 원본·다른 글꼴 결과를 거부합니다.

음성 정책은 명령에 명시합니다. `--mute`로 무음, `--audio <파일>`로 별도 확인한 사운드트랙을 사용합니다. 원본 Flow 음성은 자동으로 유지하지 않습니다. 별도 음원은 5초에 맞춰 잘라내거나 무음으로 채웁니다.

각 구간을 30fps·30프레임으로 정규화하고 합친 150프레임에 ASS 타이포를 씁니다. 출력은 MP4·ASS·표시 SRT·원문 `.source-captions.srt`, `.probe.json`, 원본 해시·구간의 `.sources.json`, 실제 글꼴 선택 `.font.json`입니다. editorial 변경 이력도 보존합니다. 짧은 검수 구간을 늘릴 때 필요한 끝 프레임은 구간 안에서만 복제합니다. 원본·이전 출력은 덮어쓰지 않습니다.

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

필수 검사 이름은 이미지 `product_fidelity`, `prompt_match`; 영상 `product_fidelity`, `duration`, `frame_count`, `subtitle_timing`; v2 영상은 추가로 `full_bleed`, `font`, `overlay_product_clear`, `source_storyboard`; 전체 결과는 `template_mapping`, `product_fidelity`, `text_layout`, `brand`입니다. 모든 검사는 pass와 실제 증거가 필요합니다. v2 영상은 renderer sidecar 해시·Gmarket 글꼴·자막띠 0·원본 하나와 그 해시를 추가 대조합니다. 형식 검사는 미관이나 제품 동작 판정 대신이 아닙니다.

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

# 이동 가능한 리드 샘플 미리보기

`scripts/sample_delivery.py`는 실제 MP4 두 개·표시 SRT·v2 원문 SRT·probe JSON·Figma 사본 정지 미리보기를 새 폴더에 복사한다. 자동 재생·무음·반복·컨트롤·MP4/자막 다운로드 링크·초별 표시 카피 표를 포함한 `preview.html`을 만든다. 경로는 모두 폴더 내부 상대 경로이며 폴더째 이동할 수 있다. 전체 납품용 `delivery.py`와 구분하며 `studio.py`의 QA 상태를 변경하지 않는다.

레이아웃 JSON의 경로는 `--workspace` 기준이다. `template_note`에는 실제 정지 미리보기 상태를 적는다. 예를 들어 영상 삽입 전 템플릿에는 그 사실을 명시한다.

```json
{
  "leads": [
    {"id":"lead-1","video":"media/lead-1.mp4","subtitle":"media/lead-1.srt","probe":"media/lead-1.probe.json"},
    {"id":"lead-2","video":"media/lead-2.mp4","subtitle":"media/lead-2.srt","probe":"media/lead-2.probe.json"}
  ],
  "template_preview":"figma/lead-preview.png",
  "template_note":"헤드라인을 넣은 Figma 작업 사본입니다. 영상 삽입 전 정지 미리보기이며 MP4는 위에서 별도로 재생됩니다."
}
```

선택적으로 실제 `figma_url`을 넣을 수 있다. 각 리드 헤드라인은 job의 `kind:video`, `asset_id:lead-1/lead-2` 섹션에서 가져온다.

```powershell
python scripts/sample_delivery.py build jobs/<job_id>/sample-layout.json --job jobs/<job_id>/sample-job.json --workspace jobs/<job_id> --output jobs/<job_id>/sample-preview
python scripts/sample_delivery.py validate jobs/<job_id>/sample-preview/sample-manifest.json
```

출력 `sample-manifest.json`은 항상 `scope:lead-sample`, `status:sample_packaged`, `page_complete:false`다. 파일 해시·기록된 probe의 150프레임/30fps/5초·승인된 표시 카피와 원문 SRT를 검증한다. v2의 원문은 기본적으로 표시 파일 옆 `.source-captions.srt`에서 가져오며 layout의 `source_subtitle`로 다른 상대 경로를 지정할 수 있다. 실제 영상 시각 검수나 AE 실행 증빙을 만들어 주지는 않는다. 브라우저의 두 영상과 Figma HTTPS 프로토타입 재생은 각각 별도로 확인한다. validate 성공은 재생 확인을 대신하지 않는다. 기존 폴더를 덮어쓰지 않는다.

video_mode 필드가 없는 이전 v1 job을 다시 패키징할 때는 build에 `--video-mode legacy-five-source-v1`을 명시한다. 원본 job·기존 패키지·QA를 수정할 필요가 없다. 기존 sample-manifest에 모드 필드가 없으면 검증기는 legacy로 읽는다. 새 기본값은 v2다.

# 선택 원본 구간과 최종 1초의 구분

`media.py --source-durations 1 1 1 1 0.5`는 마지막 컷에서 `--starts`로 정한 시작점부터 0.5초만 가져와 1초로 늘린다. 기본 길이는 모두 1초이며 허용 길이는 1/99~100초다. 선택 범위가 원본 영상 길이를 넘으면 실패한다. 원본 구간 자르기 → 속도 조정 → 30fps 변환 → 필요한 끝 프레임 복제로 처리해 승인 범위 밖의 프레임을 넣지 않는다. 매 컷은 최종 30프레임, 전체는 150프레임이며 자막의 1초 구간은 변하지 않는다.

`.sources.json`에는 선택 원본 길이, 배타적인 종료 시점, 재생 속도, time stretch 비율을 기록한다. 별도 제공된 오디오 트랙은 기존 정책대로 최종 5초에 맞춰 사용하고, 원본 영상·원본 오디오는 수정하지 않는다.

