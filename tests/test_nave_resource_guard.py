from research.nave.resource_guard import check


def test_allows_small_operation_inside_included_and_checkpoint_caps():
    result = check(
        credits_used=2024.104,
        credits_included=2500,
        checkpoint_used=2024.104,
        estimate=25,
        free_disk_gb=49,
    )

    assert result.allowed is True
    assert result.level == "OK"
    assert abs(result.remaining_included - 475.896) < 1e-9


def test_fails_closed_when_operation_exceeds_hard_stop():
    result = check(
        credits_used=2024.104,
        credits_included=2500,
        checkpoint_used=1900,
        estimate=76,
        free_disk_gb=49,
    )

    assert result.allowed is False
    assert result.level == "HARD_STOP"
    assert any("hard stop" in reason for reason in result.reasons)


def test_fails_closed_when_provider_snapshot_is_missing_or_unsafe():
    result = check(
        credits_used=2024.104,
        credits_included=2500,
        checkpoint_used=2024.104,
        estimate=1,
        free_disk_gb=14.9,
    )

    assert result.allowed is False
    assert any("disk" in reason for reason in result.reasons)
