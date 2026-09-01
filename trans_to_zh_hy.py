#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动检测翻译服务：HTTP API，可用 curl 直接调用
基于 Ollama + TranslateGemma

启动（默认端口 8000，默认监听本机）:
    python3 translate_server.py [port]
    OLLAMA_TRANS_MODEL=translategemma:4b python3 translate_server.py 8000   # 换模型档位
    HOST=0.0.0.0 python3 translate_server.py 8000                           # 允许局域网其他设备访问

调用示例:
    # 健康检查
    curl http://localhost:8000/health

    # 翻译（POST，推荐，自动检测语言 -> 中文）
    curl -X POST http://localhost:8000/translate \
      -H "Content-Type: application/json" \
      -d '{"text": "Hello world"}'

    # 指定源语言（跳过自动检测）与目标语言
    curl -X POST http://localhost:8000/translate \
      -H "Content-Type: application/json" \
      -d '{"text": "Bonjour le monde", "source": "fr", "target": "zh-Hans"}'

    # 翻译成英文
    curl -X POST http://localhost:8000/translate \
      -H "Content-Type: application/json" \
      -d '{"text": "今天天气真好", "target": "en"}'

    # GET 快速测试（text 需 URL 编码）
    curl "http://localhost:8000/translate?text=Hello%20world"
"""
import sys
import os
import re
import json
import urllib.request
import urllib.parse
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = os.environ.get("OLLAMA_TRANS_MODEL", "hy-mt")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
HOST = os.environ.get("HOST", "127.0.0.1")
DEFAULT_TARGET = "zh-Hans"   # 默认目标语言：简体中文
# 后端选择：auto=根据模型名自动判断；translategemma=用 TranslateGemma 模板；hymt=用 Hy-MT 模板
BACKEND = os.environ.get("BACKEND", "auto")


def resolve_backend():
    if BACKEND == "auto":
        return "hymt" if "hy" in MODEL.lower() else "translategemma"
    return BACKEND

# langdetect 的 ISO 639-1 代码 -> (语言英文名, TranslateGemma 语言代码)
LANG_MAP = {
    "en": ("English", "en"),
    "zh": ("Chinese", "zh-Hans"),
    "zh-cn": ("Chinese", "zh-Hans"),
    "zh-tw": ("Chinese", "zh-Hant"),
    "ja": ("Japanese", "ja"),
    "ko": ("Korean", "ko"),
    "fr": ("French", "fr"),
    "de": ("German", "de"),
    "es": ("Spanish", "es"),
    "ru": ("Russian", "ru"),
    "it": ("Italian", "it"),
    "pt": ("Portuguese", "pt"),
    "nl": ("Dutch", "nl"),
    "pl": ("Polish", "pl"),
    "ar": ("Arabic", "ar"),
    "tr": ("Turkish", "tr"),
    "vi": ("Vietnamese", "vi"),
    "th": ("Thai", "th"),
    "id": ("Indonesian", "id"),
    "uk": ("Ukrainian", "uk"),
    "sv": ("Swedish", "sv"),
    "da": ("Danish", "da"),
    "fi": ("Finnish", "fi"),
    "hu": ("Hungarian", "hu"),
    "cs": ("Czech", "cs"),
    "ro": ("Romanian", "ro"),
    "el": ("Greek", "el"),
    "he": ("Hebrew", "he"),
    "hi": ("Hindi", "hi"),
    "ms": ("Malay", "ms"),
    "tl": ("Tagalog", "tl"),
    "fa": ("Persian", "fa"),
    "bn": ("Bengali", "bn"),
}

# TranslateGemma 目标语言代码 -> 显示名
TGT_LANGS = {
    "zh-Hans": "Chinese",
    "zh-Hant": "Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "ru": "Russian",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "ar": "Arabic",
    "tr": "Turkish",
    "vi": "Vietnamese",
    "th": "Thai",
    "id": "Indonesian",
    "uk": "Ukrainian",
    "sv": "Swedish",
    "da": "Danish",
    "fi": "Finnish",
    "hu": "Hungarian",
    "cs": "Czech",
    "ro": "Romanian",
    "el": "Greek",
    "he": "Hebrew",
    "hi": "Hindi",
    "ms": "Malay",
    "tl": "Tagalog",
    "fa": "Persian",
    "bn": "Bengali",
}


class BadRequest(Exception):
    pass


class OllamaDown(Exception):
    pass


def builtin_detect(text):
    """无需 langdetect 的轻量启发式检测（覆盖常见语种）"""
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    hira = sum(1 for c in text if "\u3040" <= c <= "\u309f")
    kata = sum(1 for c in text if "\u30a0" <= c <= "\u30ff")
    hang = sum(1 for c in text if "\uac00" <= c <= "\ud7af")
    cyr = sum(1 for c in text if "\u0400" <= c <= "\u04ff")
    n = max(len(text), 1)
    if (hira + kata) / n > 0.05:
        return "ja"
    if hang / n > 0.05:
        return "ko"
    if cyr / n > 0.05:
        return "ru"
    if cjk / n > 0.10:
        return "zh-cn"
    return "en"


def detect_lang(text):
    try:
        from langdetect import detect
        return detect(text)
    except (ImportError, Exception):
        return builtin_detect(text)


def build_prompt(text, src, tgt):
    """按 TranslateGemma 官方模板构造 prompt（文本前保留两个空行）"""
    src_name, src_code = src
    tgt_name, tgt_code = tgt
    return (
        f"You are a professional {src_name} ({src_code}) to {tgt_name} ({tgt_code}) translator. "
        f"Your goal is to accurately convey the meaning and nuances of the original {src_name} text "
        f"while adhering to {tgt_name} grammar, vocabulary, and cultural sensitivities.\n"
        f"Produce only the {tgt_name} translation, without any additional explanations or commentary. "
        f"Please translate the following {src_name} text into {tgt_name}:\n\n\n{text}"
    )


# Hy-MT 目标语言代码 -> 中文名（中文模板用）
TGT_ZH = {
    "zh-Hans": "中文", "zh-Hant": "繁体中文", "en": "英语", "ja": "日语",
    "ko": "韩语", "fr": "法语", "de": "德语", "es": "西班牙语", "ru": "俄语",
    "it": "意大利语", "pt": "葡萄牙语", "nl": "荷兰语", "pl": "波兰语",
    "ar": "阿拉伯语", "tr": "土耳其语", "vi": "越南语", "th": "泰语",
    "id": "印尼语", "uk": "乌克兰语", "sv": "瑞典语", "da": "丹麦语",
    "fi": "芬兰语", "hu": "匈牙利语", "cs": "捷克语", "ro": "罗马尼亚语",
    "el": "希腊语", "he": "希伯来语", "hi": "印地语", "ms": "马来语",
    "tl": "他加禄语", "fa": "波斯语", "bn": "孟加拉语",
}


def build_prompt_hymt(text, src, tgt):
    """按腾讯 Hy-MT 官方模板构造 prompt"""
    src_name, src_code = src
    tgt_name, tgt_code = tgt
    if src_code.startswith("zh"):
        # 中文 -> 其他语言：用中文模板
        zh_name = TGT_ZH.get(tgt_code, tgt_name)
        return (
            f"将以下文本翻译为{zh_name}，注意只需要输出翻译后的结果，不要额外解释：\n{text}"
        )
    # 其他语言 -> 目标语言（非中）：用英文模板
    return (
        f"Translate the following segment into {tgt_name}, without additional explanation.\n\n{text}"
    )


def make_prompt(text, src, tgt):
    """按当前后端选择正确的 prompt 构造器"""
    if resolve_backend() == "hymt":
        return build_prompt_hymt(text, src, tgt)
    return build_prompt(text, src, tgt)


def call_ollama(prompt):
    body = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "30m",   # 让模型保持常驻，避免每次冷启动
        "options": {
            "num_ctx": 2048,     # 缩小上下文窗口 -> 减少 prefill 时间和 KV cache 内存
            "num_batch": 1024,   # 增大预填充批大小 -> 长 prompt 处理更快（默认 512）
        },
    }).encode("utf-8")
    try:
        req = urllib.request.Request(
            OLLAMA_URL, data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise OllamaDown(
            f"无法连接 Ollama 服务 ({OLLAMA_URL})：{e.reason}。"
            f"请先运行 `brew services start ollama` 或 `ollama serve`"
        )
    except Exception as e:
        raise OllamaDown(f"Ollama 调用失败：{e}")
    return data.get("response", "").strip()


def ollama_alive():
    try:
        base = OLLAMA_URL.rsplit("/api/", 1)[0] + "/api/tags"
        with urllib.request.urlopen(base, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def split_text(text, max_len=600):
    """把长文本按句拆分，每块不超过 max_len 字符（单句超长则硬切）"""
    parts = re.split(r"(?<=[。！？!?；;\n])", text)
    chunks, cur = [], ""
    for p in parts:
        if not p:
            continue
        if len(cur) + len(p) <= max_len:
            cur += p
        else:
            if cur:
                chunks.append(cur)
            while len(p) > max_len:
                chunks.append(p[:max_len])
                p = p[max_len:]
            cur = p
    if cur:
        chunks.append(cur)
    return [c for c in chunks if c.strip()]


def handle_translate(text, source, target):
    if not text or not text.strip():
        raise BadRequest('缺少 text 字段，示例: {"text": "Hello world"}')
    text = text.strip()

    # 解析源语言
    if source and source != "auto":
        src = LANG_MAP.get(source)
        if src is None:
            raise BadRequest(
                f"未知源语言代码: {source}。可用: {', '.join(sorted(LANG_MAP))}，或传 auto 自动检测"
            )
        detected = source
    else:
        detected = detect_lang(text)
        if detected in ("zh", "zh-cn", "zh-tw"):
            return {
                "ok": True,
                "skipped": True,
                "note": "源语言已是中文，无需翻译",
                "text": text,
                "detected": detected,
                "translation": text,
            }
        src = LANG_MAP.get(detected, ("English", "en"))

    # 解析目标语言
    if target not in TGT_LANGS:
        raise BadRequest(
            f"未知目标语言代码: {target}。可用: {', '.join(sorted(TGT_LANGS))}"
        )
    tgt = (TGT_LANGS[target], target)

    # 长文自动分块：避免单次超出上下文、提升长文翻译速度与质量
    if len(text) > 800:
        chunks = split_text(text)
        translation = "\n".join(
            call_ollama(make_prompt(c, src, tgt)) for c in chunks
        )
        chunk_count = len(chunks)
    else:
        chunks = [text]
        translation = call_ollama(make_prompt(text, src, tgt))
        chunk_count = 1

    return {
        "ok": True,
        "text": text,
        "detected": detected,
        "source": {"name": src[0], "code": src[1]},
        "target": {"name": tgt[0], "code": tgt[1]},
        "chunks": chunk_count,
        "translation": translation,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _translate(self, text, source, target):
        try:
            self._send_json(200, handle_translate(text, source, target))
        except BadRequest as e:
            self._send_json(400, {"ok": False, "error": str(e)})
        except OllamaDown as e:
            self._send_json(503, {"ok": False, "error": str(e)})
        except Exception as e:
            self._send_json(500, {"ok": False, "error": f"服务内部错误: {e}"})

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(200, {
                "ok": True,
                "ollama": ollama_alive(),
                "model": MODEL,
                "backend": resolve_backend(),
            })
            return
        if parsed.path == "/translate":
            q = urllib.parse.parse_qs(parsed.query)
            self._translate(
                q.get("text", [""])[0],
                q.get("source", ["auto"])[0],
                q.get("target", [DEFAULT_TARGET])[0],
            )
            return
        self._send_json(404, {
            "ok": False,
            "error": "not found",
            "usage": "POST /translate  或  GET /translate?text=...",
        })

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/translate":
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            self._send_json(400, {
                "ok": False,
                "error": '请求体不是合法 JSON，示例: {"text": "Hello world"}',
            })
            return
        self._translate(
            data.get("text", ""),
            data.get("source", "auto"),
            data.get("target", DEFAULT_TARGET),
        )


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", "8882"))
    server = ThreadingHTTPServer((HOST, port), Handler)
    print(f"翻译服务已启动: http://{HOST}:{port}  (模型: {MODEL})")
    print(f"健康检查:  curl http://localhost:{port}/health")
    print(f"翻译示例:  curl -X POST http://localhost:{port}/translate "
          f"-H 'Content-Type: application/json' -d '{{\"text\": \"Hello world\"}}'")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
