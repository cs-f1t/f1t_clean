# F1T

## 처음 실행하기

처음 이 저장소를 복사한 사람은 저장소 루트에서 아래 순서대로 백엔드와 프론트엔드를 각각 실행합니다.

### 1. 저장소 받기

```bash
cd <프로젝트를 받을 상위 폴더>
git clone https://github.com/cs-f1t/f1t_new.git
cd f1t_new
```

### 2. 백엔드 환경 만들기

백엔드는 Python conda 환경 `f1t`에서 실행합니다. 처음 한 번만 환경을 만들고 패키지를 설치하면 됩니다.

```bash
conda create -n f1t python=3.11 -y
conda activate f1t
pip install -r backend/requirements.txt
cp pipeline/.env.example pipeline/.env
```

`pipeline/.env` 파일에 아래 값들을 채워야 합니다.

```env
GEMINI_API_KEY=
SUPABASE_URL=
SUPABASE_KEY=
FRONTEND_ORIGINS=http://localhost:5173
```

### 3. 프론트엔드 환경 만들기

프론트엔드는 Node.js/npm으로 실행합니다. 처음 한 번만 패키지를 설치합니다.

```bash
cd frontend
npm install
cp .env.example .env.local
cd ..
```

`frontend/.env.local`에는 프론트엔드에서 직접 쓰는 공개 설정값을 채웁니다.

```env
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
VITE_API_BASE_URL=http://localhost:8000
```

## 실행 명령어

백엔드 터미널:

```bash
conda activate f1t
uvicorn backend.api:app --host 0.0.0.0 --port 8000
```

프론트엔드 터미널:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

브라우저에서는 `http://127.0.0.1:5173/`로 접속합니다.

위 명령은 저장소 루트에서 시작한다고 가정합니다.

## 폴더 구조

- `backend/`: FastAPI 엔드포인트, HTTP 입력 검증, 응답 직렬화를 담당합니다.
- `pipeline/`: VLM reasoning, 메타데이터 추출, 검색 계획, Supabase 벡터 검색 등 핵심 추천 파이프라인 코드가 들어 있습니다.
- `pipeline/tests/`: 핵심 추천 파이프라인의 실험/스모크 테스트 산출물이 들어 있습니다.
- `frontend/`: 패션 검색/추천 결과를 확인하기 위한 Vite/React 기반 프론트엔드입니다.

이 배포용 스냅샷에서는 런타임에 필요하지 않은 `archive/`, `experiments/`, `database/` 폴더를 제외했습니다.
