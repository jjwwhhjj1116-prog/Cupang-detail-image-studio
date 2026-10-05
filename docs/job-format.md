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

## 리드 영상 두 개만 먼저 검증

사용자가 리드 샘플을 먼저 요청하면 `--scope lead-sample`로 실행합니다. 이 범위는 일반 상세 이미지 생성, Figma 전체 배치, 전체 납품을 시작하지 않습니다. 브랜드와 원본 제품 사진은 샘플에서도 필수입니다. 미지정 브랜드를 임의 선택하거나 채팅 화면의 작은 썸네일을 원본 제품 사진으로 대신하지 않습니다.

```powershell
python scripts/studio.py plan jobs/sample/sample-job.json --workspace jobs/sample --output jobs/sample/sample-plan --scope lead-sample
```

샘플 계획은 리드용 시작 이미지 10개, Flow 원본 클립 10개(`lead-1-source-01`~`05`, `lead-2-source-01`~`05`), 편집 영상 2개, SRT 2개를 필수 산출물로 추적합니다. 제품 원본 사진과 샘플 작업 파일은 해시를 확인하며 그대로 보존합니다. 샘플에서 사용하지 않는 상세 이미지 프롬프트는 출력하지 않습니다.

이미지·편집 영상은 기존 QA 형식을 사용합니다. 원본 클립은 `product_fidelity`, `scene_action`, `source_trace` 검사에 실제 Flow 결과 식별자와 관찰 증빙을 기록합니다. SRT는 `subtitle_timing`, `caption_match` 검사를 기록하며, 도구가 원고의 정확한 1초 구간·문구와 다시 대조합니다.

```powershell
python scripts/studio.py record jobs/sample/sample-plan/state.json lead-1-source-01 flow/lead-1-01.mp4 qa/lead-1-source-01.json
python scripts/studio.py record jobs/sample/sample-plan/state.json lead-1-subtitles assets/lead-1.srt qa/lead-1-subtitles.json
python scripts/studio.py complete jobs/sample/sample-plan/state.json
```

모든 샘플 파일과 QA를 기록한 뒤 `complete`를 실행하면 두 편집 영상 모두를 ffprobe로 다시 검사합니다. `.tools/media-tools.json`의 ffprobe 경로를 사용하며 설정이 없으면 PATH에서 찾습니다. 30fps·150프레임·5초 검사와 파일/QA 무결성을 모두 통과한 상태는 **`sample_verified`, `page_complete: false`**입니다. 샘플을 전체 페이지 `complete`로 기록하면 검증이 실패합니다. 기계 검사가 제품 보존·초별 동작·자막 위치의 실제 프레임 검토를 대신하지 않습니다.

전체 페이지 재개 시에는 `sample-job.json`을 수정하지 않고 `full-job.json`을 만들어 상세 섹션을 채웁니다.

```powershell
python scripts/studio.py plan jobs/sample/full-job.json --workspace jobs/sample --output jobs/sample/full-plan --scope full --reuse-sample jobs/sample/sample-plan/state.json
```

같은 작업 폴더·job ID·브랜드·타입·원본 사진·리드 원고인 경우에만 샘플 검증을 다시 통과한 이미지 10개와 편집 영상 2개를 재사용합니다. 원본 클립과 자막은 샘플 폴더/상태에 보존됩니다. 재개된 전체 계획은 `in_progress`, `page_complete: false`이며 상세 이미지와 납품 묶음 검수를 계속해야 합니다. 리드 문구나 사진이 바뀌면 기존 샘플을 통과 결과로 재사용하지 않습니다.

## 1초 단위 영상 조립

Codex가 Flow에서 각 장면의 원본 영상을 생성한 다음, 영상마다 필요한 동작이 보이는 연속 1초 구간을 선택합니다. `--starts`는 그 시작 위치입니다. 움직임이 완성되지 않거나 제품 형태가 바뀌면 원본을 재생성합니다.

```powershell
python scripts/media.py jobs/sample/job.json --lead lead-1 --clips jobs/sample/flow/01.mp4 jobs/sample/flow/02.mp4 jobs/sample/flow/03.mp4 jobs/sample/flow/04.mp4 jobs/sample/flow/05.mp4 --starts 0 1.2 0.5 2 0 --output jobs/sample/assets/lead-1.mp4 --width 688 --height 400 --mute
```

위 크기는 사용법 예시입니다. 실제 크기는 Figma 영상 슬롯을 측정하여 비율을 보존하고 짝수 픽셀로 정합니다. 780px 전체 페이지 너비를 영상 슬롯 너비로 가정하지 않습니다. 화면 비율이 다르면 제품을 잘라내지 않고 여백을 추가합니다.

제품이 화면 하단까지 차는 장면에는 `--caption-band 76`처럼 전용 하단 자막 띠를 지정할 수 있습니다. 기본값 `0`은 기존 영상 위 자막 배치를 유지합니다. 예를 들어 558×363 Figma 슬롯에 맞춘 `--width 768 --height 500 --caption-band 76`은 영상을 상단 768×424 영역 안에 비율대로 축소하고, 하단 76px를 검정 자막 띠로 비워 둡니다. 영상은 자르지 않으며 남는 공간은 모든 장면에 동일한 방식으로 검정 여백 처리합니다.

자막은 띠 중앙에 ASS 좌표로 배치합니다. 명시적 여러 줄이나 긴 자막은 띠에 맞춰 글꼴 크기를 줄이며, 읽을 수 있는 최소 크기를 확보할 수 없으면 실패 처리합니다. 1초 구간과 총 150프레임은 변하지 않습니다. 실제 결과에서 글자 크기·한글 표시·띠 밖으로 넘침을 확인합니다. `.probe.json`과 `.sources.json`에 `caption_band_px`를 기록하며 원본 클립·별도 음원 및 기존 오디오 선택 방식은 보존합니다.

`ffmpeg`, `ffprobe` 실행 파일이 필요합니다. PATH에 없으면 `--ffmpeg <전체 경로> --ffprobe <전체 경로>`로 지정합니다. 스크립트가 설치하거나 다운로드하지 않습니다. FFmpeg 빌드는 H.264 인코더와 `subtitles`/libass 필터를 지원해야 하며, 한글 자막용 `Malgun Gothic` 글꼴이 있어야 합니다.

음성 정책은 명령에 명시합니다. `--mute`로 무음, `--audio <파일>`로 별도 확인한 사운드트랙을 사용합니다. 원본 Flow 음성은 자동으로 유지하지 않습니다. 별도 음원은 5초에 맞춰 잘라내거나 무음으로 채웁니다.

각 구간을 30fps·30프레임으로 정규화하고, 합친 150프레임에 ASS 자막을 씁니다. 출력은 MP4·ASS·SRT, 기계 검사 결과인 `.probe.json`, 원본 클립 해시와 사용 구간을 담은 `.sources.json`입니다. 원본 클립은 보존합니다. 짧아서 30프레임을 확보할 수 없는 소스는 실패 처리합니다. 기존 출력 파일은 덮어쓰지 않습니다.

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

# 이동 가능한 리드 샘플 미리보기

`scripts/sample_delivery.py`는 실제 MP4 2개·SRT 2개·해당 영상의 probe JSON·Figma 사본 정지 미리보기를 새 폴더에 복사한다. 자동 재생·무음·반복·직접 재생 컨트롤과 초별 자막 표를 포함한 `preview.html`을 만든다. 파일 경로는 전부 출력 폴더 내부 상대 경로라 폴더 전체를 옮겨도 사용할 수 있다. 기존 전체 납품용 `delivery.py`와 구분하며 `studio.py`의 QA 상태를 변경하지 않는다.

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

출력 `sample-manifest.json`은 항상 `scope:lead-sample`, `status:sample_packaged`, `page_complete:false`다. 파일 해시·기록된 probe의 150프레임/30fps/5초·SRT 원문과 구간을 검증한다. 영상의 실제 시각 검수나 After Effects 실행 증빙을 새로 만들어 주지는 않는다. 생성 후 브라우저에서 `preview.html`의 두 영상이 실제로 재생되는지 별도로 확인하고, Figma는 HTTPS 프로토타입에서도 따로 재생 검수한다. 스크립트의 `validate` 성공은 브라우저 재생 확인을 대신하지 않는다. 기존 출력 폴더를 덮어쓰지 않으며 수정본은 새 폴더로 만든다.

# 선택 원본 구간과 최종 1초의 구분

`media.py --source-durations 1 1 1 1 0.5`는 마지막 컷에서 `--starts`로 정한 시작점부터 0.5초만 가져와 1초로 늘린다. 기본 길이는 모두 1초이며 허용 길이는 1/99~100초다. 선택 범위가 원본 영상 길이를 넘으면 실패한다. 원본 구간 자르기 → 속도 조정 → 30fps 변환 → 필요한 끝 프레임 복제로 처리해 승인 범위 밖의 프레임을 넣지 않는다. 매 컷은 최종 30프레임, 전체는 150프레임이며 자막의 1초 구간은 변하지 않는다.

`.sources.json`에는 선택 원본 길이, 배타적인 종료 시점, 재생 속도, time stretch 비율을 기록한다. 별도 제공된 오디오 트랙은 기존 정책대로 최종 5초에 맞춰 사용하고, 원본 영상·원본 오디오는 수정하지 않는다.

