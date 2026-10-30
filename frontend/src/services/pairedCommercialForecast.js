/**
 * Pure presentation helpers for paired commercial and total-grid forecasts.
 * Kept in JavaScript so the same selection/error logic can run under node:test.
 */

export async function loadForecastForSelectedBuilding(buildingId, requestForecast) {
  if (!buildingId) throw new Error('Select a commercial building first.');
  return requestForecast(buildingId);
}

export function pairedForecastErrorMessage(error) {
  const code = error && typeof error === 'object' ? error.code : undefined;
  if (code === 'REGION_MAPPING_NOT_FOUND') {
    return 'This building has no verified coarse-grid mapping, so its government forecast cannot be associated.';
  }
  if (code === 'MODEL_UNAVAILABLE') {
    return 'The commercial or government forecasting model is unavailable. No forecast values are shown.';
  }
  if (code === 'INVALID_MODEL_OUTPUT') {
    return 'A forecasting model returned invalid values. No forecast values are shown.';
  }
  return error instanceof Error ? error.message : 'Unable to load the paired forecast.';
}

export function isVerifiedPairedForecast(forecast) {
  return Boolean(
    forecast &&
      forecast.commercial_forecast?.model?.is_demo === false &&
      forecast.government_forecast?.model?.is_demo === false &&
      Array.isArray(forecast.paired_horizon)
  );
}

export function toPairedForecastSeries(forecast) {
  if (!isVerifiedPairedForecast(forecast)) return [];
  return forecast.paired_horizon.map((point) => ({
    timestamp: point.timestamp,
    formattedTime: new Date(point.timestamp).toLocaleString(),
    actualDemand: null,
    forecastDemand: point.commercial_prediction,
    totalGridDemandPrediction: point.total_grid_demand_prediction,
    horizonHours: point.horizon_hours,
  }));
}
