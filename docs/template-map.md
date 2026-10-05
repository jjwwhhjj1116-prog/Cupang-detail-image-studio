# Figma 템플릿과 자동 실행 연결

제공된 `.fig`를 읽기 전용으로 해석해 TYPE1~7의 실제 프레임 구조를 확인했다. 원본 전체 파일·사진·문구는 이 저장소에 포함하지 않는다. `config/template-structure.json`은 프레임 이름, 원본 내부 ID, 크기, 순서와 의미 분류만 보관한다. `semantic_role`은 분석자가 부여한 분류이며, 실제 레이어 이름은 `section_name`이다.

원본 페이지 `무한상세페이지_TYPE7` 안에 일곱 타입이 함께 있다. 별도 `실사용아이콘` 페이지는 상세페이지 템플릿 페이지가 아니다. 원본 폭은 모두 780px이다.

| 타입 | 번호형 프레임 수 | 별도 영상 자리 |
|---|---:|---:|
| TYPE1 | 20 | 2 |
| TYPE2 | 19 | 2 |
| TYPE3 | 19 | 2 |
| TYPE4 | 19 | 2 |
| TYPE5 | 20 | 2 |
| TYPE6 | 17 | 2 |
| TYPE7 | 20 | 2 |

## 자동화에서 반드시 처리할 차이

- 리드1·2의 영상 자리는 번호형 프레임 내부에 있지 않다. 중간의 형제 Group도 같이 복제한다.
- TYPE6 프롬프트 `6-18 제품정보`는 원본 `6-17`의 아래 영역에 들어간다. 원본에 `6-18` 프레임은 없다.
- TYPE7에는 `7-14`가 두 개 있다. 사용법(780×1288)과 구성품(780×749)을 서로 다른 ID/의미로 매핑한다.
- TYPE6의 활용도 이미지 자리는 5개, 사용법 4개, 디테일뷰 4개, 색상 4개+사이즈 1개다. 입력 내용의 개수가 다르면 복제본에서 슬롯을 재배치한다.
- TYPE6 마지막 프레임의 기본 Q&A는 정상 배열 4문답과 제품정보 제목 부근에 남은 별도 샘플 질문으로 구성된다. 5문답 입력은 문답 행 확장과 아래 영역 이동이 필요하다. 글자만 일괄 치환하고 완료 처리하지 않는다.
- 실제 이미지 레이어가 780px 프레임보다 크게 크롭된 경우가 많다. 생성 비율은 보이는 크롭/마스크 기준으로 계산한다.
- 템플릿의 브랜드, 환불, 평점·판매량, 재질·치수·색상은 샘플이다. 확정된 상품 자료로 치환하거나 해당 슬롯을 제외한다.

## Codex 실행 어댑터

`scripts/figma_payload.py`는 Figma MCP `use_figma`에 전달할 JSON 인수를 생성한다. 네트워크 호출이나 Figma 변경은 이 Python 파일 자체에서 실행하지 않는다. **Codex가 결과 JSON을 도구에 직접 전달**하며 사용자가 코드를 복사하는 단계는 없다. 호출 전 `figma-use`, 쓰기에는 `figma-generate-design` 스킬도 읽는다. 실제 편집 권한이 확인된 파일에서만 진행한다.

명령의 `--output`은 하위 명령 앞에 둔다. 예시는 저장소 루트에서 실행한다. 작업 경로는 Git에서 제외되는 `work/`로 설정한다.

```sh
python scripts/figma_payload.py --output work/job/inspect-payload.json inspect --file-key LIVE_FILE_KEY --type TYPE6
python scripts/figma_payload.py --output work/job/clone-payload.json clone --snapshot work/job/source-snapshot.json --job-id product-001
python scripts/figma_payload.py --output work/job/output-inspection-payload.json inspect-output --clone-state work/job/clone-state.json
python scripts/figma_payload.py --output work/job/section-inspection-payload.json inspect-output --clone-state work/job/clone-state.json --section-id CLONED_SECTION_ID --offset 0 --limit 20
python scripts/figma_payload.py --output work/job/text-payload.json text --clone-state work/job/clone-state.json --edits work/job/text-edits.json
```

1. `inspect`는 페이지를 한 번만 전환하고 원본 이름/종류/크기를 검증한다. 가져오기 후 ID가 바뀌어도 고유하게 일치하는 실제 노드를 찾는다. 겹치거나 누락된 대상은 `issues`에 남기고 `liveVerified:false`를 반환한다. 성공한 반환 객체를 `source-snapshot.json`에 저장한다. 페이지가 달라졌으면 `pages --file-key ...`로 읽고 `--page-id`로 지정한다. 도구의 응답 길이 제한 때문에 전체 노드 텍스트를 반환하지 않고 각 루트의 짧은 정보와 전체 하위 구조의 `sourceSignature`를 반환한다. 이것은 변경 감지를 위한 결정적 이중32비트 지문/문자길이/노드수이며 보안용 전자서명은 아니다. 예전 `tree` 형식은 다시 검사해 갱신한다.
2. `clone`은 성공한 스냅샷만 입력받는다. 실제 노드 전체 계층의 ID·이름·종류·크기·텍스트·현재 폰트를 다시 확인하고 폰트를 불러온 뒤 복제한다. 원본의 위에서 아래 순서대로 영상 자리까지 새 세로 Auto Layout에 넣는다. 기존 스타일, 컴포넌트 인스턴스, 변수 연결은 복제를 통해 보존한다. Code Connect/새 라이브러리 검색은 기존 템플릿을 그대로 복제하므로 대상이 아니다.
3. 반환한 `clone-result`를 `clone-state.json`에 저장한다. `sourceToClone`은 원본 **실제 ID**에서 복제본 ID로 가는 외부 매핑이다. 큰 결과는 `figma.io.write`로 전체 JSON을 도구 결과 파일에 첨부하고 `mode:clone-result-reference`, `fullResultFile`과 모든 생성 ID를 반환한다. 이때 Codex가 첨부 JSON을 읽어 `clone-state.json`으로 저장한다. 요약을 전체 상태 파일로 저장하지 않는다. Figma `pluginData`에 작업 상태를 쓰지 않는다. 같은 `job-id`의 wrapper가 있으면 재복제를 중지하고 기존 상태를 읽어 재개한다.
4. `inspect-output` 기본 응답은 섹션 루트와 종류별 노드 수만 포함한다. 실제 텍스트·이미지 해시·폰트는 `--section-id`로 복제본 하위 노드를 지정하고 `--offset`/`--limit`으로 나눠 읽는다. `nextOffset`이 있으면 그 위치를 다음 요청에 넣는다. 자동 응답 크기 제한이 적용되므로 요청한 limit보다 적은 수가 반환될 수 있다. 각 호출은 페이지를 한 번만 전환한다. 이 결과를 바탕으로 Codex가 문구와 이미지 슬롯을 연결한다. 생성된 제품 사진은 `upload_assets` 등 지원되는 업로드 도구로 **복제본 ID**에 배치한다.
5. `text`는 복제본에 속하는 TextNode만 수정한다. 모든 대상과 `expectedText`가 일치하고 현재 사용 폰트가 로드된 뒤 수정한다. 컴포넌트 속성에 연결된 문구는 해당 인스턴스의 확인된 `setProperties` 매핑으로 처리한다.

`text-edits.json` 형식:

```json
[
  {"nodeId":"CLONED_TEXT_ID","expectedText":"현재 검사한 문구","text":"새 상품 문구"}
]
```

`clone-result`의 `status:cloned-not-filled`는 템플릿만 복제했다는 뜻이다. 이미지·영상·문구 제작 및 검수 완료를 의미하지 않는다. 부분 실패는 `status:partial`과 생성된 ID를 반환한다. 이를 확인하기 전 같은 생성 명령을 다시 실행하지 않는다.

## 완료 검수

모든 자산을 넣은 뒤 원본 샘플 문구/사진 잔존, 넘침·겹침, 실제 폰트, 이미지 크롭, 영상 초수·자막, 상품 스펙 일치를 검사한다. 구조 검사에서 복제본의 편집 가능한 텍스트/사진/인스턴스 노드 수와 배치를 확인하고 전체 캡처를 한 번 확인한다. 오류가 있으면 해당 부분을 고치고 다시 캡처한다. 최종 합격 후 placeholder를 해제하고 내보낸다. 마스터 프레임은 수정하지 않는다.

원본 파일 SHA-256: `ad3ca0887a920a4781b97cde85fd39f1cab44100d187f9b4e31fa571310cab71`. 이 해시는 스냅샷 식별용이며 live Figma 파일의 현재 상태 검증을 대체하지 않는다.
