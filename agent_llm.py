"""Small bounded Responses API client; no SDK, saved responses, or credential logs."""
from __future__ import annotations
import json
from urllib import error, request

DEFAULT_MODEL = 'gpt-6-luna'


class ModelError(ValueError):
    def __init__(self, message, *, safe=False):
        super().__init__(message)
        self.public_message = message if safe else '模型服務暫時無法完成；請稍後重試。'



class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ModelError('模型服務轉址已拒絕，未轉送金鑰。', safe=True)


def respond(api_key: str, instructions: str, inputs: list, tools: list) -> dict:
    if not isinstance(api_key, str) or len(api_key.strip()) < 8:
        raise ModelError('自主 Agent 需要你的 OpenAI API Key。', safe=True)
    body = {'model': DEFAULT_MODEL, 'instructions': instructions, 'input': inputs,
            'tools': tools, 'parallel_tool_calls': False, 'store': False,
            'max_output_tokens': 1600, 'reasoning': {'effort': 'none'}}
    encoded = json.dumps(body, ensure_ascii=False).encode('utf-8')
    if len(encoded) > 180_000:
        raise ModelError('本輪內容已達上限；請縮小問題或另開任務。', safe=True)
    req = request.Request('https://api.openai.com/v1/responses', data=encoded, method='POST',
                          headers={'Authorization': 'Bearer ' + api_key.strip(),
                                   'Content-Type': 'application/json'})
    try:
        with request.build_opener(NoRedirect()).open(req, timeout=35) as response:
            raw = response.read(500_001)
        if len(raw) > 500_000:
            raise ModelError('模型回應超過大小限制。', safe=True)
        result = json.loads(raw)
        if not isinstance(result, dict) or not isinstance(result.get('output'), list):
            raise ValueError
        if result.get('status') in ('incomplete', 'failed', 'cancelled'):
            raise ModelError('模型未完成本次規劃；已取得的資料仍保留，可縮小問題後接續。', safe=True)
        return result
    except error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ModelError('OpenAI 金鑰或模型權限無效，請檢查連線設定。', safe=True) from None
        if exc.code == 429:
            raise ModelError('OpenAI 額度或速率達到限制；請稍後重試。', safe=True) from None
        raise ModelError(f'OpenAI 服務暫時無法完成（HTTP {exc.code}）。', safe=True) from None
    except (OSError, ValueError, TimeoutError) as exc:
        if isinstance(exc, ModelError):
            raise
        raise ModelError('模型服務無法連線或回應格式異常，已保留取得的資料。', safe=True) from None
