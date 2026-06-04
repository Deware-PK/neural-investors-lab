import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.core.config import Settings, get_settings
from src.core.logging import configure_logging
from src.core.i18n import get_text
from src.interfaces.formatter import format_boardroom_result_html
from src.main_orchestrator import BoardroomOrchestrator


logger = logging.getLogger(__name__)

# Conversation states
ASKING_TICKER = 1
SELECTING_LANGUAGE = 2


class TelegramBotInterface:
    def __init__(self, orchestrator: BoardroomOrchestrator | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.orchestrator = orchestrator or BoardroomOrchestrator(settings=self.settings)

    def build_application(self) -> Application:
        if self.settings.telegram_bot_token is None:
            msg = "TELEGRAM_BOT_TOKEN is required to start the Telegram bot."
            raise ValueError(msg)
        application = ApplicationBuilder().token(self.settings.telegram_bot_token.get_secret_value()).build()

        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler("start", self.start_command),
                CallbackQueryHandler(self.cb_start, pattern="^cb_start$"),
            ],
            states={
                ASKING_TICKER: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_ticker),
                ],
                SELECTING_LANGUAGE: [
                    CallbackQueryHandler(self.receive_language, pattern="^lang_(en|th)$"),
                ],
            },
            fallbacks=[
                CommandHandler("cancel", self.cancel_command),
                CommandHandler("help", self.help_command),
                CommandHandler("analyze", self.analyze_command),
            ],
            per_message=False,
        )

        application.add_handler(conv_handler)
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("analyze", self.analyze_command))
        application.add_error_handler(self._error_handler)
        return application

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        keyboard = [
            [InlineKeyboardButton(
                get_text(self.settings.output_language, "bot_button_start"),
                callback_data="cb_start",
            )],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.effective_message is not None:
            await update.effective_message.reply_html(
                get_text(self.settings.output_language, "bot_start"),
                reply_markup=reply_markup,
            )
        return ConversationHandler.END

    async def cb_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        if query is not None:
            await query.answer()
            await query.edit_message_text(
                get_text(self.settings.output_language, "bot_ask_ticker"),
            )
        return ASKING_TICKER

    async def receive_ticker(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if update.effective_message is None:
            return ConversationHandler.END
        raw = update.effective_message.text or ""
        ticker = re.sub(r"[^A-Za-z0-9.-]", "", raw).upper()
        if not ticker or len(ticker) > 16:
            await update.effective_message.reply_html(
                get_text(self.settings.output_language, "bot_invalid_ticker"),
            )
            return ASKING_TICKER
        context.user_data["ticker"] = ticker
        logger.info("Telegram user entered ticker: %s", ticker)

        keyboard = [
            [
                InlineKeyboardButton(
                    get_text("th", "bot_button_thai"),
                    callback_data="lang_th",
                ),
                InlineKeyboardButton(
                    get_text("en", "bot_button_english"),
                    callback_data="lang_en",
                ),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.effective_message.reply_html(
            get_text(self.settings.output_language, "bot_ask_language"),
            reply_markup=reply_markup,
        )
        return SELECTING_LANGUAGE

    async def receive_language(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        if query is None or query.data is None:
            return ConversationHandler.END
        await query.answer()
        lang = query.data.replace("lang_", "")
        context.user_data["lang"] = lang
        ticker = context.user_data.get("ticker", "")
        logger.info("Telegram user selected language %s for ticker %s", lang, ticker)

        await query.edit_message_text(
            get_text(lang, "bot_analyze_running").format(ticker=ticker),
        )

        # Temporarily override language so all agents receive Thai prompts
        original_lang = self.settings.output_language
        self.settings.output_language = lang
        try:
            result = await self.orchestrator.analyze_ticker(ticker, article_urls=None, persist=True)
        except Exception:
            logger.exception("Analysis failed for %s", ticker)
            await query.edit_message_text(
                get_text(lang, "bot_error"),
            )
            self.settings.output_language = original_lang
            context.user_data.clear()
            return ConversationHandler.END
        finally:
            self.settings.output_language = original_lang

        await self._reply(update, format_boardroom_result_html(result, lang=lang))

        context.user_data.clear()
        return ConversationHandler.END

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if update.effective_message is not None:
            await update.effective_message.reply_html(
                get_text(self.settings.output_language, "bot_cancel"),
            )
        context.user_data.clear()
        return ConversationHandler.END

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._reply(update, get_text(self.settings.output_language, "bot_help"))

    async def analyze_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await self._reply(update, get_text(self.settings.output_language, "bot_analyze_usage"))
            return
        ticker = context.args[0].upper()
        article_urls = context.args[1:]
        logger.info("Telegram ticker request received: %s", ticker)
        await self._reply(update, get_text(self.settings.output_language, "bot_analyze_running").format(ticker=ticker))
        result = await self.orchestrator.analyze_ticker(ticker, article_urls=article_urls, persist=True)
        await self._reply(update, format_boardroom_result_html(result, lang=self.settings.output_language))

    async def _error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log full exception tracebacks from Telegram handler errors."""
        logger.error("Exception while handling an update: %s", context.error, exc_info=context.error)

    @staticmethod
    async def _reply(update: Update, text: str) -> None:
        if update.effective_message is not None:
            await update.effective_message.reply_html(text, disable_web_page_preview=True)
        elif update.callback_query is not None and update.callback_query.message is not None:
            await update.callback_query.message.reply_html(text, disable_web_page_preview=True)


def run_telegram_bot() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    application = TelegramBotInterface(settings=settings).build_application()
    application.run_polling(allowed_updates=Update.ALL_TYPES)
