import os
import json
import base64

SIMPLE_RESULTS = os.path.join(os.path.dirname(__file__), "simple_test_results_gemini.json")
IMAGE_RESULTS  = os.path.join(os.path.dirname(__file__), "image_test_results_gemini.json")
OUTPUT_HTML    = os.path.join(os.path.dirname(__file__), "results_visualization.html")

ATTR_COLORS = {
    "category1":    "#4A90D9",
    "sleeve":       "#7B68EE",
    "length":       "#9B59B6",
    "sex":          "#E67E22",
    "season":       "#27AE60",
    "stretch":      "#16A085",
    "thickness":    "#2980B9",
    "fit":          "#8E44AD",
    "color":        "#C0392B",
    "fabric":       "#D35400",
    "visual_detail":"#1ABC9C",
}


def img_to_base64(path):
    try:
        with open(path, "rb") as f:
            ext = os.path.splitext(path)[1].lower().lstrip(".")
            if ext == "jpg":
                ext = "jpeg"
            return f"data:image/{ext};base64,{base64.b64encode(f.read()).decode()}"
    except Exception:
        return None


def render_attrs(attrs):
    SKIP = {"reasoning", "error", "raw_output", "loaded_image_url"}
    tags = ""
    for k, v in attrs.items():
        if k in SKIP or not v:
            continue
        color = ATTR_COLORS.get(k, "#555")
        tags += f'<span class="tag" style="background:{color}">{k}: {v}</span>'
    return tags


def render_card(item, show_image=False):
    attrs = item.get("inferred_attributes", {})
    qid   = item.get("id", "")
    query = item.get("query", "")
    reasoning = attrs.get("reasoning", "")
    error     = attrs.get("error", "")

    img_html = ""
    if show_image:
        img_path = item.get("image_path")
        if img_path:
            b64 = img_to_base64(img_path)
            if b64:
                img_html = f'<img src="{b64}" class="ref-img" alt="ref">'
            else:
                img_html = '<div class="no-img">이미지 로드 실패</div>'

    tags_html = render_attrs(attrs)
    if error:
        tags_html += f'<span class="tag error">⚠ {error}</span>'

    return f"""
    <div class="card">
      <div class="card-header">
        <span class="qid">{qid}</span>
        <span class="query">"{query}"</span>
      </div>
      <div class="card-body">
        {img_html}
        <div class="card-content">
          <div class="tags">{tags_html if tags_html else '<span class="no-attr">속성 없음</span>'}</div>
          {'<div class="reasoning">' + reasoning + '</div>' if reasoning else ''}
        </div>
      </div>
    </div>"""


def build_html(simple_results, image_results):
    simple_cards = "\n".join(render_card(r, show_image=False) for r in simple_results)
    image_cards  = "\n".join(render_card(r, show_image=True)  for r in image_results)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Intent Analysis Results — Gemini 3.5 Flash</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', sans-serif; background: #f0f2f5; color: #222; padding: 24px; }}
  h1 {{ font-size: 1.6rem; margin-bottom: 8px; color: #1a1a2e; }}
  h2 {{ font-size: 1.2rem; margin: 32px 0 12px; color: #333; border-left: 4px solid #4A90D9; padding-left: 10px; }}
  .subtitle {{ color: #666; font-size: 0.9rem; margin-bottom: 24px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); gap: 16px; }}
  .card {{ background: #fff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); overflow: hidden; }}
  .card-header {{ background: #1a1a2e; color: #fff; padding: 10px 14px; display: flex; align-items: baseline; gap: 10px; }}
  .qid {{ font-size: 0.75rem; background: #4A90D9; padding: 2px 8px; border-radius: 10px; white-space: nowrap; }}
  .query {{ font-size: 0.92rem; line-height: 1.4; }}
  .card-body {{ display: flex; gap: 12px; padding: 14px; align-items: flex-start; }}
  .ref-img {{ width: 120px; height: 150px; object-fit: cover; border-radius: 8px; flex-shrink: 0; border: 1px solid #eee; }}
  .no-img {{ width: 120px; height: 150px; background: #eee; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; color: #999; }}
  .card-content {{ flex: 1; }}
  .tags {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }}
  .tag {{ padding: 3px 10px; border-radius: 12px; font-size: 0.8rem; color: #fff; font-weight: 500; }}
  .tag.error {{ background: #e74c3c; }}
  .no-attr {{ color: #aaa; font-size: 0.85rem; }}
  .reasoning {{ font-size: 0.78rem; color: #555; line-height: 1.6; border-top: 1px solid #f0f0f0; padding-top: 8px; }}
</style>
</head>
<body>
<h1>Intent Analysis Results</h1>
<p class="subtitle">Model: gemini-3.5-flash &nbsp;|&nbsp; Simple test: {len(simple_results)}건 &nbsp;|&nbsp; Image test: {len(image_results)}건</p>

<h2>Simple Test (텍스트 전용)</h2>
<div class="grid">{simple_cards}</div>

<h2>Image Test (이미지 + 텍스트)</h2>
<div class="grid">{image_cards}</div>

</body>
</html>"""


def main():
    with open(SIMPLE_RESULTS, encoding="utf-8") as f:
        simple_results = json.load(f)
    with open(IMAGE_RESULTS, encoding="utf-8") as f:
        image_results = json.load(f)

    html = build_html(simple_results, image_results)

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Saved: {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
