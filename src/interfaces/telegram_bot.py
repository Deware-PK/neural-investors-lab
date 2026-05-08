import logging

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

from src.core.config import Settings, get_settings
from src.core.logging import configure_logging
from src.interfaces.formatter import format_boardroom_result_html
from src.main_orchestrator import BoardroomOrchestrator


logger = logging.getLogger(__name__)


class TelegramBotInterface:
    def __init__(self, orchestrator: BoardroomOrchestrator | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.orchestrator = orchestrator or BoardroomOrchestrator(settings=self.settings)

    def build_application(self) -> Application:
        if self.settings.telegram_bot_token is None:
            msg = "TELEGRAM_BOT_TOKEN is required to start the Telegram bot."
            raise ValueError(msg)
        application = ApplicationBuilder().token(self.settings.telegram_bot_token.get_secret_value()).build()
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("analyze", self.analyze_command))
        return application

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._reply(update, "<b>Neural Investors Lab</b>\nUse <code>/analyze TICKER</code> to start a boardroom review.")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._reply(
            update,
            "<b>Commands</b>\n<code>/analyze AAPL</code>\n<code>/analyze AAPL https://example.com/news</code>",
        )

    async def analyze_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await self._reply(update, "Usage: <code>/analyze TICKER [article_url ...]</code>")
            return
        ticker = context.args[0].upper()
        article_urls = context.args[1:]
        logger.info("Telegram ticker request received: %s", ticker)
        await self._reply(update, f"Running boardroom analysis for <b>{ticker}</b>...")
        result = await self.orchestrator.analyze_ticker(ticker, article_urls=article_urls, persist=True)
        await self._reply(update, format_boardroom_result_html(result))

    @staticmethod
    async def _reply(update: Update, text: str) -> None:
        if update.effective_message is not None:
            await update.effective_message.reply_html(text, disable_web_page_preview=True)


def run_telegram_bot() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    application = TelegramBotInterface(settings=settings).build_application()
    application.run_polling(allowed_updates=Update.ALL_TYPES)
