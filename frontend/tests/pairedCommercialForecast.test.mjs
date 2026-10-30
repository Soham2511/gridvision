import test from 'node:test';
import assert from 'node:assert/strict';

import {
  isVerifiedPairedForecast,
  loadForecastForSelectedBuilding,
  pairedForecastErrorMessage,
  toPairedForecastSeries,
} from '../src/services/pairedCommercialForecast.js';

function pairedFixture(overrides = {}) {
  return {
    generated_at: '2026-10-29T12:00:00+00:00',
    building: { building_id: 'building-22', 'id.grid.coarse': 408 },
    commercial_forecast: {
      source: 'commercial_building_model',
      model: { model_name: 'commercial-lgbm', model_version: '4', provider: 'mlflow', is_demo: false },
      horizon: [],
    },
    government_forecast: {
      source: 'government_grid_model',
      scope: 'total_grid_demand',
      grid_id: 408,
      model: { model_name: 'government-hybrid', model_version: '9', provider: 'joblib', is_demo: false },
      horizon: [],
    },
    paired_horizon: [
      { timestamp: '2026-10-30T01:00:00Z', horizon_hours: 1, commercial_prediction: 125.5, total_grid_demand_prediction: 3200 },
      { timestamp: '2026-10-30T02:00:00Z', horizon_hours: 2, commercial_prediction: 129, total_grid_demand_prediction: 3310 },
    ],
    ...overrides,
  };
}

test('selected building ID is the one requested and its mapped grid is retained', async () => {
  const requested = [];
  const response = await loadForecastForSelectedBuilding('building-22', async (id) => {
    requested.push(id);
    return pairedFixture();
  });
  assert.deepEqual(requested, ['building-22']);
  assert.equal(response.building['id.grid.coarse'], 408);
  assert.equal(response.government_forecast.grid_id, 408);
});

test('both verified model series are shown on matching timestamps and horizons', () => {
  const rows = toPairedForecastSeries(pairedFixture());
  assert.equal(rows.length, 2);
  assert.equal(rows[0].timestamp, '2026-10-30T01:00:00Z');
  assert.equal(rows[0].horizonHours, 1);
  assert.equal(rows[0].forecastDemand, 125.5);
  assert.equal(rows[0].totalGridDemandPrediction, 3200);
  assert.equal(rows[1].horizonHours, 2);
});

test('missing region mapping is presented as an explicit mapping message', () => {
  const message = pairedForecastErrorMessage({ code: 'REGION_MAPPING_NOT_FOUND' });
  assert.match(message, /no verified coarse-grid mapping/i);
});

test('model and API errors do not fall back to demo forecasts', () => {
  assert.match(
    pairedForecastErrorMessage({ code: 'MODEL_UNAVAILABLE' }),
    /No forecast values are shown/
  );
  assert.equal(pairedForecastErrorMessage(new Error('server error')), 'server error');
});

test('demo model responses and empty paired histories produce no plotted forecast values', () => {
  const demo = pairedFixture();
  demo.commercial_forecast.model.is_demo = true;
  assert.equal(isVerifiedPairedForecast(demo), false);
  assert.deepEqual(toPairedForecastSeries(demo), []);
  assert.deepEqual(toPairedForecastSeries(pairedFixture({ paired_horizon: [] })), []);
});
