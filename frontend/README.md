# F1T Frontend

Vite/React 기반의 패션 검색 UI입니다. 백엔드 API는 저장소 루트에서 `uvicorn backend.api:app --host 0.0.0.0 --port 8000`로 실행합니다.

## 환경 설정

프론트엔드 폴더에서 처음 한 번만 의존성을 설치하고 로컬 환경변수 파일을 만듭니다.

```bash
cd frontend
npm install
cp .env.example .env.local
```

`frontend/.env.local`에는 Vercel 대시보드에도 넣을 공개 설정값을 채웁니다.

```env
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
VITE_API_BASE_URL=http://localhost:8000
```

## 실행

```bash
npm run dev -- --host 127.0.0.1 --port 5173
```

브라우저에서는 `http://127.0.0.1:5173/`로 접속합니다.

## 개발 명령

```bash
npm run lint
npm run build
npm run preview
```
