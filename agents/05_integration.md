# Agent 05 — Integration Agent

**전문 분야**: E2E 연결, 버그 수정, 성능 최적화, 최종 배포 준비  
**상태**: ⏳ PENDING  
**담당 Phase**: 5

---

## 세션 시작 절차

```
1. MEMORY.md 읽기 → Phase 5인지 확인, Phase 3 & 4 완료 여부 확인
2. 이 파일 전체 읽기
3. 백엔드 + 프론트엔드 동시 실행
4. E2E 시나리오 체크리스트 실행
```

---

## E2E 시나리오 (전체 플로우)

### 시나리오 A: 최초 캘리브레이션

```
1. 앱 접속 → 빈 화면 (프로필 없음)
2. "새 프로필 만들기" → 이름 입력 → 형상/물성 입력
3. 캘리브레이션 탭 → 시험 데이터 파일 업로드
4. 컬럼 매핑 (time, rpm, I_phase, T_amb, T_coil, torque)
5. Step 3: 발열 모델 선택 (간편 모드)
6. Step 4: n_starts=3, ss_penalty=5 설정
7. "캘리브레이션 실행" 클릭
8. SSE 진행바: Phase 1 → Phase 2 → Joint 표시 확인
9. 결과 표시: R₁, R₂, h_nat, h_rpm + 온도 비교 차트
10. 프로필 저장 → 프로필 목록에 나타남 확인
11. Excel 내보내기
```

### 시나리오 B: 손실 맵 모드

```
1. Step 3에서 "FEA 손실 맵" 선택
2. 손실 맵 CSV 업로드
3. 컬럼 매핑 (rpm, torque_nm, p_copper_w, p_iron_w)
4. 캘리브레이션 실행 → 결과 확인
5. Q_copper(map) vs Q_copper(direct) 비교 표시
```

### 시나리오 C: 온도 예측

```
1. 기존 프로필 선택
2. 예측 탭 → I=8A, RPM=2000, T_amb=25
3. T_coil_ss, T_core_ss, T_housing_ss 출력 확인
4. 격자 예측 (I: 2~15A, RPM: 500~4000) → 히트맵
```

### 시나리오 D: 프로필 비교

```
1. 프로필 2개 이상 있는 상태
2. 프로필 관리 탭 → 2개 선택 → 비교
3. 같은 조건 예측 오버레이 차트 표시
```

---

## 버그 체크리스트

- [ ] 파일 업로드 시 인코딩 (EUC-KR, UTF-8-BOM) 처리
- [ ] 컬럼 매핑 없이 캘리브레이션 시도 → 에러 메시지 정상 표시
- [ ] 최적화 실패(발산) 시 에러 처리 + SSE error event 표시
- [ ] 프로필 삭제 후 해당 프로필 선택 상태 초기화
- [ ] 브라우저 새로고침 시 프로필 목록 유지 (로컬 저장소)
- [ ] 손실 맵 범위 외 (RPM, torque) clamp 경고 표시
- [ ] T_coil > 300°C → 경고 배너

---

## 성능 최적화

- [ ] 격자 예측 병렬 처리 (ThreadPoolExecutor 확인)
- [ ] Plotly 차트 데이터 decimation (>5000pt → 1000pt 서브샘플)
- [ ] 파일 업로드 진행 표시
- [ ] React Query staleTime 적절히 설정 (프로필: 5분, 결과: Infinity)

---

## 배포 준비

```bash
# 프로덕션 빌드 테스트
cd frontend && npm run build
# → dist/ 생성 확인

# FastAPI 정적 서빙 테스트
cd backend && uvicorn main:app --port 8000
# → http://localhost:8000 접속 시 React 앱 표시 확인
```

---

## README 작성

`motor-thermal-model-v2/README.md` 작성:
- 설치 방법
- 실행 방법 (개발/프로덕션)
- 모터 형상 파라미터 입력 가이드
- 손실 맵 파일 형식

---

## 완료 후 MEMORY.md 업데이트

```markdown
### Phase 5: Integration ✅
- [x] E2E 시나리오 A~D 통과
- [x] 버그 체크리스트 완료
- [x] 프로덕션 빌드 확인
- [x] README.md 작성

## 프로젝트 상태: 🎉 COMPLETE
```

## 다음 단계 (선택적)

- 사용자 인증 추가 (FastAPI + JWT)
- Docker 이미지 빌드
- 다중 측정 채널 (T_housing 직접 측정 지원)
- 2D 방사형 온도 분포 시각화
