"""Phone number normalization to E.164 + type classification via libphonenumber."""
from __future__ import annotations

from dataclasses import dataclass

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberType


@dataclass
class NormalizedPhone:
    e164: str | None
    type: str | None


_TYPE_NAMES = {
    PhoneNumberType.MOBILE: "mobile",
    PhoneNumberType.FIXED_LINE: "landline",
    PhoneNumberType.FIXED_LINE_OR_MOBILE: "mobile_or_landline",
    PhoneNumberType.VOIP: "voip",
    PhoneNumberType.TOLL_FREE: "toll_free",
    PhoneNumberType.PREMIUM_RATE: "premium",
    PhoneNumberType.SHARED_COST: "shared_cost",
    PhoneNumberType.PERSONAL_NUMBER: "personal",
    PhoneNumberType.PAGER: "pager",
    PhoneNumberType.UAN: "uan",
    PhoneNumberType.VOICEMAIL: "voicemail",
    PhoneNumberType.UNKNOWN: None,
}


def normalize_phone(raw: str | None, default_region: str = "US") -> NormalizedPhone:
    if not raw:
        return NormalizedPhone(e164=None, type=None)
    try:
        parsed = phonenumbers.parse(raw, default_region)
    except NumberParseException:
        return NormalizedPhone(e164=None, type=None)
    if not phonenumbers.is_valid_number(parsed):
        return NormalizedPhone(e164=None, type=None)
    e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    type_name = _TYPE_NAMES.get(phonenumbers.number_type(parsed))
    return NormalizedPhone(e164=e164, type=type_name)
