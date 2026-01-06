import logging
import os
from dotenv import load_dotenv
from flask import Request, jsonify, make_response
from functions_framework import http
from google.cloud.logging_v2.handlers import StructuredLogHandler

from dingdoor_utils_package import fetch_one
from utils.phone import normalize_phone

load_dotenv()
env = os.getenv("ENV", "DEV")


# ------------- logging (structured -> Cloud Logging) -----------------
logger = logging.getLogger("user_info_lookup")
if not logger.handlers:  
    handler = StructuredLogHandler() 
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

_SQL = """
WITH ranked AS (
  SELECT pl.postalCode, p.phoneNumber, p.email, k.createdAt, p.name, p.lastName,
         ROW_NUMBER() OVER (PARTITION BY p.id ORDER BY k.createdAt DESC) AS rn
  FROM `dingdoor_data_warehouse.profiles` AS p
  LEFT JOIN `dingdoor_data_warehouse.knocks`  AS k ON p.id = k.userId
  LEFT JOIN `dingdoor_data_warehouse.places`  AS pl ON pl.id = k.placeId
  WHERE p.phoneNumber = @phone AND pl.postalCode IS NOT NULL
)
SELECT postalCode, name, lastName FROM ranked WHERE rn = 1 ORDER BY createdAt DESC LIMIT 1;
"""

@http
def http_lookup(request: Request):
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        phone = body.get("phoneNumber")
    elif request.method == "GET":
        phone = request.args.get("phoneNumber")
    else:
        return make_response({"error": "method not allowed"}, 405)

    if not phone:
        return jsonify({"error": "missing 'phone'"}), 400

    logger.info({"event": "lookup_start", "method": request.method, "phone_number":phone})

    try:
        norm = normalize_phone(phone)
        # dev enviroment using mock data
        if env == "DEV":
            row = {
                "postalCode": "33126",
                "name": "John",
                "lastName": "Doe"
            }
        else:
            row = fetch_one(_SQL, {"phone": norm}, timeout=20.0)

        if not row:
            logger.info({"event": "lookup_done", "status": "not_found",  "phone_number": norm})
            return {"zipCode": None, "firstName":None, "lastName":None, "success": True,"statusCode":200, "message":"User info lookup successful, but no data found."}

        zipcode, firstName, lastName = row["postalCode"], row["name"], row["lastName"]
        logger.info({"event": "lookup_done", "status": "ok", "zipcode": zipcode})
        return {"zipCode": zipcode, "firstName":firstName, "lastName":lastName, "success": True,"statusCode":200,"message":"User info lookup successful."}

    except Exception as e:
        logger.error({"event": "lookup_error", "phone_number": norm, "error": str(e)})
        return make_response({"error": "lookup failed"}, 500)
