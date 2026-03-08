"""
message_templates.py -- Multilingual alert templates and Polly voice mappings.

Supported languages: English (en), Tamil (ta), Hindi (hi).
"""

# -- Polly Voice Mappings ------------------------------------------------
POLLY_VOICE_MAP = {
    "en": {"VoiceId": "Joanna", "LanguageCode": "en-US"},
    "ta": {"VoiceId": "Aditi", "LanguageCode": "ta-IN"},
    "hi": {"VoiceId": "Aditi", "LanguageCode": "hi-IN"},
}


# -- Alert Message Templates ---------------------------------------------
_TEMPLATES = {
    "en": {
        "advisory": (
            "FloodWatch Advisory: Minor water-level rise predicted near "
            "your location. Stay informed and monitor local updates."
        ),
        "warning": (
            "FloodWatch Warning: Moderate flooding predicted near your "
            "location within the next 1-3 hours. Avoid low-lying areas "
            "and stay alert for further updates."
        ),
        "danger": (
            "FloodWatch Danger: Significant flooding predicted near your "
            "location within the next 1-3 hours. Avoid all travel and "
            "prepare to move to higher ground immediately."
        ),
        "emergency": (
            "FloodWatch EMERGENCY: Severe flooding predicted near your "
            "location within the next 1-3 hours. Evacuate immediately "
            "to the nearest relief center and follow safe evacuation routes."
        ),
    },
    "ta": {
        "advisory": (
            "FloodWatch: ungkal pakuthiyil siriya neermattam uyarvu "
            "kanikkappattullathu. ulloor pudhuppippugalai kavaniyungal."
        ),
        "warning": (
            "FloodWatch echcharikkai: ungkal pakuthiyil aduththa 1-3 mani "
            "neraththil midhamaana vellam kanikkappattullathu. thaazhvaana "
            "pakuthigalaith thavirkavum."
        ),
        "danger": (
            "FloodWatch aapaththu: ungkal pakuthiyil aduththa 1-3 mani "
            "neraththil kadumaiyana vellam kanikkappattullathu. "
            "uyaramaana idaththirkku udanadiyaaga nakaravum."
        ),
        "emergency": (
            "FloodWatch avasaranilai: ungkal pakuthiyil kadumaiyana vellam "
            "kanikkappattullathu. udanadiyaaga veliyeri arugiluullaa "
            "nivaarana maiyaththirkku sellavum."
        ),
    },
    "hi": {
        "advisory": (
            "FloodWatch soochana: aapke kshetra mein maamuli jal star vriddhi "
            "ki bhavishyavaani ki gayi hai. sthaaniy update par nazar rakhein."
        ),
        "warning": (
            "FloodWatch chetaavani: aapke kshetra mein agle 1-3 ghanton mein "
            "madhyam baadh ki bhavishyavaani ki gayi hai. nichle ilakon se "
            "bachein aur satark rahein."
        ),
        "danger": (
            "FloodWatch khatara: aapke kshetra mein agle 1-3 ghanton mein "
            "gambhir baadh ki bhavishyavaani ki gayi hai. turant oonche sthan "
            "par jaayein."
        ),
        "emergency": (
            "FloodWatch aapaatkaal: aapke kshetra mein bhishan baadh ki "
            "bhavishyavaani ki gayi hai. turant nikaasi karein aur nikatam "
            "raahat kendra mein jaayein."
        ),
    },
}


def get_alert_message(severity: str, language: str = "en") -> str:
    """
    Return the localised alert message for a severity and language.

    Args:
        severity: One of advisory / warning / danger / emergency.
        language: ISO 639-1 code (en, ta, hi).

    Returns:
        Alert message string.
    """
    lang_templates = _TEMPLATES.get(language, _TEMPLATES["en"])
    return lang_templates.get(severity, lang_templates.get("advisory", ""))


def get_polly_voice(language: str = "en") -> dict:
    """
    Return the Polly voice configuration for a language.

    Returns:
        Dict with VoiceId and LanguageCode.
    """
    return POLLY_VOICE_MAP.get(language, POLLY_VOICE_MAP["en"])
