# F1T 패션 추천 파이프라인

패션 검색 추천의 핵심 로직이 담긴 폴더예요.  
HTTP API는 `../backend/`에 있어요. 이 배포용 스냅샷에는 런타임에 필요하지 않은 실험/데이터 구축 자산은 포함하지 않습니다.

---

## 파이프라인 구조

진입점은 `recommendation_service.py`이며, 아래 5단계를 순서대로 실행해요.

| 파일 | 역할 |
|---|---|
| `intent/intent_extraction.py` | Gemini VLM으로 사용자가 명시한 속성만 추출 (추론 금지) |
| `retrieval/candidate_selection.py` | 속성 기반 Supabase 테이블 라우팅 + SQL 후보 필터링 |
| `target_description/target_description_generation.py` | Gemini로 검색용 영문 target description 생성 |
| `retrieval/target_description_retrieval.py` | gemini-embedding-2로 텍스트 → 768차원 벡터 인코딩 |
| `target_description/recommendation_explanation.py` | 매칭된 속성 기반 한국어 추천 이유 생성 |

오케스트레이터:

| 파일 | 역할 |
|---|---|
| `recommendation_service.py` | 파이프라인 전체 조율 (병렬 실행 포함) |
| `vector_db_client.py` | Supabase pgvector RPC 호출 클라이언트 |

---

## 전체 흐름

```
사용자 입력 (텍스트 + 이미지?)
    ↓
[1단계 + 2단계 — 병렬]
  ├→ 메타데이터 추출 — Gemini VLM (명시된 속성만)
  └→ Target Description 생성 — Gemini gemini-3.5-flash
    ↓
[3단계] 테이블 라우팅 + SQL 후보 필터링
    ↓
[4단계 — 병렬]
  ├→ Gemini Embedding 인코딩 → Supabase 벡터 검색
  └→ (fabric 속성 있을 시) fabric 임베딩 인코딩
    ↓
[5단계] 한국어 추천 이유 생성
    ↓
API 응답 반환
```

베이스라인과의 차이: 베이스라인은 target description 생성부터 시작하지만, 우리 파이프라인은 메타데이터로 먼저 범위를 좁혀 정확도를 높여요.

---

## 유사도 스코어 계산

벡터 검색 결과의 최종 유사도는 두 가지 임베딩의 가중 합산이에요:

```
최종 점수 = 0.8 × 이미지 유사도 + 0.2 × fabric 유사도
```

- **이미지 유사도**: `gemini_image_embedding_768` — 상품 이미지 vs. target description 텍스트
- **fabric 유사도**: `gemini_fabric_text_embedding_768` — 상품 소재 설명 vs. 사용자 요청 소재
- fabric 속성이 없거나 임베딩이 없으면 이미지 유사도 100%로 폴백

가중치는 `recommendation_service.py`의 `_rank_stored_gemini_vectors(fabric_weight=0.2)` 및 Supabase RPC 함수 `match_fashion_items_768`에서 적용돼요.

---

## 로컬 실행

```bash
# 1. 환경변수 설정
cp pipeline/.env.example pipeline/.env
# GEMINI_API_KEY, SUPABASE_URL, SUPABASE_KEY, FRONTEND_ORIGINS 입력

# 2. 의존성 설치
conda create -n f1t python=3.11 -y
conda activate f1t
pip install -r pipeline/requirements.txt
cd frontend && npm install && cd ..

# 3. 백엔드 실행 (f1t_new/ 루트에서)
uvicorn backend.api:app --host 0.0.0.0 --port 8000 --reload

# 4. 프론트엔드 실행 (다른 터미널)
cd frontend && npm run dev
```

프론트엔드: `http://localhost:5173`

---

## API

`POST /search` — `multipart/form-data`

| 파라미터 | 필수 | 설명 |
|---|---|---|
| `query` | 둘 중 하나 | 텍스트 검색어 |
| `image` | 둘 중 하나 | 참조 이미지 파일 |
| `top_k` | 선택 | 결과 수 (기본값 10) |
| `table` | 선택 | `musinsa_top_clothes` / `musinsa_pants` / `musinsa_skirt_dress` |
| `category2_keyword` | 선택 | 세부 카테고리 키워드 (예: `원피스`, `스커트`) |
| `pipeline_method` | 선택 | `intent` (기본값) |
| `provider` | 선택 | `gemini` (기본값) |

응답 예시:
```json
{
  "provider": "gemini",
  "target_description": "Oversized black long-sleeve hoodie",
  "target_description_ko": "오버사이즈 블랙 긴팔 후드티",
  "recommendation_reason": "요청하신 긴 소매와 오버사이즈 핏 조건에 맞는 후드 상의를 중심으로 찾았습니다. 여유 있는 실루엣과 후드 디테일이 캐주얼한 분위기를 살려줘 데일리로 입기 좋아 추천했습니다.",
  "pipeline": {
    "id": "intent_text_table_narrowing",
    "parsed_attributes": { "sleeve": "long", "fit": "oversized" },
    "parallel_execution": { "intent_and_target_description": true }
  },
  "results": [
    {
      "rank": 1,
      "name": "...",
      "similarity": 0.712
    }
  ]
}
```

---

## 환경변수 (.env)

| 변수 | 설명 |
|---|---|
| `GEMINI_API_KEY` | Gemini API 키 |
| `SUPABASE_URL` | Supabase 프로젝트 URL |
| `SUPABASE_KEY` | Supabase 서비스 키 |
| `FRONTEND_ORIGINS` | CORS 허용 출처 |

---

## Supabase 설정

벡터 검색을 위해 두 가지가 Supabase에 설정되어 있어야 해요:

**1. HNSW 인덱스** (3개 테이블 모두):
```sql
CREATE INDEX ON musinsa_top_clothes USING hnsw (gemini_image_embedding_768 vector_cosine_ops);
CREATE INDEX ON musinsa_pants USING hnsw (gemini_image_embedding_768 vector_cosine_ops);
CREATE INDEX ON musinsa_skirt_dress USING hnsw (gemini_image_embedding_768 vector_cosine_ops);

CREATE INDEX ON musinsa_top_clothes USING hnsw (gemini_fabric_text_embedding_768 vector_cosine_ops);
CREATE INDEX ON musinsa_pants USING hnsw (gemini_fabric_text_embedding_768 vector_cosine_ops);
CREATE INDEX ON musinsa_skirt_dress USING hnsw (gemini_fabric_text_embedding_768 vector_cosine_ops);
```

**2. RPC 함수** `match_fashion_items_768`:  
유사도 계산 공식 `0.8 × 이미지 + 0.2 × fabric`을 적용하는 PostgreSQL 함수.  
Supabase SQL Editor에서 직접 생성/수정.

**3. 임베딩 빌드**:  
배포 환경에서는 이미 구축된 Supabase 테이블과 RPC를 사용합니다. 임베딩 생성 스크립트와 실험 산출물은 이 배포용 스냅샷에서 제외했습니다.
