from datetime import date

from trading.stocks.portfolio_manager import (
    Action,
    Candidate,
    Evidence,
    PortfolioPolicy,
    Position,
    allocate_monthly_budget,
    monthly_review_date,
    rank_candidates,
    review_positions,
)


def test_monthly_review_moves_weekend_funding_to_monday() -> None:
    assert monthly_review_date(2026, 8) == date(2026, 8, 26)
    assert monthly_review_date(2026, 11) == date(2026, 11, 27)
    assert monthly_review_date(2026, 7) == date(2026, 7, 27)


def test_rank_requires_confluence_and_ondo_liquidity_penalty() -> None:
    policy = PortfolioPolicy()
    candidates = [
        Candidate("NVDA", Evidence(ism_score=1.0, congress_score=.8,
                                    technical_score=1.0, reserve_ai_score=1.0,
                                    social_score=.8, ondo_available=True,
                                    ondo_liquid=True),
                 price=100.0, entry_zone=(90.0, 110.0)),
        Candidate("TSLA", Evidence(ism_score=.9, technical_score=.2,
                                    ondo_available=True, ondo_liquid=False)),
    ]
    decisions = rank_candidates(candidates, policy=policy)
    assert decisions[0].ticker == "NVDA"
    assert decisions[0].action is Action.ENTER
    assert decisions[1].action is not Action.ENTER
    assert "technical_confirmation_missing" in decisions[1].reason_codes


def test_allocator_keeps_cash_and_caps_each_position() -> None:
    policy = PortfolioPolicy(monthly_budget=300)
    decisions = [
        *rank_candidates(
            [Candidate("NVDA", Evidence(ism_score=1, technical_score=1,
                                          reserve_ai_score=1, ondo_available=True,
                                          ondo_liquid=True),
                       price=100.0, entry_zone=(90.0, 110.0)),
             Candidate("AMD", Evidence(ism_score=1, technical_score=1,
                                        reserve_ai_score=1, ondo_available=True,
                                        ondo_liquid=True),
                       price=100.0, entry_zone=(90.0, 110.0))],
            policy=policy,
        )
    ]
    allocations = allocate_monthly_budget(decisions, policy=policy)
    assert len(allocations) == 2
    assert sum(item.allocation_usd for item in allocations) == 210.0
    assert all(item.allocation_usd <= 105.0 for item in allocations)


def test_allocator_respects_existing_open_book() -> None:
    policy = PortfolioPolicy(monthly_budget=300, max_positions=8)
    decisions = rank_candidates(
        [
            Candidate(
                "NVDA",
                Evidence(
                    ism_score=1,
                    technical_score=1,
                    reserve_ai_score=1,
                    ondo_available=True,
                    ondo_liquid=True,
                ),
            )
        ],
        policy=policy,
    )
    open_book = ["BAC", "MSFT", "FCX", "AMZN", "META", "TSLA", "COST", "SPY"]
    assert allocate_monthly_budget(decisions, policy=policy, open_tickers=open_book) == []


def test_price_outside_entry_zone_is_watch() -> None:
    policy = PortfolioPolicy()
    decisions = rank_candidates(
        [
            Candidate(
                "NVDA",
                Evidence(
                    ism_score=1,
                    technical_score=1,
                    reserve_ai_score=1,
                    ondo_available=True,
                    ondo_liquid=True,
                ),
                price=200.0,
                entry_zone=(100.0, 120.0),
            )
        ],
        policy=policy,
    )
    assert decisions[0].action is Action.WATCH
    assert "price_outside_entry_zone" in decisions[0].reason_codes


def test_missing_entry_zone_is_watch_even_with_perfect_evidence() -> None:
    decisions = rank_candidates(
        [Candidate("NVDA", Evidence(ism_score=1, congress_score=1,
                                     technical_score=1, reserve_ai_score=1,
                                     social_score=1, ondo_available=True,
                                     ondo_liquid=True))],
        policy=PortfolioPolicy(),
    )
    assert decisions[0].action is Action.WATCH
    assert "entry_zone_not_checked" in decisions[0].reason_codes


def test_broken_thesis_is_exit_and_profit_or_drawdown_is_review() -> None:
    policy = PortfolioPolicy()
    decisions = review_positions(
        [
            Position("META", 100, 80, thesis_status="active",
                     evidence=Evidence(technical_score=.3)),
            Position("MSFT", 100, 125, thesis_status="active",
                     evidence=Evidence(technical_score=.8)),
            Position("TSLA", 100, 90, thesis_status="broken"),
        ],
        policy=policy,
    )
    assert decisions[0].action is Action.REVIEW
    assert decisions[1].action is Action.REVIEW
    assert decisions[2].action is Action.EXIT
