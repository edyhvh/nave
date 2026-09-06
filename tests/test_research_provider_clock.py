from types import SimpleNamespace

from app.services import openbb


def test_provider_as_of_is_observation_not_retrieval(monkeypatch):
    monkeypatch.setattr(openbb, '_get_obb', lambda: SimpleNamespace(economy=SimpleNamespace(
        fred_series=lambda **kwargs: [{'observation_date': '2026-01-02', 'value': 3}])) )
    data = openbb.fetch_fred_series('fixture')
    assert data['as_of'] == data['latest_observation_at'] == '2026-01-02T00:00:00+00:00'
    assert data['retrieved_at'] != data['as_of']


def test_spread_does_not_invent_common_observation(monkeypatch):
    monkeypatch.setitem(openbb.OPENBB_INDICATORS, 'fixture', {'type': 'yield_curve_spread', 'long_symbol': 'a', 'short_symbol': 'b'})
    monkeypatch.setattr(openbb, 'fetch_fixedincome_rate', lambda symbol: {
        'records': [{'value': 3}], 'latest_observation_at': '2026-01-02' if symbol == 'a' else None})
    data = openbb.fetch_openbb_indicator('fixture')
    assert data['as_of'] is None
    assert data['latest_observation_at'] is None
    assert data['retrieved_at']
