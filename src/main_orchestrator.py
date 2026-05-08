import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from src.agents.auditor import AuditorAgent
from src.agents.chartist import ChartistAgent
from src.agents.chief_strategist import ChiefStrategistAgent
from src.agents.researcher import ResearcherAgent
from src.agents.risk_manager import RiskManagerAgent
from src.core.config import Settings, get_settings
from src.core.db_postgres import create_session_factory, initialize_database, persist_analysis_output
from src.core.db_redis import create_optional_redis_client
from src.models.agent_schema import ConflictAssessment, StrategyDraft
from src.models.fundamental_schema import FundamentalAnalysis
from src.models.research_schema import ResearchFinding
from src.models.synthesis_schema import FinalSynthesis
from src.models.technical_schema import TechnicalAnalysis
from src.services.deep_research import DeepResearchService
from src.services.finance_api import FinanceAPI
from src.services.indicator_math import IndicatorMath


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BoardroomResult:
    ticker: str
    fundamentals: FundamentalAnalysis
    technicals: TechnicalAnalysis
    research: ResearchFinding
    conflict_assessment: ConflictAssessment
    strategy_draft: StrategyDraft
    final_synthesis: FinalSynthesis
    persisted_record_id: str | None = None


class BoardroomOrchestrator:
    def __init__(
        self,
        auditor: AuditorAgent | None = None,
        chartist: ChartistAgent | None = None,
        researcher: ResearcherAgent | None = None,
        chief_strategist: ChiefStrategistAgent | None = None,
        risk_manager: RiskManagerAgent | None = None,
        session_factory: sessionmaker[Session] | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        redis_client = create_optional_redis_client(self.settings)
        finance_api = FinanceAPI(redis_client=redis_client)
        indicator_math = IndicatorMath()
        deep_research = DeepResearchService(redis_client=redis_client)
        self.auditor = auditor or AuditorAgent(finance_api=finance_api, indicator_math=indicator_math)
        self.chartist = chartist or ChartistAgent(finance_api=finance_api, indicator_math=indicator_math)
        self.researcher = researcher or ResearcherAgent(deep_research=deep_research, settings=self.settings)
        self.chief_strategist = chief_strategist or ChiefStrategistAgent(settings=self.settings)
        self.risk_manager = risk_manager or RiskManagerAgent(settings=self.settings)
        self.session_factory = session_factory

    async def analyze_ticker(
        self,
        ticker: str,
        article_urls: list[str] | None = None,
        persist: bool = True,
    ) -> BoardroomResult:
        symbol = ticker.upper()
        logger.info("Incoming ticker request: %s", symbol)
        fundamentals_task = asyncio.to_thread(self.auditor.analyze, symbol)
        technicals_task = asyncio.to_thread(self.chartist.analyze, symbol)
        research_task = asyncio.to_thread(self.researcher.analyze, symbol, article_urls)
        fundamentals, technicals, research = await asyncio.gather(fundamentals_task, technicals_task, research_task)
        logger.info("Round 1 agents completed for %s", symbol)

        conflict = self.chief_strategist.identify_contradictions(fundamentals, technicals, research)
        final_research = research
        if conflict.has_conflict and conflict.deep_dive_query is not None:
            logger.info("Debate triggered for %s: %s", symbol, "; ".join(conflict.reasons))
            final_research = await asyncio.to_thread(
                self.researcher.investigate_conflict,
                symbol,
                conflict.deep_dive_query,
                article_urls,
            )
        else:
            logger.info("No debate trigger for %s", symbol)

        draft = await asyncio.to_thread(
            self.chief_strategist.draft_strategy_with_assessment,
            fundamentals,
            technicals,
            final_research,
            conflict,
        )
        logger.info("CEO draft completed for %s with action=%s", symbol, draft.action)
        final = await asyncio.to_thread(self.risk_manager.finalize, draft, technicals)
        logger.info("Final Risk Manager decision for %s: %s", symbol, final.risk_decision)
        record_id = await asyncio.to_thread(self._persist_final_output, symbol, final) if persist else None
        return BoardroomResult(
            ticker=symbol,
            fundamentals=fundamentals,
            technicals=technicals,
            research=final_research,
            conflict_assessment=conflict,
            strategy_draft=draft,
            final_synthesis=final,
            persisted_record_id=record_id,
        )

    def _persist_final_output(self, ticker: str, final: FinalSynthesis) -> str | None:
        if self.session_factory is None:
            self.session_factory = create_session_factory()
        session = self.session_factory()
        try:
            initialize_database(session.get_bind())
            record_id = persist_analysis_output(session, ticker, final.model_dump(mode="json"))
            logger.info("Persisted final output for %s as %s", ticker, record_id)
            return record_id
        except Exception:
            logger.exception("Failed to persist final output for %s", ticker)
            session.rollback()
            return None
        finally:
            session.close()


def run_boardroom_analysis(ticker: str, article_urls: list[str] | None = None, persist: bool = True) -> BoardroomResult:
    return asyncio.run(BoardroomOrchestrator().analyze_ticker(ticker, article_urls=article_urls, persist=persist))
