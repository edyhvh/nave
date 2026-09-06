import json

from scripts.memecoin_experiment_preflight import inspect_manifest


def test_closed_acquisition_cannot_prove_population_or_execution(tmp_path):
    path = tmp_path / 'manifest.json'
    data = {'date': '2026-09-01', 'execution_id': 'inline:2026-09-02T01:00:00Z',
            'rows': [{'mint': 'one'}], 'sample_size': 1, 'denominator': 1000}
    path.write_text(json.dumps(data))
    result = inspect_manifest(path)
    assert result['acquired_after_close'] is True
    assert result['complete_population_proven'] is False
    data['execution_id'] = 'opaque-provider-execution-id'
    path.write_text(json.dumps(data))
    assert inspect_manifest(path)['acquired_after_close'] is None
