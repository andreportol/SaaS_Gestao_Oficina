import re

from django import template

register = template.Library()


@register.filter
def whatsapp_number(value):
    digits = re.sub(r"\D", "", value or "")
    if not digits:
        return ""
    if len(digits) in (10, 11) and not digits.startswith("55"):
        digits = f"55{digits}"
    return digits
