from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from pipeline.env import load_pipeline_env
from pipeline.recommendation_service import (
    DEFAULT_PIPELINE_METHOD,
    DEFAULT_RECOMMENDATION_COUNT,
    FashionRecommendationPipeline,
    MAX_TOP_K,
    PIPELINE_MODE,
    VALID_TABLES,
    needs_reference_image,
)
from pipeline.intent.intent_extraction import (
    analyze_fashion_intent,
    resolve_intent_model,
)
from pipeline.retrieval.candidate_selection import retrieve_products
from pipeline.target_description.target_description_generation import (
    OPENAI_MODEL_NAME,
    QWEN_FALLBACK_MODEL_NAME,
    resolve_target_description_model,
)


load_pipeline_env()


def parse_origins() -> list[str]:
    raw = os.getenv("FRONTEND_ORIGINS", "*").strip()
    if raw == "*":
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.search_service = FashionRecommendationPipeline()
    yield


app = FastAPI(title="F1T Supabase Vector Search API", lifespan=lifespan)
_origins = parse_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "mode": PIPELINE_MODE,
        "provider": os.getenv("VLM_PROVIDER", "gemini"),
    }


@app.get("/status")
def status_check(request: Request) -> dict:
    result: dict = {}

    clip_model = os.getenv("CLIP_MODEL", "ViT-B-32")
    result["clip_model"] = clip_model
    try:
        service: FashionRecommendationPipeline = request.app.state.search_service
        vector = service.retriever.encode_text(["test"])
        result["clip"] = f"ok (dim={len(vector[0].tolist())})"
    except Exception as exc:
        result["clip"] = f"error: {exc}"

    result["gemini_key_set"] = bool(os.getenv("GEMINI_API_KEY"))
    result["supabase_url_set"] = bool(os.getenv("SUPABASE_URL"))
    result["supabase_key_set"] = bool(os.getenv("SUPABASE_KEY"))
    return result


@app.get("/models")
def models_info() -> dict[str, str]:
    qwen_model = (
        os.getenv("QWEN_FALLBACK_MODEL")
        or os.getenv("QWEN3_VL_MODEL")
        or QWEN_FALLBACK_MODEL_NAME
    )
    return {
        "gemini": resolve_target_description_model(),
        "gemini_intent": resolve_intent_model(),
        "gemini_target_description": resolve_target_description_model(),
        "openai": os.getenv("OPENAI_MODEL", OPENAI_MODEL_NAME),
        "qwen": qwen_model.split("/")[-1],
    }


@app.post("/search")
def search(
    request: Request,
    query: str | None = Form(default=None),
    image: UploadFile | None = File(default=None),
    top_k: int = Form(default=DEFAULT_RECOMMENDATION_COUNT),
    table: str | None = Form(default=None),
    category2: str | None = Form(default=None),
    category2_keyword: str | None = Form(default=None),
    provider: str | None = Form(default=None),
    pipeline_method: str = Form(default=DEFAULT_PIPELINE_METHOD),
) -> dict[str, Any]:
    normalized_query = (query or "").strip()
    table_filter = (table or "").strip() or None
    category2_filter = (category2 or "").strip() or None
    category2_keyword_filter = (category2_keyword or "").strip() or None
    image_bytes = None
    image_mime_type = None

    if top_k < 1 or top_k > MAX_TOP_K:
        raise HTTPException(
            status_code=400,
            detail=f"top_k must be between 1 and {MAX_TOP_K}.",
        )

    if table_filter and table_filter not in VALID_TABLES:
        raise HTTPException(status_code=400, detail="Invalid table filter.")

    if image:
        image_mime_type = image.content_type or "image/jpeg"
        if not image_mime_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="image must be an image file.")
        image_bytes = image.file.read()

    if not normalized_query and not image_bytes:
        raise HTTPException(status_code=400, detail="query or image is required.")

    if normalized_query and not image_bytes and needs_reference_image(normalized_query):
        raise HTTPException(status_code=400, detail="이미지를 첨부하세요.")

    service: FashionRecommendationPipeline = request.app.state.search_service
    try:
        target_description, target_description_ko, reasoning_metadata, raw_results = (
            service.search(
                query=normalized_query,
                top_k=top_k,
                image_bytes=image_bytes,
                image_mime_type=image_mime_type,
                table_filter=table_filter,
                category2_filter=category2_filter,
                category2_keyword_filter=category2_keyword_filter,
                provider=provider,
                pipeline_method=pipeline_method,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Internal error: {exc}") from exc

    return {
        "mode": PIPELINE_MODE,
        "provider": reasoning_metadata["provider"],
        "pipeline": reasoning_metadata.get("pipeline"),
        "target_description": target_description,
        "target_description_ko": target_description_ko,
        "recommendation_reason": reasoning_metadata.get("recommendation_reason"),
        "reasoning": reasoning_metadata,
        "results": [
            {
                "rank": rank,
                "id": str(row.get("id") or ""),
                "source_table": row.get("source_table"),
                "name": row.get("name"),
                "brand": row.get("brand"),
                "image_url": row.get("image_url"),
                "category1": row.get("category1"),
                "category2": row.get("category2"),
                "price": row.get("price"),
                "color": row.get("color"),
                "sleeve": row.get("sleeve"),
                "length": row.get("length"),
                "sex": row.get("sex"),
                "season": row.get("season"),
                "stretch": row.get("stretch"),
                "thickness": row.get("thickness"),
                "fit": row.get("fit"),
                "fabric": row.get("fabric"),
                "similarity": float(row.get("similarity") or 0),
            }
            for rank, row in enumerate(raw_results, start=1)
        ],
    }


@app.post("/analyze")
def analyze(
    text_input: str = Form(...),
    image_input: UploadFile | None = File(None),
) -> dict[str, Any]:
    """VLM으로 텍스트/이미지를 분석하여 속성 추론"""
    try:
        # 이미지 경로 처리
        image_path = None
        if image_input:
            # 임시 이미지 저장 (실제로는 메모리에서 처리 권장)
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                tmp.write(image_input.file.read())
                image_path = tmp.name

        # VLM 추론 실행
        result = analyze_fashion_intent(text_input, image_path)
        return {"status": "success", "inferred_attributes": result}

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis error: {exc}") from exc


@app.post("/retrieve")
def retrieve(request_body: dict) -> dict[str, Any]:
    """추론된 속성을 기반으로 상품 검색"""
    try:
        # JSON Body에서 inferred_attributes 추출
        inferred_attributes = request_body.get("inferred_attributes", {})

        # Retrieval 실행
        products = retrieve_products(inferred_attributes)
        return {
            "status": "success",
            "products": products,
            "count": len(products),
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Retrieval error: {exc}") from exc
