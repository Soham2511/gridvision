import type { PairedCommercialForecast } from '../types/analytics';

export function loadForecastForSelectedBuilding<T>(
  buildingId: string,
  requestForecast: (buildingId: string) => Promise<T>
): Promise<T>;
export function pairedForecastErrorMessage(error: unknown): string;
export function isVerifiedPairedForecast(
  forecast: PairedCommercialForecast | null | undefined
): forecast is PairedCommercialForecast;
export function toPairedForecastSeries(
  forecast: PairedCommercialForecast | null | undefined
): {
  timestamp: string;
  formattedTime: string;
  actualDemand: null;
  forecastDemand: number;
  totalGridDemandPrediction: number;
  horizonHours: number;
}[];
