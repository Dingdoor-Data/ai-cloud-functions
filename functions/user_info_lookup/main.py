import time
import logging
import re
from flask import Request, jsonify, make_response
from functions_framework import http
from google.cloud.logging_v2.handlers import StructuredLogHandler

from utils.bq_utils import fetch_one
from utils.phone import normalize_phone
from models.user_info_models import UserInfoResponse

# ------------- logging (structured -> Cloud Logging) -----------------
logger = logging.getLogger("user_info_lookup")
if not logger.handlers:  # avoid duplicate handlers on warm instances
    handler = StructuredLogHandler()  # writes JSON to stdout
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

def _mask(phone: str) -> str:
    d = re.sub(r"\D", "", phone or "")
    tail = d[-4:] if len(d) >= 4 else d
    return f"...{tail}"

# ------------- query -------------------------------------------------
_SQL = """
WITH ranked AS (
  SELECT pl.postalCode, p.phoneNumber, p.email, k.createdAt,
         ROW_NUMBER() OVER (PARTITION BY p.id ORDER BY k.createdAt DESC) AS rn
  FROM `dingdoor_data_warehouse.profiles` AS p
  LEFT JOIN `dingdoor_data_warehouse.knocks`  AS k ON p.id = k.userId
  LEFT JOIN `dingdoor_data_warehouse.places`  AS pl ON pl.id = k.placeId
  WHERE p.phoneNumber = @phone AND pl.postalCode IS NOT NULL
)
SELECT postalCode FROM ranked WHERE rn = 1 ORDER BY createdAt DESC LIMIT 1;
"""

@http
def http_lookup(request: Request):
    # --- allow GET & POST; flip the branches if you want POST-only
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        phone = body.get("phoneNumber")
    elif request.method == "GET":
        phone = request.args.get("phoneNumber")
    else:
        return make_response({"error": "method not allowed"}, 405)

    if not phone:
        return jsonify({"error": "missing 'phone'"}), 400

    masked = _mask(phone)
    t0 = time.monotonic()
    logger.info({"event": "lookup_start", "method": request.method, "phone_masked": masked})

    try:
        norm = normalize_phone(phone)
        row = fetch_one(_SQL, {"phone": norm}, timeout=20.0)
        elapsed_ms = round((time.monotonic() - t0) * 1000, 1)

        if not row:
            logger.info({"event": "lookup_done", "status": "not_found", "elapsed_ms": elapsed_ms, "phone_masked": masked})
            return {"zipCode": None, "success": True,"statusCode":200}

        zipcode = row["postalCode"]
        logger.info({"event": "lookup_done", "status": "ok", "elapsed_ms": elapsed_ms, "phone_masked": masked, "zipcode": zipcode})
        return {"zipCode": zipcode, "success": True,"statusCode":200}

    except Exception as e:
        elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
        logger.error({"event": "lookup_error", "elapsed_ms": elapsed_ms, "phone_masked": masked, "error": str(e)})
        return make_response({"error": "lookup failed"}, 500)
