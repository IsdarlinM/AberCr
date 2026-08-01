from datetime import date
import re


def validate_email(email: str) -> str:
    normalized = email.strip()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
        raise ValueError("El correo electrónico no tiene un formato válido.")
    return normalized


def validate_password(password: str) -> None:
    if not password:
        raise ValueError("La contraseña no puede estar vacía.")


def validate_name(field_name: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} no puede estar vacío.")
    if len(normalized) > 100:
        raise ValueError(f"{field_name} no puede superar 100 caracteres.")
    return normalized


def validate_birth_date(
    year: int | None,
    month: int | None,
    day: int | None,
) -> None:
    supplied = (year, month, day)
    if all(value is None for value in supplied):
        return
    if any(value is None for value in supplied):
        raise ValueError(
            "birth_year, birth_month y birth_day deben enviarse juntos."
        )
    try:
        date(int(year), int(month), int(day))
    except (TypeError, ValueError) as exc:
        raise ValueError("La fecha de nacimiento no es válida.") from exc
