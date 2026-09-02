from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import re
import requests

app = FastAPI(title="网页摘要服务")
OLLAMA_URL = "http://127.0.0.1:11434/v1/chat/completions"

class SummaryRequest(BaseModel):
    text: str

def clean_text(text: str, max_len=1800):
    """清洗网页文本，去除多余换行空格，做长度截断"""
    text = re.sub(r'\s+', '\n', text.strip())
    return text[:max_len]

@app.post("/api/summary")
def summary(req: SummaryRequest):
    clean_content = clean_text(req.text)
    payload = {
        "model": "qwen2.5:3b-instruct",
        "num_ctx": 4096,
        "messages": [
            {
                "role": "user",
                "content": "严格依据原文内容，不要删减关键信息、不要过度压缩。提取原文核心要点，以条目列表输出；保留主体、条件、关键结论；禁止编造内容；不要大段改写。只输出结果：\n" + clean_content
            }
        ],
        "max_tokens": 1024,
        "temperature": 0.2
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
        resp.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ollama调用失败:{str(e)}")

    data = resp.json()
    choice = data["choices"][0]
    result = choice["message"]["content"].strip()
    if choice["finish_reason"] == "length":
        result += "\n【警告：摘要输出被截断，输入文本过长】"
    return {"summary": result}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8883)
