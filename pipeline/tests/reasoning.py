import os
import json
import re
from pathlib import Path
from PIL import Image
from lmdeploy import pipeline, TurbomindEngineConfig, GenerationConfig
from supabase import create_client, Client
import requests
from io import BytesIO

# ===================== CONFIG =====================
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")

SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")

TABLE_NAME = "test_top_clothes"
IMAGE_URL_COLUMN = "image_url"  # 테이블 내 이미지 URL 컬럼명 (필요시 수정)
GT_SLEEVE_COLUMN = "sleeve"     # 정답 sleeve 컬럼명

MODEL_NAME = "Qwen/Qwen3-VL-32B-Instruct"
TOP_K = 1  # sleeve는 후보 3개 중 1개 선택이므로 K=1

SLEEVE_CANDIDATES = ["long", "short", "sleeveless"]

INSTRUCTION_TEXT = """You are a fashion attribute classification expert.
You are given an image of a top clothing item.
Your task is to identify the sleeve type of the clothing in the image.

## Sleeve Candidates
Choose ONLY one of the following options:
- long: The sleeve covers the full arm (long sleeve)
- short: The sleeve covers roughly half the arm (short sleeve)
- sleeveless: No sleeve at all (tank top, camisole, etc.)

## Output Format
Return ONLY a valid JSON object with the following structure:
{
    "sleeve": "long | short | sleeveless"
}

Do NOT output anything outside of the JSON object."""


# ===================== UTILS =====================
def parse_json_from_text(text):
    """LLM 출력에서 JSON 추출"""
    try:
        match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        match = re.search(r'(\{.*\})', text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        return None
    except Exception as e:
        print(f"  ⚠️ JSON parse error: {e}")
        return None


def load_image_from_url(url: str) -> Image.Image | None:
    """URL에서 이미지 로드"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return Image.open(BytesIO(response.content)).convert("RGB")
    except Exception as e:
        print(f"  ❌ Image load failed ({url[:60]}...): {e}")
        return None


def fetch_test_data(supabase: Client) -> list[dict]:
    """Supabase에서 테스트 데이터 가져오기"""
    print(f"📦 Fetching data from '{TABLE_NAME}'...")
    response = supabase.table(TABLE_NAME).select("*").execute()
    data = response.data
    print(f"  → {len(data)} rows fetched")
    return data


# ===================== EVAL =====================
def evaluate_sleeve(pipe, gen_config, data: list[dict]) -> dict:
    """sleeve 속성 예측 및 정확도 평가"""
    results = []
    correct = 0
    total = 0
    failed = 0

    for i, row in enumerate(data):
        print(f"\n[{i+1}/{len(data)}] ID: {row.get('id', 'N/A')}")

        # 이미지 로드
        image_url = row.get(IMAGE_URL_COLUMN)
        if not image_url:
            print("  ⚠️ No image URL, skipping")
            failed += 1
            continue

        pil_img = load_image_from_url(image_url)
        if pil_img is None:
            failed += 1
            continue

        # 정답 가져오기
        gt_sleeve = row.get(GT_SLEEVE_COLUMN, "").strip().lower()
        if gt_sleeve not in SLEEVE_CANDIDATES:
            print(f"  ⚠️ Unknown gt_sleeve value: '{gt_sleeve}', skipping")
            failed += 1
            continue

        # 추론
        try:
            outputs = pipe(
                [([pil_img], INSTRUCTION_TEXT)],
                gen_config=gen_config
            )
            out_text = outputs[0].text.strip()
        except Exception as e:
            print(f"  ❌ Inference error: {e}")
            failed += 1
            continue

        # 파싱
        parsed = parse_json_from_text(out_text)
        if not parsed or "sleeve" not in parsed:
            print(f"  ⚠️ Parse failed. Raw: {out_text[:100]}")
            failed += 1
            continue

        pred_sleeve = parsed["sleeve"].strip().lower()
        is_correct = (pred_sleeve == gt_sleeve)
        if is_correct:
            correct += 1
        total += 1

        result = {
            "id": row.get("id"),
            "image_url": image_url,
            "gt_sleeve": gt_sleeve,
            "pred_sleeve": pred_sleeve,
            "reasoning": parsed.get("reasoning", ""),
            "correct": is_correct
        }
        results.append(result)

        status = "✅" if is_correct else "❌"
        print(f"  GT: {gt_sleeve} | Pred: {pred_sleeve} {status}")
        print(f"  Reasoning: {parsed.get('reasoning', '')[:100]}")

    # 최종 결과
    accuracy = correct / total if total > 0 else 0.0
    summary = {
        "total": total,
        "correct": correct,
        "failed": failed,
        "accuracy": round(accuracy, 4),
        "results": results
    }

    return summary


# ===================== MAIN =====================
def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_KEY 환경변수가 설정되지 않았습니다.")

    # Supabase 연결
    print(f"🔌 Connecting to Supabase...")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # 데이터 가져오기
    data = fetch_test_data(supabase)
    if not data:
        print("❌ No data fetched. Check table name or Supabase connection.")
        return

    # 모델 초기화
    print(f"\n🚀 Initializing Pipeline: {MODEL_NAME}...")
    backend_config = TurbomindEngineConfig(tp=2, session_len=32768, cache_max_entry_count=0.8)
    pipe = pipeline(MODEL_NAME, backend_config=backend_config)
    gen_config = GenerationConfig(temperature=0.0, max_new_tokens=512, stop_words=["<|im_end|>"])

    # 평가 실행
    print(f"\n🧪 Starting sleeve evaluation on {len(data)} samples...")
    summary = evaluate_sleeve(pipe, gen_config, data)

    # 결과 출력
    print("\n" + "="*60)
    print("📊 [Evaluation Summary]")
    print("="*60)
    print(f"  Total evaluated : {summary['total']}")
    print(f"  Correct         : {summary['correct']}")
    print(f"  Failed/Skipped  : {summary['failed']}")
    print(f"  Accuracy        : {summary['accuracy'] * 100:.2f}%")
    print("="*60)

    # 오답 분석
    wrong = [r for r in summary["results"] if not r["correct"]]
    if wrong:
        print(f"\n❌ Wrong predictions ({len(wrong)} cases):")
        for w in wrong:
            print(f"  ID: {w['id']} | GT: {w['gt_sleeve']} | Pred: {w['pred_sleeve']}")

    # 결과 저장
    output_path = "sleeve_eval_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=4, ensure_ascii=False)
    print(f"\n💾 Results saved to '{output_path}'")


if __name__ == "__main__":
    main()
