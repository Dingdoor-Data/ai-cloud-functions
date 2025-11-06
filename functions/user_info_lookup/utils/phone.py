import re

def normalize_phone(phone: str) -> str:
    phone = phone.strip()
    if phone.startswith('+'):
        return '+' + re.sub(r"[^\d]", "", phone[1:])
    return re.sub(r"[^\d]", "", phone)
