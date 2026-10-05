"""Gender-aware wording. Matrix text uses placeholders that are filled in for each team:

- pronouns: {they} {them} {their} {theirs} {themself}; a capitalised placeholder ({They}) capitalises the result
- verb agreement: {singular|plural}, e.g. "{they} {is|are}"; girls' and boys' teams use the singular form
"""
import re

GENDERS = ("girls", "boys", "mixed")
PRONOUNS = {
    "girls": {"they": "she", "them": "her", "their": "her", "theirs": "hers", "themself": "herself"},
    "boys": {"they": "he", "them": "him", "their": "his", "theirs": "his", "themself": "himself"},
    "mixed": {"they": "they", "them": "them", "their": "their", "theirs": "theirs", "themself": "themselves"},
}
PLACEHOLDER = re.compile(r"\{(?:(?P<pronoun>[Tt]hey|[Tt]hem|[Tt]heir|[Tt]heirs|[Tt]hemself)|(?P<singular>[^{}|]+)\|(?P<plural>[^{}|]+))\}")
GENDERED_WORD = re.compile(r"\b(she|her|hers|herself|he|him|his|himself)\b", re.IGNORECASE)


def render(text: str, gender: str) -> str:
    def replace(match):
        if match["pronoun"]:
            word = PRONOUNS[gender][match["pronoun"].lower()]
            return word[0].upper() + word[1:] if match["pronoun"][0].isupper() else word
        return match["plural"] if gender == "mixed" else match["singular"]
    return PLACEHOLDER.sub(replace, text)


def render_document(value, gender: str):
    """A copy of a matrix document (or any nested value) with every string rendered."""
    if isinstance(value, str):
        return render(value, gender)
    if isinstance(value, list):
        return [render_document(item, gender) for item in value]
    if isinstance(value, dict):
        return {key: render_document(item, gender) for key, item in value.items()}
    return value


def gendered_words(text: str) -> list[str]:
    """Gendered words written directly instead of placeholders (for warnings in the matrix editor)."""
    return [m.group(0) for m in GENDERED_WORD.finditer(text)]
