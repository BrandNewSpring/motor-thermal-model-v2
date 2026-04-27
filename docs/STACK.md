# Motor Thermal Model v2 — Technology Stack

**버전**: 1.0  
**작성일**: 2026-04-09

---

## 1. 프레임워크 선택 이유 (Streamlit → FastAPI + React)

| 기준 | Streamlit v1 | **FastAPI + React v2** |
|------|-------------|----------------------|
| 모터 프로필 관리 (CRUD) | ❌ 상태관리 한계 | ✅ 완전한 상태 관리 |
| 실시간 최적화 진행 | △ spinner (블로킹) | ✅ SSE 스트리밍 |
| 복잡한 입력 폼 | △ 레이아웃 제약 | ✅ React Hook Form |
| 차트 커스터마이징 | △ matplotlib 정적 | ✅ Plotly.js 인터랙티브 |
| 향후 인증/팀 기능 | ❌ 불가 | ✅ FastAPI 미들웨어로 확장 |
| 데스크탑 배포 | △ 브라우저 의존 | ✅ Electron 래핑 가능 |

---

## 2. 전체 스택

### 2.1 Backend — FastAPI (Python)

```
Python 3.11+
fastapi          0.111+   # REST API + SSE
uvicorn[standard] 0.29+   # ASGI server
pydantic         2.7+     # 데이터 검증 & 직렬화
python-multipart 0.0.9+   # 파일 업로드
numpy            1.26+    # 수치 연산
scipy            1.13+    # ODE, 최적화
pandas           2.2+     # 데이터 처리
openpyxl         3.1+     # Excel 읽기/쓰기
```

**선택 이유**:
- Python 물리 엔진 그대로 재사용 (NumPy/SciPy)
- Pydantic v2로 엄격한 입력 검증
- SSE(`EventSourceResponse`)로 최적화 진행 상황 스트리밍
- 기존 thermal_model.py, data_loader.py 마이그레이션 용이

### 2.2 Frontend — React 18 + TypeScript

```
Node.js 20 LTS
React            18.3+    # UI 프레임워크
TypeScript       5.4+     # 타입 안전성
Vite             5.2+     # 빌드 도구 (CRA 대비 10x 빠름)
```

#### UI 컴포넌트

```
tailwindcss      3.4+     # 유틸리티 CSS
shadcn/ui        latest   # 고품질 컴포넌트 (Radix UI 기반)
lucide-react     0.370+   # 아이콘
```

#### 차트 & 시각화

```
react-plotly.js  2.6+     # 인터랙티브 차트 (Plotly.js 래퍼)
@types/plotly.js         # 타입 정의
```

#### 상태 관리

```
zustand          4.5+     # 클라이언트 전역 상태 (가볍고 단순)
@tanstack/react-query 5.40+ # 서버 상태, 캐싱, 재요청
```

#### 폼 & 검증

```
react-hook-form  7.51+    # 폼 상태 관리
zod              3.23+    # 스키마 검증 (Pydantic과 동형)
@hookform/resolvers      # zod-react-hook-form 브릿지
```

#### 파일 & 테이블

```
@tanstack/react-table 8.16+ # 대용량 데이터 테이블 (가상화)
```

**선택 이유**:
- Vite: 개발 서버 HMR 즉시 반영
- shadcn/ui: 복잡한 입력 폼(슬라이더, 탭, 아코디언)에 최적
- React Query: 캘리브레이션 결과 캐싱, 자동 재요청
- Zustand: Redux 대비 훨씬 단순, 모터 프로필 전역 관리

---

## 3. 프로젝트 구조

```
motor-thermal-model-v2/
├── backend/                    # FastAPI 서버
│   ├── main.py                 # 앱 엔트리포인트, 라우터 등록
│   ├── routers/
│   │   ├── calibration.py      # 캘리브레이션 API
│   │   ├── profiles.py         # 모터 프로필 CRUD
│   │   ├── prediction.py       # 온도 예측 API
│   │   └── files.py            # 파일 업로드/파싱
│   ├── core/
│   │   ├── motor_geometry.py   # 형상→열용량/초기 저항 계산
│   │   ├── thermal_model.py    # 3-노드 ODE
│   │   ├── loss_model.py       # 동손/철손 + 손실 맵
│   │   └── calibration.py      # 최적화 엔진
│   ├── schemas/
│   │   ├── motor.py            # MotorProfile, MotorGeometry 스키마
│   │   ├── calibration.py      # CalibRequest, CalibResult 스키마
│   │   └── data.py             # TestData, LossMap 스키마
│   ├── storage/
│   │   └── profiles.py         # JSON 기반 프로필 저장소
│   └── requirements.txt
│
├── frontend/                   # React 앱
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx      # 전체 레이아웃 (사이드바 + 메인)
│   │   │   └── providers.tsx   # QueryClient, 전역 상태 프로바이더
│   │   ├── pages/
│   │   │   ├── Calibration.tsx # 캘리브레이션 페이지
│   │   │   ├── Prediction.tsx  # 온도 예측 페이지
│   │   │   └── Profiles.tsx    # 모터 프로필 관리
│   │   ├── components/
│   │   │   ├── motor/          # 모터 형상 입력 폼
│   │   │   ├── calibration/    # 캘리브레이션 설정, 진행바, 결과
│   │   │   ├── charts/         # 온도 비교, R_th, 손실 차트
│   │   │   └── ui/             # shadcn/ui 컴포넌트 (자동 생성)
│   │   ├── hooks/
│   │   │   ├── useCalibration.ts  # 캘리브레이션 실행 + SSE 구독
│   │   │   └── useProfiles.ts     # 프로필 CRUD
│   │   ├── stores/
│   │   │   └── appStore.ts     # Zustand 전역 스토어
│   │   └── lib/
│   │       ├── api.ts          # axios 기반 API 클라이언트
│   │       └── utils.ts        # 공통 유틸
│   ├── package.json
│   └── vite.config.ts
│
├── docs/
│   ├── PRD.md
│   ├── STACK.md
│   └── SPEC.md
├── agents/
├── MEMORY.md
└── AGENTS.md
```

---

## 4. 개발 환경

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev   # http://localhost:5173
```

CORS: 개발 시 `localhost:5173` 허용, 프로덕션 시 동일 도메인 서빙.

---

## 5. API 통신 패턴

| 패턴 | 사용처 |
|------|--------|
| REST POST | 파일 업로드, 캘리브레이션 시작, 프로필 저장 |
| REST GET | 프로필 목록/상세, 예측 결과 |
| SSE | 캘리브레이션 실시간 진행 상황 |
| REST DELETE | 프로필 삭제 |

---

## 6. 배포 옵션

| 환경 | 방법 |
|------|------|
| 로컬 개발 | `uvicorn` + `vite dev` |
| 로컬 프로덕션 | `npm run build` → FastAPI가 `dist/` 정적 서빙 |
| 서버 배포 | Docker (python:3.11 + node:20 멀티스테이지 빌드) |
