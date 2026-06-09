import os
import json
import re
from pathlib import Path
from PIL import Image
import google.generativeai as genai
import requests
from io import BytesIO

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DEFAULT_GEMINI_API_KEY = (
    os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
)
MODEL_NAME = "gemini-3.5-flash"

INFERENCE_PROMPT_TEMPLATE = """You are a fashion search intent analyzer.

User query: {user_query}

{image_instruction}

---

Step 1 — Identify mentioned attributes (think first):
Read the query carefully. List ONLY the attributes the user explicitly stated. Do NOT add anything the user did not say.
Ask yourself: "Did the user actually say this?" If not, exclude it.

CRITICAL — Do NOT infer attributes from the garment type name itself.
Examples of forbidden inference:
- User says "티셔츠" → do NOT add sleeve:short (user didn't mention sleeve)
- User says "치마" or "원피스" → do NOT add sex:female (user didn't mention sex)
- User says "슬렉스" → do NOT add length:long (user didn't mention length)
- User says "후드" → do NOT add sex:unisex (user didn't mention sex)
Only category1 may be derived from the garment type name. Nothing else.

Step 2 — Map to schema:
For each attribute identified in Step 1, assign a value using the schema below.

Attributes to extract (use predefined values only):
- category1: top / pants / dress / skirt
- sleeve: long / short / sleeveless  → only for tops
- length: long / half / short  → only for pants / skirt / dress
- sex: male / female / unisex
- season: spring / summer / fall / winter
- stretch: yes / no
- thickness: thin / medium / thick
- fit: slim / regular / loose / oversize

Step 3 — Output:
Respond with valid JSON only. Include ONLY the extracted attributes from Step 1 and 2. No extras.

{{
  "<attribute>": "<value>",
  "reasoning": "한국어로, 각 속성에 대해 사용자가 실제로 말한 표현을 인용하여 설명. 사용자가 직접 말하지 않은 속성은 절대 포함하지 말 것."
}}"""


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


def load_image_from_path(path: str) -> Image.Image | None:
    """로컬 경로에서 이미지 로드"""
    try:
        if not os.path.exists(path):
            print(f"  ❌ Image file not found: {path}")
            return None
        return Image.open(path).convert("RGB")
    except Exception as e:
        print(f"  ❌ Image load failed ({path}): {e}")
        return None


# ===================== INTENT ANALYSIS MODULE =====================
class IntentAnalysisModule:
    """사용자 쿼리와 이미지로부터 패션 속성을 추론하는 모듈"""

    def __init__(self, api_key: str | None = None, model_name=MODEL_NAME):
        """
        Args:
            api_key: Google Gemini API 키
            model_name: Gemini 모델 이름
        """
        api_key = api_key or DEFAULT_GEMINI_API_KEY
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY / GOOGLE_API_KEY 환경변수가 설정되지 않았습니다.")

        print(f"🚀 Initializing IntentAnalysisModule: {model_name}")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model_name=model_name,
            generation_config=genai.GenerationConfig(
                temperature=0.1,
                max_output_tokens=1024,
            )
        )
        print("✅ IntentAnalysisModule initialized\n")

    def infer_single(self, user_query: str, image_path: str = None, image_url: str = None) -> dict:
        """
        단일 사용자 쿼리에 대해 속성 추론

        Args:
            user_query: 사용자 텍스트 쿼리
            image_path: 로컬 이미지 경로 (선택사항)
            image_url: 이미지 URL (선택사항)

        Returns:
            추론된 속성 딕셔너리
        """

        # 이미지 로드
        image = None
        loaded_image_url = None

        if image_path:
            print(f"  📷 Loading image from path: {image_path}")
            image = load_image_from_path(image_path)
            loaded_image_url = image_path if image else None

        elif image_url:
            print(f"  📷 Loading image from URL: {image_url[:60]}...")
            image = load_image_from_url(image_url)
            loaded_image_url = image_url if image else None

        # 이미지 유무에 따른 지침 생성
        if image:
            image_instruction = "Reference image provided: use the image ONLY to determine the value of attributes the user explicitly mentioned in the query (e.g. if user asked about color, read the color from the image). Do NOT extract or add any attribute the user did not mention, even if it is clearly visible in the image."
        else:
            image_instruction = "No image provided: extract attributes from the text query only."

        # 프롬프트 구성
        final_prompt = INFERENCE_PROMPT_TEMPLATE.format(
            user_query=user_query,
            image_instruction=image_instruction
        )

        # 추론 실행
        print(f"  🤖 Running inference...")
        print(f"  Query: '{user_query}'")

        try:
            if image:
                contents = [image, final_prompt]
            else:
                contents = [final_prompt]

            response = self.model.generate_content(contents)
            out_text = response.text.strip()
        except Exception as e:
            print(f"  ❌ Inference error: {e}")
            return {"error": str(e), "loaded_image_url": loaded_image_url}

        # 결과 출력
        print("\n" + "="*60)
        print("[Raw Output from Model]")
        print("="*60)
        print(out_text)
        print("="*60)

        # 파싱
        parsed = parse_json_from_text(out_text)

        if parsed and "reasoning" in parsed:
            print(f"\n[Inferred Attributes]")
            print(json.dumps({k: v for k, v in parsed.items() if v and k != "reasoning"}, indent=2, ensure_ascii=False))
            print(f"\n[Reasoning]\n{parsed['reasoning']}")
            parsed["loaded_image_url"] = loaded_image_url
            return parsed
        else:
            print("\n[Warning] Failed to parse JSON response.")
            return {"error": "JSON parse failed", "raw_output": out_text, "loaded_image_url": loaded_image_url}

    def infer_batch(self, queries: list[dict]) -> list[dict]:
        """
        배치로 여러 쿼리 추론

        Args:
            queries: 쿼리 리스트, 각 항목은 다음 구조:
                {
                    "id": "unique_id",
                    "query": "user query text",
                    "image_path": "path/to/image" (선택사항),
                    "image_url": "https://..." (선택사항)
                }

        Returns:
            추론 결과 리스트
        """
        results = []

        for i, item in enumerate(queries):
            print(f"\n[{i+1}/{len(queries)}] ID: {item.get('id', 'N/A')}")
            print("-" * 60)

            user_query = item.get("query", "").strip()
            if not user_query:
                print("  ⚠️ Empty query, skipping")
                continue

            image_path = item.get("image_path")
            image_url = item.get("image_url")

            # 추론 실행
            inferred = self.infer_single(user_query, image_path=image_path, image_url=image_url)

            # 결과 저장
            result = {
                "id": item.get("id"),
                "query": user_query,
                "image_path": image_path,
                "image_url": image_url,
                "inferred_attributes": inferred
            }
            results.append(result)

        return results



# ===================== MAIN =====================
TEST_QUERIES = [
    {"id": "q01", "query": "티셔츠이면서, 노란색이며 얇은 옷 추천해줘"},
    {"id": "q02", "query": "셔츠면서, 밝은색이며 신축성이 있는 옷 골라줘."},
    {"id": "q03", "query": "후드면서, 와이드 핏에 소매가 긴 옷 골라줘."},
    {"id": "q04", "query": "바지인데, 반바지이고 여름에 입을 옷 골라줘."},
    {"id": "q05", "query": "슬렉스인데, 딱 달라붙으면서, 색이며 신축성이 없는 바지 찾아줘."},
    {"id": "q06", "query": "치마인데, 어두운 색이며 얇은 옷 골라줘."},
    {"id": "q07", "query": "치마인데, 짧고 봄에 입을 옷 골라줘."},
    {"id": "q08", "query": "원피스인데 미디정도의 길이고, 가을에 입을 옷 골라줘."},
    {"id": "q09", "query": "원피스인데 두께가 있으면서 어두운 색 골라줘."},
    {"id": "q10", "query": "원피스인데 오버사이즈이며 얇은 원피스 골라줘."},
]


def main():
    output_path = os.path.join(os.path.dirname(__file__), "simple_test_results_gemini_except_color_fabric.json")

    print("\n" + "="*60)
    print("🚀 Initializing model...")
    print("="*60)
    analyzer = IntentAnalysisModule()

    print("\n" + "="*60)
    print("🧪 Running inference on simple test queries")
    print("="*60)

    batch_results = analyzer.infer_batch(TEST_QUERIES)

    # loaded_image_url 정리
    for result in batch_results:
        result["inferred_attributes"].pop("loaded_image_url", None)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(batch_results, f, indent=4, ensure_ascii=False)
    print(f"\n💾 Results saved to '{output_path}'")


if __name__ == "__main__":
    main()
