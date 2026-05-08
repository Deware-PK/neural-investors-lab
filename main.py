from src.core.config import get_settings
from src.core.logging import configure_logging
from src.models.synthesis_schema import Action, FinalSynthesis, RiskDecision


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    FinalSynthesis(
        ticker="SMOKE",
        action=Action.HOLD,
        conviction_score=0,
        entry_price=None,
        take_profit=None,
        stop_loss=None,
        position_size_pct=0,
        risk_decision=RiskDecision.APPROVED,
        thesis="Foundation smoke check only.",
        key_risks=[],
        evidence=[],
    )

    missing_secrets = settings.missing_runtime_secrets()
    if missing_secrets:
        print(f"Foundation bootstrap OK. Missing runtime secrets: {', '.join(missing_secrets)}")
        return

    print("Foundation bootstrap OK. Runtime secrets are configured.")


if __name__ == "__main__":
    main()
