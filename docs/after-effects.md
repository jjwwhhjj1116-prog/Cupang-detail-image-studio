# 리드 영상의 AE 편집 준비와 로컬 시안

리드 하나는 **다섯 장면을 합친 5초/30fps/150프레임**이다. 두 리드는 별도 컴포지션이다. 각 장면·전체 자막은 `[0,1)`부터 `[4,5)`까지 유지한다. 전환은 겹치는 디졸브 없이 정확한 컷으로 처리한다.

`scripts/typography.py`는 FFmpeg 시안과 AE JSX 생성기가 공유하는 디자인 값이다. 흑백 바탕·라임 키워드·짧은 이동/크기 변화·5단계 진행 표시를 쓴다. 라임은 이번 **샘플 크리에이티브**이며 확정된 브랜드 색상이 아니다. 본문 자막 전체는 움직이거나 사라지지 않고, 자막에서 추출한 키워드만 0.12초 동안 작게 움직인다. 새로운 BGM을 생성하거나 추가하지 않는다.

## 두 실행 결과의 구분

| 도구 | 실제로 만드는 것 | 완료라고 말할 수 없는 것 |
|---|---|---|
| `media.py --style kinetic` | FFmpeg/libass로 인코딩한 MP4·ASS·SRT·검사 기록 | AE 렌더 결과 |
| `after_effects.py` | `.jsx`와 `.ae-plan.json` | AE 실행, `.aep` 저장, AE 영상 렌더 |
| 생성한 JSX를 AE에서 실제 실행 | 원본 영상 10개를 연결한 편집 가능한 5초 컴포지션 2개와 `.aep` 저장 시도 | 자동 렌더 성공·최종 시각 검수 |

개발 시점 PC에서 AE 실행 파일을 확인하지 못했다. 생성한 JSX는 문법·입력·계획 구조를 정적으로 확인했고 **AE 호스트 실행 호환성은 미검증**이다. 로컬 MP4 시안은 FFmpeg 결과로 표시한다. `.aep` 파일은 AE가 성공적으로 저장하기 전에는 존재한다고 보고하지 않는다.

## FFmpeg 시안

기존 `media.py` 명령에 `--style kinetic --caption-band 76 --width 768 --height 500`을 추가한다. 기본 스타일 `plain`은 기존 결과를 유지한다. 제품 영상은 상단 768×424 안에 비율대로 맞추고 하단 자막 띠를 남긴다. 원본 영상은 자르지 않는다. 음성은 기존 `--mute` 또는 `--audio` 선택을 유지한다.

kinetic 스타일은 자막 띠가 최소 64px이어야 하며 한 줄의 전체 원문 자막을 사용한다. 들어가지 않는 긴 문구는 임의 축약하지 않고 실패 처리한다. 필요하면 작업 원고의 각 초에 `accent_keyword`를 지정하되 반드시 원문 자막에 있는 문자열이어야 한다.

## AE JSX 생성

작업 폴더 아래 `ae/media-map.json`에 각 리드의 원본 영상 다섯 개와 실제 동작이 보이는 시작점을 기록한다. 아래는 구조 예시이며 배열을 다섯 항목씩 채워야 한다.

```json
{
  "lead-1": [{"file":"flow/lead-1-source-01.mp4","start_seconds":0,"selection_status":"requires_visual_review"}],
  "lead-2": [{"file":"flow/lead-2-source-01.mp4","start_seconds":0,"selection_status":"requires_visual_review"}]
}
```

```powershell
python scripts/after_effects.py jobs/sample/sample-job.json --workspace jobs/sample --media-map jobs/sample/ae/media-map.json --output jobs/sample/ae/build-kinetic-v1.jsx --width 768 --height 500 --caption-band 76 --audio-mode preserve
```

파일 다운로드가 끝나기 전에 준비본이 필요할 때만 `--allow-missing`을 쓴다. 누락 파일은 `.ae-plan.json`에 남고 AE 실행 시 다시 존재 여부를 검사한다. `start_seconds:0`은 동작 검수가 끝났다는 뜻이 아니다. 원본마다 선택한 1초 구간을 실제로 확인해야 한다.

JSX는 기존 프로젝트를 바꾸지 않도록 **빈 AE 프로젝트에서만** 동작하고, 대상 `.aep`가 이미 있으면 덮어쓰지 않는다. 원본 영상을 가져오고 선택한 1초씩 배치하며, 자막·키워드를 편집 가능한 텍스트 레이어로 만든다. `preserve`는 해당 원본 구간의 오디오를 유지하고 `mute`는 끈다. 실제 저장이 끝나면 AEP만 생성하며 렌더를 자동 실행하지 않는다. 파일 쓰기 권한이나 폰트 문제가 생기면 중단 이유와 부분 생성 가능성을 알린다.

Adobe 공식 안내에 따라 `.jsx`는 AE의 **File → Scripts → Run Script File**로 실행할 수 있다. 실행 중인 AE에는 `afterfx.exe -r`로도 전달할 수 있다. 스크립트 파일 쓰기가 막힌 경우 Adobe의 Scripting & Expressions 설정에서 허용 상태를 확인한다. [Adobe 공식 스크립트 실행 안내](https://helpx.adobe.com/after-effects/desktop/automate-in-after-effects/automate-animation/scripts.html)

## 검증 범위와 API 근거

컴포지션 생성, 영상 가져오기, 텍스트, 글꼴·색상, 레이어 시작/종료, 키프레임은 Adobe 작성 *After Effects CS6 Scripting Guide*의 `addComp`, `importFile`, `addText`, `TextDocument`, `startTime/inPoint/outPoint`, `setValueAtTime`을 확인했다. 원 Adobe 블로그 파일은 접근되지 않아 Adobe 저작권 표기가 있는 보존 PDF를 참조했다. 오래된 API 문서 확인은 최신 AE 실행 검증을 대신하지 않는다. [Adobe 작성 가이드 보존본](https://fendrafx.com/wp-content/uploads/After-Effects-CS6-Scripting-Guide.pdf)

자막의 중앙 기준점 계산에는 Adobe가 설명하는 `sourceRectAtTime` 표현식을 쓴다. 기본 폰트 PostScript 이름 `MalgunGothicBold`는 이 PC의 실제 글꼴 파일에서도 확인했다. AE에서의 폰트 로딩과 실제 위치는 실행 후 다시 확인한다. [Adobe 표현식 레퍼런스](https://helpx.adobe.com/after-effects/desktop/work-with-expressions/expression-language-reference/expression-language-reference.html)

필수 시각 검수는 제품 잘림/변형, 1초 경계의 장면·전체 자막 교체, 한글 폰트, 키워드 겹침, 자막 띠 이탈, 원본 오디오다. JSX 생성이나 단위 테스트만으로 이 검수를 통과 처리하지 않는다.
# 안전 구간만 1초로 늘리기

원본의 뒷부분에서 제품이 변형되면 시각 검수에 통과한 짧은 구간만 사용할 수 있다. media-map의 해당 컷에 `source_duration:0.5`를 넣으면 선택 시작점부터 0.5초를 1초로 늘린다. 기본값은 1이다. JSX는 `layer.stretch=100/source_duration`, `startTime=shot.start-source_start/source_duration`으로 배치하고 프레임 혼합을 끈다. 입력의 원본 파일은 변경하지 않는다.

AE의 stretch 속성 범위와 프레임 혼합 열거형은 [Adobe CS6 Scripting Guide, 44–45·94쪽](https://fendrafx.com/wp-content/uploads/After-Effects-CS6-Scripting-Guide.pdf)에서 확인했다. 공통 허용 구간 길이는 1/99~100초로 제한한다. 현재 PC에서 AE를 실행하지 않았으므로 실제 AE 프레임 선택·렌더는 검증되지 않았다. FFmpeg 검증 결과를 AE 실행 성공으로 취급하지 않는다.
