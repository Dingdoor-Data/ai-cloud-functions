import json


def _safe_json_loads(value):
    if not value or not isinstance(value, str):
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None
    
def _build_tools_summary(transcript):
    tool_calls = []
    tool_results = []
    for turn in transcript or []:
        tool_calls.extend(turn.get("tool_calls", []) or [])
        tool_results.extend(turn.get("tool_results", []) or [])

    calls_by_request_id = {}
    for call in tool_calls:
        request_id = call.get("request_id")
        if not request_id:
            continue
        raw_payload = None
        tool_details = call.get("tool_details") or {}
        if isinstance(tool_details, dict):
            raw_payload = tool_details.get("body")
        if raw_payload is None:
            raw_payload = call.get("params_as_json")
        calls_by_request_id[request_id] = raw_payload

    tools = []
    for idx, result in enumerate(tool_results[:3]):
        tool_name = result.get("tool_name")
        parsed_value = _safe_json_loads(result.get("result_value"))
        is_error = result.get("is_error") is True
        request_id = result.get("request_id")
        raw_payload = calls_by_request_id.get(request_id)
        payload = _safe_json_loads(raw_payload) if raw_payload else None

        summary = None
        if idx == 0:
            summary = {
                "zipCode": None,
                "status": None,
            }
            if not is_error and isinstance(parsed_value, dict):
                summary["zipCode"] = parsed_value.get("zipCode")
                summary["status"] = parsed_value.get("status") or (
                    "success" if parsed_value.get("success") else None
                )
        elif idx == 1:
            summary = {
                "status": None,
                "data": {
                    "inferredCategory": None,
                    "summary": None,
                },
            }
            if not is_error and isinstance(parsed_value, dict):
                summary["status"] = parsed_value.get("status")
                data = parsed_value.get("data") or {}
                summary["data"]["inferredCategory"] = data.get("inferredCategory")
                summary["data"]["summary"] = data.get("summary")
        elif idx == 2:
            summary = {
                "status": None,
                "message": None,
                "data": {
                    "knockId": None,
                },
            }
            if not is_error and isinstance(parsed_value, dict):
                summary["status"] = parsed_value.get("status")
                summary["message"] = parsed_value.get("message")
                data = parsed_value.get("data") or {}
                summary["data"]["knockId"] = data.get("knockId")

        tools.append(
            {
                "toolName": tool_name,
                "result": summary,
                "isError": is_error,
                "payload": payload,
            }
        )

    return tools
