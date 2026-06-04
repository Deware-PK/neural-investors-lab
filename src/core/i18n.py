from typing import Literal

Language = Literal["en", "th"]

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # Formatter labels
        "trade_plan": "Trade Plan",
        "entry": "Entry",
        "take_profit": "Take Profit",
        "stop_loss": "Stop Loss",
        "thesis": "Thesis",
        "key_risks": "Key Risks",
        "evidence": "Evidence",
        "conviction": "Conviction",
        "risk_decision": "Risk Decision",
        "position_size": "Position Size",
        "boardroom_signals": "Boardroom Signals",
        "fundamentals": "Fundamentals",
        "technicals": "Technicals",
        "research": "Research",
        "visual_chart": "Visual Chart",
        "debate_triggered": "Debate Triggered",
        "na": "N/A",
        # Telegram bot
        "bot_start": "<b>Neural Investors Lab</b>\nUse <code>/analyze TICKER</code> to start a boardroom review.",
        "bot_help": "<b>Commands</b>\n<code>/analyze AAPL</code>\n<code>/analyze AAPL https://example.com/news</code>",
        "bot_analyze_usage": "Usage: <code>/analyze TICKER [article_url ...]</code>",
        "bot_analyze_running": "Running boardroom analysis for <b>{ticker}</b>...",
        "bot_button_start": "🚀 Start Analysis",
        "bot_ask_ticker": "Which ticker would you like to analyze?",
        "bot_ask_language": "Select output language:",
        "bot_button_thai": "🇹🇭 Thai",
        "bot_button_english": "🇬🇧 English",
        "bot_invalid_ticker": "Please enter a valid ticker symbol (e.g., AAPL, NVDA).",
        "bot_cancel": "Analysis cancelled.",
        "bot_error": "❌ <b>Analysis failed</b>\nSomething went wrong during the boardroom review.\nPlease try again or use <code>/analyze TICKER</code>.",
        # LLM prompt suffix
        "llm_prompt_suffix": (
            "All narrative text (thesis, key_risks, rationale, summary, catalysts, concerns, observed_patterns) "
            "must be written in clear, professional English. JSON keys and enum values remain in English."
        ),
    },
    "th": {
        # Formatter labels
        "trade_plan": "แผนการเทรด",
        "entry": "จุดเข้า",
        "take_profit": "เป้าหมายทำกำไร",
        "stop_loss": "จุดตัดขาดทุน",
        "thesis": "ข้อสรุป",
        "key_risks": "ความเสี่ยงสำคัญ",
        "evidence": "หลักฐานสนับสนุน",
        "conviction": "ความมั่นใจ",
        "risk_decision": "การตัดสินใจด้านความเสี่ยง",
        "position_size": "ขนาดพอร์ต",
        "boardroom_signals": "สัญญาณจากบอร์ดรูม",
        "fundamentals": "ปัจจัยพื้นฐาน",
        "technicals": "ปัจจัยทางเทคนิค",
        "research": "งานวิจัย",
        "visual_chart": "วิเคราะห์กราฟ",
        "debate_triggered": "เกิดการโต้แย้ง",
        "na": "ไม่มี",
        # Telegram bot
        "bot_start": "<b>Neural Investors Lab</b>\nใช้ <code>/analyze TICKER</code> เพื่อเริ่มต้นการวิเคราะห์",
        "bot_help": "<b>คำสั่ง</b>\n<code>/analyze AAPL</code>\n<code>/analyze AAPL https://example.com/news</code>",
        "bot_analyze_usage": "การใช้งาน: <code>/analyze TICKER [article_url ...]</code>",
        "bot_analyze_running": "กำลังวิเคราะห์ <b>{ticker}</b>...",
        "bot_button_start": "🚀 เริ่มต้นวิเคราะห์",
        "bot_ask_ticker": "หุ้นอะไรที่ต้องการวิเคราะห์?",
        "bot_ask_language": "เลือกภาษาสำหรับผลลัพธ์:",
        "bot_button_thai": "🇹🇭 ไทย",
        "bot_button_english": "🇬🇧 English",
        "bot_invalid_ticker": "กรุณากรอกชื่อหุ้นที่ถูกต้อง (เช่น AAPL, NVDA)",
        "bot_cancel": "ยกเลิกการวิเคราะห์แล้ว",
        "bot_error": "❌ <b>วิเคราะห์ล้มเหลว</b>\nเกิดข้อผิดพลาดระหว่างการวิเคราะห์\nกรุณาลองใหม่อีกครั้งหรือใช้ <code>/analyze TICKER</code>",
        # LLM prompt suffix
        "llm_prompt_suffix": (
            "CRITICAL LANGUAGE RULE: You MUST write ALL narrative text in Thai language only. "
            "This includes thesis, key_risks, rationale, summary, catalysts, concerns, and observed_patterns. "
            "DO NOT write any narrative in English. Write naturally in Thai as if explaining to a Thai investor. "
            "Example of CORRECT thesis: 'หุ้นตัวนี้มีแนวโน้มขาขึ้นจากสัญญาณทางเทคนิคที่แข็งแกร่ง' "
            "Example of WRONG thesis: 'The stock shows strong technical signals' — NEVER do this. "
            "JSON keys and enum values MUST remain in English."
        ),
    },
}


def get_text(lang: str, key: str) -> str:
    """Return translated text for the given language and key."""
    return _TRANSLATIONS.get(lang, _TRANSLATIONS["en"]).get(key, key)


def get_prompt_suffix(lang: str) -> str:
    """Return the LLM prompt language instruction suffix."""
    return get_text(lang, "llm_prompt_suffix")


def localize_prompt(system_content: str, lang: str) -> str:
    """Prepend language instruction to an LLM system prompt when lang is not English."""
    if lang == "en":
        return system_content
    suffix = get_prompt_suffix(lang)
    return f"LANGUAGE RULE (READ FIRST): {suffix}\n\n{system_content}"
