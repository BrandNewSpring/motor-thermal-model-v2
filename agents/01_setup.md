# Agent 01 — Setup Agent

**전문 분야**: 프로젝트 스캐폴딩, 의존성 설치, 빌드 도구 구성  
**상태**: ⏳ PENDING  
**담당 Phase**: 1

---

## 세션 시작 절차

```
1. MEMORY.md 읽기 → Phase 1이 현재 단계인지 확인
2. 이 파일 (agents/01_setup.md) 전체 읽기
3. docs/STACK.md 읽기 (사용할 패키지 목록 확인)
4. 아래 "수행 태스크" 순서대로 진행
```

---

## 수행 태스크 (순서 중요)

### Backend 스캐폴딩
- [ ] `backend/` 디렉토리 생성
- [ ] `backend/requirements.txt` 작성 (STACK.md 기준)
- [ ] `backend/main.py` 기본 FastAPI 앱 + CORS 설정
- [ ] `backend/routers/` 빈 라우터 파일 생성 (calibration, profiles, prediction, files)
- [ ] `backend/core/` 빈 모듈 파일 생성 (motor_geometry, thermal_model, loss_model, calibration)
- [ ] `backend/schemas/` 빈 스키마 파일 생성
- [ ] `backend/storage/profiles.py` JSON 저장소 기본 구조
- [ ] `backend/.env.example` 환경변수 예시

### Frontend 스캐폴딩
- [ ] `cd frontend && npm create vite@latest . -- --template react-ts`
- [ ] `tailwindcss`, `shadcn/ui` 초기화
- [ ] `zustand`, `@tanstack/react-query`, `react-hook-form`, `zod` 설치
- [ ] `react-plotly.js`, `@types/plotly.js` 설치
- [ ] `@tanstack/react-table` 설치
- [ ] `lucide-react` 설치
- [ ] `src/` 디렉토리 구조 생성 (SPEC.md 컴포넌트 트리 기준)
- [ ] `src/lib/api.ts` 기본 axios 클라이언트 (baseURL: http://localhost:8000)
- [ ] `src/stores/appStore.ts` Zustand 스토어 기본 구조
- [ ] `vite.config.ts` proxy 설정 (`/api` → `localhost:8000`)

### 검증
- [ ] `cd backend && uvicorn main:app --reload` 실행 확인 (404 없이 `{detail: Not Found}`)
- [ ] `cd frontend && npm run dev` 실행 확인 (빈 화면이라도 에러 없이 시작)
- [ ] `GET /api/profiles` 호출 시 `[]` 반환 확인

---

## 완료 후 MEMORY.md 업데이트 내용

```markdown
### Phase 1: Setup ✅
- [x] backend/ 스캐폴딩 완료
- [x] frontend/ Vite + React + shadcn/ui 초기화
- [x] 기본 실행 확인
```

## 다음 에이전트

**→ Physics Agent** (`agents/02_physics.md`)  
완료 후 git commit → git push → `/clear`
