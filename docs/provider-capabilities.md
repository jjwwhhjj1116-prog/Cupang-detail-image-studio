# 공급자 기능 확인

확인일: 2026-10-05. 공급자 기능은 바뀔 수 있으므로 작업 실행 전 실제 노출 기능을 우선 확인한다.

## OpenAI 이미지

요청 사양은 **Image 2.5 / high**. 공식 API 문서에는 `gpt-image-2.5-sunburst`, `gpt-image-2.5-flare` 및 품질 설정이 설명되어 있다. 제품 이미지의 반복 편집·일관성에는 Sunburst의 설명이 관련된다. 하지만 현재 연결된 Codex 내장 이미지 도구의 인자는 prompt, referenced_image_paths, num_last_images_to_include, transparent_background이며 model/quality 지정 인자가 없다.

Codex 이미지 생성 안내는 내장 생성을 `gpt-image-2` 및 일반 Codex 사용 한도와 연결해서 설명한다. 따라서 Image 2.5 high가 보장된다는 표현은 사용하지 않는다. 계정의 실제 기능이 해당 사양을 증명하거나, 사용자가 대체 사양을 명시하기 전까지 공급자 실행 조건은 미해결이다. API 키 사용·별도 과금으로 자동 전환하지 않는다.

근거: [OpenAI 이미지 생성 API](https://developers.openai.com/api/docs/guides/image-generation), [Codex 이미지 생성](https://learn.chatgpt.com/docs/image-generation).

## Google Flow

현재 공식 모델 표에서 Veo 3.1 Quality의 Frames to Video는 시작/끝 이미지를 지원하고 4·6·8초 길이를 제공한다. 직접 5초 생성 옵션과 프롬프트의 매초 동작 보장은 같은 문제가 아니다. 사용자의 5초 결과물은 소재 생성 뒤 타임라인 편집으로 만든다.

Scenebuilder는 클립 순서 조립·트리밍·다운로드를 제공한다. 공식 문서에서 한글 자막을 각 초에 정확히 배치하는 보장은 확인되지 않았다. 자막은 로컬 편집에서 합성하고 프레임을 확인한다. 특정 모델에 없는 Ingredients 기능 등을 추정 호출하지 않는다.

Flow 계정은 PC의 `.local/connections.json`에 저장하고 화면에서 확인한다. 기존 구독/크레딧 사용과 추가 구매를 구분한다. 자동 추가 구매는 비활성화다.

근거: [모델별 기능](https://support.google.com/flow/answer/16352836?hl=en), [영상 생성](https://support.google.com/flow/answer/16353334?co=GENIE.Platform%3DDesktop&hl=en), [Flow 편집](https://support.google.com/flow/answer/16935718).

## Figma

현재 연결된 Figma `upload_assets` 도구는 PNG/JPG/GIF/WebP/SVG, 파일당10MB까지 지원한다. MP4 업로드 도구로 사용하지 않는다. `use_figma`의 VIDEO paint 타입 존재만으로 로컬 MP4 업로드가 가능한 것은 아니다. 실제 편집기 기능 또는 지원된 미디어 경로를 확인해야 한다.

GIF가 업로드되더라도 최종 렌더에서 재생 여부를 확인한다. 정적 이미지 export에 움직임이 보존된다고 가정하지 않는다. MP4와 HTML 미리보기는 별도 전달해 영상 결과를 검수할 수 있게 한다.

템플릿 원본 .fig 분석은 live 파일의 편집권한 확인을 대체하지 않는다. 파일 링크는 편집 대상 식별, 로그인 계정은 접근 가능 여부 확인에 사용한다.
