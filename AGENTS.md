# AGENTS.md — 에이전트 핸드오프 프로토콜

## 에이전트 운영 원칙

1. **세션 시작 시**: `MEMORY.md`를 먼저 읽어 현재 Phase와 미완료 작업을 파악한다.
2. **작업 중**: 각 태스크 완료 시 `MEMORY.md`의 체크리스트를 업데이트한다.
3. **세션 종료 전**: `MEMORY.md`에 완료 내역과 다음 단계를 반드시 기록한다.
4. **에이전트 교체 시**: 다음 에이전트에게 `/clear`로 컨텍스트를 초기화하도록 안내한다.
5. **각 에이전트는 자신의 전문 범위만 수행한다.** 범위를 벗어난 작업은 다음 에이전트에게 위임한다.

---

## 에이전트 로스터

| ID | 에이전트 | 전문 분야 | 파일 | 상태 |
|----|---------|----------|------|------|
| 00 | Planning Agent | 요구사항 정의, 문서화 | `agents/00_planning.md` | ✅ DONE |
| 01 | Setup Agent | 프로젝트 스캐폴딩, 패키지 설치 | `agents/01_setup.md` | ⏳ PENDING |
| 02 | Physics Agent | 열전달 물리 엔진 구현 | `agents/02_physics.md` | ⏳ PENDING |
| 03 | Backend Agent | FastAPI 서버, API 엔드포인트 | `agents/03_backend.md` | ⏳ PENDING |
| 04 | Frontend Agent | React UI, 컴포넌트, 차트 | `agents/04_frontend.md` | ⏳ PENDING |
| 05 | Integration Agent | E2E 연결, 버그 수정, 폴리싱 | `agents/05_integration.md` | ⏳ PENDING |

---

## 핸드오프 흐름

```
[00 Planning] ──승인 후──> [01 Setup] ──> [02 Physics] ──> [03 Backend]
                                                                 ↓
                                               [05 Integration] <── [04 Frontend]
```

---

## 세션 시작 표준 절차

새 에이전트가 시작할 때 다음을 실행:

```
1. MEMORY.md 읽기
2. 현재 Phase 확인
3. 해당 에이전트 파일 (agents/XX_name.md) 읽기
4. 완료된 작업 목록 확인
5. 미완료 작업부터 시작
```

---

## 세션 종료 표준 절차

에이전트가 작업을 마칠 때:

```
1. MEMORY.md "완료된 작업" 섹션 업데이트 (체크박스)
2. MEMORY.md "현재 단계" 및 "다음 단계" 업데이트
3. MEMORY.md "변경 이력"에 한 줄 추가
4. git commit (완료된 작업 기준)
5. git push
6. 사용자에게: "Phase XX 완료. 다음은 [YY Agent]입니다. /clear 후 시작하세요."
```
