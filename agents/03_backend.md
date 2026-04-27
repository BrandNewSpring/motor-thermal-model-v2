# Agent 03 — Backend Agent

**전문 분야**: FastAPI 서버, REST API, SSE, 프로필 저장소  
**상태**: ⏳ PENDING  
**담당 Phase**: 3

---

## 세션 시작 절차

```
1. MEMORY.md 읽기 → Phase 3인지 확인, Phase 2 완료 여부 확인
2. 이 파일 전체 읽기
3. docs/SPEC.md 섹션 1~2 읽기 (스키마, API 엔드포인트)
4. backend/core/ 구현 파일들 파악 (Physics Agent 산출물)
5. 아래 태스크 순서대로 구현
```

---

## 전제 조건 확인

```bash
# Physics Agent 산출물이 있는지 확인
ls backend/core/motor_geometry.py
ls backend/core/thermal_model.py
ls backend/core/loss_model.py
ls backend/core/calibration.py
# 없으면 MEMORY.md 확인 후 Physics Agent 먼저 진행
```

---

## 태스크 1: Pydantic 스키마 (`backend/schemas/`)

`SPEC.md` 섹션 1 기준으로 구현:

```
schemas/
├── motor.py        # MotorGeometry, MaterialProps, CoilParams, MotorProfile
├── calibration.py  # CalibSettings, CalibRequest, ThermalParams, CalibResult
└── data.py         # LossMapEntry, ColumnMapping, DataSummary
```

---

## 태스크 2: 파일 업로드 라우터 (`backend/routers/files.py`)

```python
POST /api/files/upload
- multipart form data
- 지원: .csv, .xlsx, .xls
- 파일 ID 생성 (UUID), 저장소에 보관
- 컬럼 자동 감지 반환

GET /api/files/{file_id}/columns
POST /api/files/{file_id}/map-columns
DELETE /api/files/{file_id}
```

파일 저장: `~/.mtm_v2/uploads/{file_id}_{original_name}`

---

## 태스크 3: 프로필 저장소 (`backend/storage/profiles.py`)

```python
class ProfileStorage:
    def __init__(self, base_dir: Path): ...
    def list_profiles(self) -> List[MotorProfile]: ...
    def get_profile(self, id: str) -> MotorProfile: ...
    def save_profile(self, profile: MotorProfile) -> MotorProfile: ...
    def delete_profile(self, id: str) -> bool: ...
    def update_calib_result(self, id: str, result: CalibResult): ...
```

저장 경로: `~/.mtm_v2/profiles/{uuid}.json`

---

## 태스크 4: 프로필 라우터 (`backend/routers/profiles.py`)

```
GET    /api/profiles                 → List[MotorProfileSummary]
POST   /api/profiles                 → MotorProfile
GET    /api/profiles/{id}            → MotorProfile
PUT    /api/profiles/{id}            → MotorProfile
DELETE /api/profiles/{id}            → 204
POST   /api/profiles/{id}/copy       → MotorProfile
POST   /api/profiles/compute-geometry → GeometryPreview
```

---

## 태스크 5: 캘리브레이션 라우터 (`backend/routers/calibration.py`)

```
POST /api/calibration/start
  - CalibRequest body
  - background task로 calibrate_3node() 실행
  - job_id 즉시 반환

GET /api/calibration/{job_id}/stream  ← SSE
  - EventSourceResponse
  - progress_callback → SSE event 발행
  - 완료 시 result JSON 포함 done event

GET /api/calibration/{job_id}/result
  - 완료된 결과 반환 (polling용)
```

**SSE 구현 방법**:
```python
from fastapi.responses import StreamingResponse
import asyncio
import json

async def event_stream(job_id: str):
    queue = get_job_queue(job_id)  # asyncio.Queue
    while True:
        event = await queue.get()
        yield f"data: {json.dumps(event)}\n\n"
        if event["type"] in ("done", "error"):
            break

@router.get("/{job_id}/stream")
async def stream(job_id: str):
    return StreamingResponse(event_stream(job_id),
                             media_type="text/event-stream")
```

progress_callback은 동기 함수에서 `asyncio.run_coroutine_threadsafe`로 큐에 넣는다.

---

## 태스크 6: 예측 라우터 (`backend/routers/prediction.py`)

```
POST /api/prediction/steady-state
  - simulate_3node를 충분히 긴 시간(3×tau) 실행 후 마지막 값 반환
  - thermal_runaway 감지 (T_coil > 500°C → 400 에러)

POST /api/prediction/grid
  - (I_range, RPM_range) N×N 격자 계산
  - 병렬: ThreadPoolExecutor 사용
```

---

## 태스크 7: 내보내기 라우터 (`backend/routers/export.py`)

```
GET /api/export/{job_id}/excel
  - openpyxl로 Excel 생성
  - 시트: 모델 요약 / Calibration 상세 / T_core T_housing 추정값 / 격자 예측
```

---

## 태스크 8: `main.py` 완성

```python
app = FastAPI(title="Motor Thermal Model v2", version="2.0.0")

# CORS
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], ...)

# 라우터 등록
app.include_router(files.router,       prefix="/api/files",       tags=["files"])
app.include_router(profiles.router,    prefix="/api/profiles",    tags=["profiles"])
app.include_router(calibration.router, prefix="/api/calibration", tags=["calibration"])
app.include_router(prediction.router,  prefix="/api/prediction",  tags=["prediction"])
app.include_router(export.router,      prefix="/api/export",      tags=["export"])

# 프로덕션: React build 정적 서빙
app.mount("/", StaticFiles(directory="../frontend/dist", html=True), name="static")
```

---

## 태스크 9: API 스모크 테스트

```bash
# 서버 시작
uvicorn main:app --reload

# 테스트
curl -X GET http://localhost:8000/api/profiles    # → []
curl -X POST http://localhost:8000/api/files/upload -F "file=@test.csv"
curl -X POST http://localhost:8000/api/profiles/compute-geometry -H "Content-Type: application/json" \
  -d '{"D_motor_mm":106,"L_motor_mm":48.85,"m_motor_g":1200,...}'
```

---

## 완료 후 MEMORY.md 업데이트

```markdown
### Phase 3: Backend API ✅
- [x] Pydantic 스키마 (motor, calibration, data)
- [x] 파일 업로드/파싱 API
- [x] 프로필 CRUD (JSON 저장)
- [x] 캘리브레이션 시작 + SSE 스트리밍
- [x] 온도 예측 API (단일 + 격자)
- [x] Excel 내보내기
- [x] 스모크 테스트 통과
```

## 다음 에이전트

**→ Frontend Agent** (`agents/04_frontend.md`)  
완료 후 git commit → git push → `/clear`
