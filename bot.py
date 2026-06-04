"""Simple launcher for the Neural Investors Lab Telegram bot."""

from src.core.config import get_settings
from src.core.logging import configure_logging
from src.interfaces.telegram_bot import run_telegram_bot


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    print("=" * 50)
    print("  Neural Investors Lab - Telegram Bot")
    print("=" * 50)

    missing = settings.missing_runtime_secrets()
    if missing:
        print(f"\nMissing runtime secrets: {', '.join(missing)}")
        print("Please configure them in your .env file.\n")
    else:
        print("\nStarting Telegram bot... Press Ctrl+C to stop.\n")
        run_telegram_bot()


if __name__ == "__main__":
    main()
