from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import re
import requests

app = FastAPI(title="内容相关性&专业性打分服务")
OLLAMA_CHAT = "http://127.0.0.1:11434/v1/chat/completions"

class ProfRelevanceRequest(BaseModel):
    target_subject: str = Field(default="是否对虚拟币市场有贡献，是否有实用性", description="评估的目标主题")
    text: str = Field(description="待评估的文本内容")
    relevance_desc: str = Field(default="0‑10分。完全不相关0分；部分沾边中间分；紧密围绕目标主题、全部内容服务于主题得10分", description="相关性打分评判规则")
    professional_desc: str = Field(default="0‑10分。错误、口水灌水、营销软文0‑3；普通科普泛泛而谈4‑6；逻辑严谨、术语准确、事实可靠、有专业深度7‑10", description="专业性打分评判规则")
    max_relevance: int = Field(default=10, description="相关性满分")
    max_professional: int = Field(default=10, description="专业性满分")

def clean_text(text: str, max_len=2000):
    text = re.sub(r'\s+', '\n', text.strip())
    return text[:max_len]

def parse_score_output(raw: str):
    """解析模型输出key=value，不再要求输出total"""
    lines = raw.splitlines()
    res = {}
    for line in lines:
        line = line.strip()
        if "=" not in line:
            continue
        k, v = line.split("=", maxsplit=1)
        k = k.strip()
        v = v.strip()
        if k in ("relevance", "professional"):
            res[k] = int(v)
        elif k == "reason":
            res[k] = v
    must_keys = {"relevance", "professional", "reason"}
    if not must_keys.issubset(res.keys()):
        raise ValueError(f"解析缺少字段：{res}")
    return res

@app.post("/api/prof_relevance_score")
def prof_relevance_score(req: ProfRelevanceRequest):
    clean_content = clean_text(req.text, max_len=2000)

    prompt = f"""
任务：对文本做【相关性】和【专业性】两项打分。
目标主题：{req.target_subject}

相关性规则（满分{req.max_relevance}）：
{req.relevance_desc}

专业性规则（满分{req.max_professional}）：
{req.professional_desc}

输出严格遵守下面格式，**禁止JSON、禁止markdown、禁止```、禁止列表符号，不要输出total字段！**
共3行 key=value：
relevance=数字
professional=数字
reason=简短1‑3句理由，不要换行

待评估文本：
{clean_content}
"""

    payload = {
        "model": "qwen2.5:7b-instruct",
        "num_ctx": 4096,
        "messages": [{"role": "user", "content": prompt.strip()}],
        "max_tokens": 512,
        "temperature": 0.0
    }
    try:
        resp = requests.post(OLLAMA_CHAT, json=payload, timeout=120)
        resp.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"模型调用失败:{str(e)}")

    raw_output = resp.json()["choices"][0]["message"]["content"].strip()
    try:
        parsed = parse_score_output(raw_output)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败，原始输出：{raw_output}, err:{str(e)}")

    # 后端手动计算总分，避免大模型算错数学
    total = parsed["relevance"] + parsed["professional"]
    return {
        "relevance": parsed["relevance"],
        "professional": parsed["professional"],
        "total": total,
        "reason": parsed["reason"]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8884)
