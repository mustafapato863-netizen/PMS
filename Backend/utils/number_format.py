def format_report_number(value: float | int | str | None, unit: str | None = None) -> str:
    if value is None:
        return "N/A"

    try:
        if isinstance(value, str):
            numeric_value = float(value.replace(",", ""))
        else:
            numeric_value = float(value)
    except (ValueError, TypeError):
        return str(value)

    abs_value = abs(numeric_value)
    formatted = ""

    if abs_value >= 1_000_000_000:
        formatted = f"{numeric_value / 1_000_000_000:.2f}B"
    elif abs_value >= 1_000_000:
        formatted = f"{numeric_value / 1_000_000:.2f}M"
    elif abs_value >= 1_000:
        formatted = f"{numeric_value / 1_000:.2f}K"
    else:
        if numeric_value % 1 != 0:
            formatted = f"{numeric_value:.2f}"
        else:
            formatted = str(int(numeric_value))

    # Remove unnecessary trailing zeros
    if "." in formatted and any(c in formatted for c in "KMB"):
        # e.g., 1.20K -> 1.2K, 1.00M -> 1M
        import re
        formatted = re.sub(r'\.00([KMB])', r'\1', formatted)
        formatted = re.sub(r'(\.\d)0([KMB])', r'\1\2', formatted)
    elif "." in formatted:
        if formatted.endswith(".00"):
            formatted = formatted[:-3]
        elif formatted[-1] == "0":
            formatted = formatted[:-1]

    if unit:
        unit = unit.strip()
        if unit.lower() == "%":
            return f"{formatted}%"
        if len(unit) in (2, 3) and unit.isalpha():
            return f"{unit} {formatted}"
        return f"{formatted} {unit}"

    return formatted
