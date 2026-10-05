# 로컬 Remotion 편집

공식 Agent Skills 12개를 이 PC의 Codex 스킬 폴더에 설치했다. 버전은 4.0.533이며 공식 저장소 커밋과 각 SKILL.md 해시를 `config/remotion-skills.lock.json`에 고정했다. 새 채팅부터 자동 스킬 검색에 반영된다. 현재 작업에서도 저장된 지침을 읽고 실행할 수 있다.

```powershell
python scripts/setup-remotion-skills.py --check
python scripts/setup-remotion-skills.py
powershell -File scripts/setup-remotion.ps1
```

첫 명령은 설치를 확인하고 두 번째는 없는 스킬을 고정된 공식 버전으로 설치한다. 이미 있는 다른 버전을 덮어쓰지 않는다. 렌더 프로젝트는 `remotion/`이며 package-lock.json으로 실제 npm 의존성을 고정했다. 설치 경로가 PATH에 없는 PC에서는 Codex가 로컬 Node/Python 경로를 지정한다.

제작은 **Flow 원본 생성 → 실제 장면 검수 → FFmpeg 무자막 5초 편집 → Remotion 타이포/무자막 렌더 → 결과 검수 → Figma·다운로드 출력** 순서다. Remotion은 자막 선택을 바꿀 때 Flow를 호출하지 않는다.

원본 제품과 장면에 맞게 `media.py --caption-mode without-captions --caption-band 0`으로 깨끗한 MP4를 만든다. 1280×720, 30fps, 150프레임이며 `.sources.json`, `.probe.json`, `.source-captions.srt`를 함께 보존한다. 자막을 이미 합성한 MP4에서 글자를 지우는 방식은 사용하지 않는다.

```powershell
python scripts/remotion_render.py jobs/sample/job.json --lead lead-1 --clean-source jobs/sample/clean/lead-1.mp4 --output jobs/sample/remotion/lead-1-with.mp4 --caption-mode with-captions --font .tools/fonts/gmarket-sans/GmarketSansTTFBold.ttf
python scripts/remotion_render.py jobs/sample/job.json --lead lead-1 --clean-source jobs/sample/clean/lead-1.mp4 --output jobs/sample/remotion/lead-1-without.mp4 --caption-mode without-captions
```

자막 있음은 Gmarket Sans Bold를 로컬 파일로 로드하고 각 초에 핵심 단어를 움직인다. 검은 하단바 없이 제품과 얼굴을 피한 위치를 사용한다. 자막 없음은 글자·배경 띠·텍스트 모션을 생성하지 않으며 폰트 파일도 필요하지 않다. 원문 자막은 데이터로 남긴다.

출력은 MP4와 렌더 로그, `.remotion.json`, `.probe.json`, `.sources.json`, 원문 SRT다. 원본 구간과 해시를 유지하고 편집 입력 MP4의 해시도 별도로 기록한다. 기존 여러 소재를 보정한 영상은 출처를 그대로 기록하며 단일 Flow 원본으로 표시하지 않는다.

실제 Remotion 4.0.533으로 자막 있음·없음 두 모드를 1280×720·30fps·150프레임 MP4로 시험 렌더했다. 이는 편집 기능 검증이며 새로운 고정 모델 상품 영상이나 전체 상세페이지 완료를 뜻하지 않는다. Studio 브라우저 미리보기는 연결 제한으로 확인되지 않았다. 결과 프레임 검수와 상품별 QA는 별도다.

편집 화면은 `remotion/`에서 `npm run dev`로 열고 CLI가 출력한 주소를 사용한다. Studio와 렌더러는 로컬 실행이며 Flow 크레딧을 소모하지 않는다. 실제 렌더 파일 없이 스킬 설치나 JSX 생성만으로 영상을 완료 처리하지 않는다.
