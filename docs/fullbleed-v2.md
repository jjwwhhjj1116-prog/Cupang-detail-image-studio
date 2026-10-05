# 단일 Flow 원본과 풀블리드 모션 자막 v2

## 자막 선택과 Remotion

현재 제작 타입은 `with-captions` / `without-captions`다. 아래 타이포·폰트 규칙은 자막 있음에 적용한다. 자막 없음은 전체 화면 영상만 만들고 글자·띠·텍스트 모션을 생략하며 원문 카피 데이터는 보존한다. 선택 변경 시 `plan --reuse-source-plan`으로 기존 원본과 생성 예약을 공유하고 Flow를 다시 제출하지 않는다.

로컬 Remotion은 검수한 1280×720·30fps·150프레임 무자막 편집본을 입력으로 사용한다. [Remotion 실행서](remotion-local.md)의 실제 렌더 경로와 증빙 검사를 따른다. FFmpeg 직접 타이포 경로도 명시적으로 선택할 수 있으며 실제 사용한 렌더러를 기록한다.

사용자의 새 제작 기준은 **리드 영상 한 편당 Flow 생성 한 번·출력 x1**이다. 다섯 장면을 타임스탬프 스토리보드로 한 번 요청하고 원본 MP4 한 개를 내려받는다. 5초 생성이 지원되지 않으면 현재 UI의 지원 길이 하나로 생성한다. 원본의 실제 장면 구간을 확인한 뒤 각 구간을 최종 1초로 편집한다. 모델이 정확한 컷 시각을 보장한다고 가정하지 않는다. 장면별 생성 다섯 번이나 실패 시 재생성으로 자동 전환하지 않는다. 장면 누락·제품 변형은 결과와 가능한 로컬 조정을 기록한다.

`studio.py plan --scope lead-sample`의 기본 `single-source-v2`는 두 개의 Flow 작업만 만든다. 각 리드의 참조 사진은 1~5개를 선택·재사용하며 원본과 최종 MP4를 별도 추적한다. 제출 전에 모델·지원 길이·x1·표시 비용·스크린샷을 기록하고 `generation-start`로 한 요청을 예약한다. 예약된 요청은 재시작해도 다시 제출하지 않는다. 실행 명령과 증빙 형식은 [job-format.md](job-format.md)를 따른다.

기존 `kinetic` 검은 하단 띠 샘플은 이전 버전이다. 파일·QA를 덮어쓰지 않고 별도 v2 폴더를 사용한다. `fullbleed-motion`은 자막띠를 허용하지 않으며 화면을 채운 화보 영상 위에 타이포를 표시한다. 착용·제품 회전·디테일을 중심으로 구성하고 360도는 실제 Flow 원본의 회전을 사용한다. `zoom-in`·`zoom-out`은 중심 기준 2.5% 확대 보정이며 평면 회전을 360도 제품 촬영으로 대체하지 않는다.

## Gmarket Sans Bold

[Gmarket 공식 배포 페이지](https://corp.gmarket.com/fonts/)의 TTF 다운로드에서 `GmarketSansTTFBold.ttf`를 사용한다. 공식 페이지는 SIL Open Font License에 따른 상업적 사용을 안내하며 파일 내부에도 저작권·라이선스가 들어 있다. 받은 원본과 라이선스 정보를 함께 보관하고 변경하지 않는다. 현재 프로젝트의 폰트는 공개 저장소에 포함하지 않는 `.tools/fonts/gmarket-sans/`에 있다.

- 파일의 PostScript 이름: `GmarketSansTTFBold`
- Windows FFmpeg/libass에서 확인한 선택 이름: `G마켓 산스 TTF Bold`
- 검증한 공식 TTF SHA256: `ff7c354dd1a324e4cecc1223c4f71e74fa81be7027e0c7f6324c475909cacefc`

FFmpeg는 `--font` 파일을 임시 fontsdir에 넣어 사용하므로 Windows 전역 설치가 필요 없다. 렌더 로그에서 `GmarketSansTTFBold`가 실제 선택되어야 성공한다. 대체 폰트가 선택되면 MP4 출력을 거부하고 `.font-failure.log`를 남긴다. 성공 시 `.font.json`에 파일 해시와 선택 로그를 저장한다. AE는 해당 글꼴이 실제 호스트에 설치되어 있어야 하며, JSX가 글꼴 일치를 검사한다. 현재 PC의 AE 실행·렌더는 미검증이다.

## 실제 컷 구간을 편집 지도에 기록

다음은 형식 예제이며 원본 영상의 실제 장면을 보고 값을 채운다. `start_seconds`와 `source_duration`은 원본 구간이고, 결과는 각 구간당 정확히 1초다. 겹치거나 순서가 바뀐 구간은 거부된다. 느린 동작에 사용할 짧은 안전 구간은 `source_duration:0.5`처럼 기록한다.

```json
{
  "segments": [
    {"second":1,"start_seconds":0,"source_duration":1.5,"motion":"zoom-in","overlay":{"anchor":"top-left","font_size":36}},
    {"second":2,"start_seconds":1.5,"source_duration":1.5,"motion":"none","overlay":{"anchor":"bottom-center","font_size":36}},
    {"second":3,"start_seconds":3,"source_duration":1.5,"motion":"none","overlay":{"anchor":"top-right","font_size":36}},
    {"second":4,"start_seconds":4.5,"source_duration":1.5,"motion":"zoom-out","overlay":{"anchor":"top-center","font_size":36}},
    {"second":5,"start_seconds":6,"source_duration":1.5,"motion":"none","overlay":{"anchor":"bottom-left","font_size":36}}
  ]
}
```

기본 caption 모드의 `overlay.anchor`는 top/bottom과 left/center/right를 조합한 여섯 값이다. color는 white/black이며 배경 박스를 만들지 않는다. `display_caption`은 원문 단어를 유지한 최대 두 줄의 줄바꿈용이다. 각 1초 구간에서 짧은 이동·확대를 적용한다.

화보용 키워드/보조문구는 `overlay.mode:editorial`로 지정한다. 아래는 형식 예시이며 실제 확인한 제품 사실만 카피에 사용한다. 원문 `caption`은 바꾸지 않는다. **job의 `seconds[].overlay`와 edit-map의 overlay를 동일하게** 기록해야 자막·해시 검증을 통과한다.

```json
{
  "mode": "editorial",
  "keyword": "화보 키워드",
  "support": "확인된 특징의 짧은 설명",
  "copy_change_reason": "사용자가 승인한 화보 구성에 맞춰 원문을 축약",
  "anchor": "top-left",
  "position": [0.08, 0.12],
  "keyword_font_size": 54,
  "support_font_size": 22,
  "color": "white",
  "support_color": "white"
}
```

editorial은 키워드와 보조문구를 각각 편집 가능한 레이어로 만들고 짧은 이동/확대를 적용한다. 제품을 가리는 검은 박스나 굵은 외곽선으로 읽힘을 해결하지 않는다. 텍스트를 빼는 초는 `enabled:false`와 명시적 사유를 기록한다. 이때 표시 SRT cue만 생략하며 원문은 남긴다. 효능·성능·제품 사실을 추가하는 축약은 허용하지 않는다.

표시 `.srt`는 초별 키워드/보조문구를 단순 텍스트 cue로 기록한다. 두 레이어의 세부 진입 시각은 ASS와 probe의 디자인 기록이 기준이다. 원문은 `.source-captions.srt`, job JSON과 디자인의 caption에 보존하며 `.copy-changes.json`으로 변경 이력을 남긴다. planner와 샘플 미리보기도 승인된 표시 카피와 원문을 각각 검증한다.

자막 위치·크기는 실제 제품과 겹치지 않는 여백을 보고 선택한다. 화면 채움은 비율을 유지한 확대와 중앙 크롭으로 구현되므로 원본·출력 비율을 가능하면 맞추고 모자·챙·손이 잘리지 않는지 프레임으로 검수한다. 영상 전체를 잘라 숨기는 하단 띠로 해결하지 않는다.

## 편집과 다운로드 파일

```powershell
python scripts/media.py jobs/<job_id>/sample-job-v2.json --lead lead-1 --source jobs/<job_id>/flow-v2/lead-1-storyboard.mp4 --edit-map jobs/<job_id>/edit-v2/lead-1.json --output jobs/<job_id>/media-v2/lead-1.mp4 --width 768 --height 432 --caption-band 0 --style fullbleed-motion --font .tools/fonts/gmarket-sans/GmarketSansTTFBold.ttf --mute --ffmpeg <ffmpeg.exe> --ffprobe <ffprobe.exe>
```

리드2도 원본 하나로 같은 절차를 수행한다. MP4·표시/원문 SRT·ASS·probe·source·font·카피 변경 기록을 보관하고 0/1/2/3/4초 경계 전후를 실제로 검수한다. `.sources.json`의 `unique_source_files:1`은 편집 입력이 하나라는 뜻이며 실제 Flow 요청 횟수 증거는 아니다. 요청 예약·UI 비용 증빙·공급자 결과 ID를 함께 대조한다.

사용자가 내려받을 수 있는 **최종 MP4 두 개**를 반드시 제공한다. `scripts/sample_delivery.py`의 미리보기에는 영상별 MP4·SRT 다운로드 링크가 있으며 실제 생성한 v2 파일 경로로 레이아웃을 지정한다. 브라우저와 Figma 프로토타입 재생 확인은 파일 검사 후 별도로 수행한다.

## AE 편집 준비

AE media-map은 각 리드에 `source_file` 하나와 위 `segments` 배열을 갖는 객체를 넣는다. 기존 다섯 파일 배열 형식은 이전 작업 재개를 위해 유지한다.

```powershell
python scripts/after_effects.py jobs/<job_id>/sample-job-v2.json --workspace jobs/<job_id> --media-map jobs/<job_id>/edit-v2/ae-media-map.json --output jobs/<job_id>/ae-v2/build-fullbleed.jsx --width 768 --height 432 --caption-band 0 --style fullbleed-motion --font .tools/fonts/gmarket-sans/GmarketSansTTFBold.ttf --audio-mode mute
```

JSX는 표시 카피·폰트·위치·주요 모션을 공유하며 같은 원본을 중복 가져오지 않고 다섯 시간 구간으로 나눈다. 실제 AE에서 실행되면 편집 가능한 두 컴포지션을 만들고 AEP를 저장한다. **렌더는 실행하지 않는다.** 현재 PC는 AE가 설치되지 않아 JSX 정적 확인과 FFmpeg 출력까지만 검증할 수 있다. 준비 파일을 실제 AEP·AE 렌더 완료로 표시하지 않으며 샘플을 전체 상세페이지 완료로 확대하지 않는다.
