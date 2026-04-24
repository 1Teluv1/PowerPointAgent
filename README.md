# PPT 생성 에이전트

Planner -> LoRA2 -> LoRA3 -> 코드 실행으로 이어지는 직렬형 PPT 생성 파이프라인 구현입니다.

## 구조
- `backend`: FastAPI + 직렬 오케스트레이터 + 실행/오류수정 루프
- `frontend`: React 기반 요청/상태/결과 UI
- `contracts`: 단계 간 JSON 계약 및 버저닝 정책
- `data`: LoRA2/LoRA3 학습 데이터 스펙/샘플
- `docs`: 환경 구성, 품질/릴리스 기준
- `scripts`: 데이터 검증/스모크 테스트 스크립트

## 루트에서 동시 실행 (권장)
```bash
npm run install:all
npm start
```

## 개별 실행
### 백엔드 실행
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 프론트엔드 실행
```bash
cd frontend
npm install
npm run dev
```

## 검증
```bash
python scripts/validate_training_data.py
```
