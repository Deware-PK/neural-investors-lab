import asyncio
import base64
from io import BytesIO
import logging

import matplotlib
matplotlib.use('Agg')
import mplfinance as mpf

from src.agents.json_utils import parse_json_model
from src.core.config import Settings, get_settings
from src.core.llm_client import ChatMessage, OpenRouterClient, get_openrouter_client
from src.models.technical_schema import TechnicalAnalysis
from src.models.vision_schema import VisualChartAnalysis
from src.services.finance_api import FinanceAPI
from src.services.indicator_math import IndicatorMath


logger = logging.getLogger(__name__)


class ChartistAgent:
    def __init__(
        self,
        finance_api: FinanceAPI | None = None,
        indicator_math: IndicatorMath | None = None,
        llm_client: OpenRouterClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.finance_api = finance_api or FinanceAPI(settings=self.settings)
        self.indicator_math = indicator_math or IndicatorMath()
        self.llm_client = llm_client

    def analyze(self, ticker: str, period: str = "2y", interval: str = "1d") -> TechnicalAnalysis:
        symbol = ticker.upper()
        logger.info("Chartist started for %s", symbol)
        history = self.finance_api.fetch_historical_prices(symbol, period=period, interval=interval)
        result = self.indicator_math.analyze_technical(symbol, history)
        try:
            mtf_bars = self.finance_api.fetch_multi_timeframe(symbol)
            mtf = self.indicator_math.analyze_multi_timeframe(
                mtf_bars["weekly"], mtf_bars["monthly"], result.close_price
            )
            result = result.model_copy(update={"multi_timeframe": mtf})
        except Exception:
            logger.warning("Multi-timeframe analysis failed for %s", symbol)
        logger.info(
            "Chartist completed for %s: close=%.2f, trend=%s, rsi=%s, momentum=%s, volume=%s, volatility=%s, support=%s, resistance=%s, mtf=%s",
            symbol,
            result.close_price,
            result.moving_average.state,
            f"{result.momentum.rsi:.1f}" if result.momentum.rsi is not None else "N/A",
            result.momentum.tag or "N/A",
            result.volume.volume_trend,
            result.volatility.bollinger_state,
            result.support_levels[:3] if result.support_levels else [],
            result.resistance_levels[:3] if result.resistance_levels else [],
            result.multi_timeframe.confluence_tag if result.multi_timeframe else "N/A",
        )
        return result

    async def get_visual_analysis(self, ticker: str, period: str = "6mo", interval: str = "1d") -> VisualChartAnalysis:
        return await asyncio.to_thread(self._get_visual_analysis_sync, ticker, period, interval)

    def _get_visual_analysis_sync(self, ticker: str, period: str, interval: str) -> VisualChartAnalysis:
        symbol = ticker.upper()
        logger.info("Visual chart analysis started for %s", symbol)
        image_base64 = self._get_chart_image_base64(symbol, period=period, interval=interval)
        client = self.llm_client or get_openrouter_client(self.settings)
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "You are an expert Price Action (PA) Chart Analyst. Analyze the supplied candlestick chart image to provide context that raw data cannot see. "
                    "RULES: "
                    "1. Return ONLY strict JSON matching the VisualChartAnalysis schema. "
                    "2. Focus heavily on identifying recent price rejections (e.g., long wicks), consolidation zones, and momentum shifts. "
                    "3. Do not invent precise numeric prices; use visual estimation for 'support_zones' and 'resistance_zones' (e.g., 'Demand zone around recent swing low'). "
                    "4. In 'observed_patterns', strictly name standard patterns (e.g., Bull Flag, Double Bottom, Bearish Engulfing) only if they are clearly visible. "
                    "5. Evaluate if the visual volume trend validates the price action. "
                    "Your visual context will serve as a crucial validation layer for algorithmic indicators."
                ),
            ),
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Ticker: {symbol}. Perform visual chart analysis from this mplfinance candlestick chart. "
                            "Support/resistance zones may be approximate visual price levels."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                    },
                ],
            },
        ]
        response = client.generate_completion(
            model=self.settings.news_analyst_model,
            messages=messages,
            use_reasoning=self.settings.news_analyst_model_reasoning,
            temperature=0.1,
        )
        parsed = parse_json_model(response.content, VisualChartAnalysis)
        if parsed.ticker.upper() != symbol:
            parsed = parsed.model_copy(update={"ticker": symbol})
        logger.info(
            "Visual chart analysis completed for %s: sentiment=%s, confidence=%.2f, patterns=%s, support_zones=%s, resistance_zones=%s",
            symbol,
            parsed.sentiment,
            parsed.confidence_score,
            parsed.observed_patterns[:3] if parsed.observed_patterns else [],
            parsed.support_zones[:3] if parsed.support_zones else [],
            parsed.resistance_zones[:3] if parsed.resistance_zones else [],
        )
        return parsed

    def _get_chart_image_base64(self, ticker: str, period: str = "6mo", interval: str = "1d") -> str:
        symbol = ticker.upper()
        history = self.finance_api.fetch_historical_prices(symbol, period=period, interval=interval)
        frame = self.finance_api.bars_to_frame(history)
        if frame.empty:
            msg = f"No price history available to render chart for {symbol}"
            raise ValueError(msg)
        chart_frame = frame.rename(
            columns={
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "volume": "Volume",
            }
        )
        buffer = BytesIO()
        mpf.plot(
            chart_frame,
            type="candle",
            volume=True,
            style="yahoo",
            title=f"{symbol} {period} {interval}",
            ylabel="Price",
            ylabel_lower="Volume",
            savefig={"fname": buffer, "format": "png", "bbox_inches": "tight"},
        )
        buffer.seek(0)
        return base64.b64encode(buffer.read()).decode("ascii")
