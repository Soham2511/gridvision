import { useEffect, useMemo, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { SegmentationRegion } from '../../types/segmentation';

const CATEGORY_COLORS: Record<string, string> = {
  Residential: '#087e75',
  Commercial: '#2563eb',
  Industrial: '#d97706',
  Institutional: '#9333ea',
  Recreational: '#db2777',
};
const FALLBACK_COLOR = '#475569';
const TILE_URL = import.meta.env.VITE_MAP_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';

interface GeographicPointsMapProps {
  points: SegmentationRegion[];
  selectedRegion: string | null;
  onSelectRegion: (regionId: string) => void;
}

function popupContent(point: SegmentationRegion): HTMLElement {
  const container = L.DomUtil.create('div', 'gv-seg-map-popup');
  const heading = L.DomUtil.create('strong', '', container);
  heading.textContent = `Grid ${point.region_id}`;
  const details = [
    `Category: ${point.GeneralUseType}`,
    `Segment: ${point.segment_id}`,
    `Buildings: ${point.building_count.toLocaleString('en-US')}`,
    `Coordinates: ${point.latitude?.toFixed(5)}, ${point.longitude?.toFixed(5)}`,
  ];
  details.forEach((detail) => {
    const line = L.DomUtil.create('div', '', container);
    line.textContent = detail;
  });
  return container;
}

export function GeographicPointsMap({ points, selectedRegion, onSelectRegion }: GeographicPointsMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const markerRefs = useRef<Array<{ marker: L.CircleMarker; regionId: string }>>([]);
  const selectedRegionRef = useRef(selectedRegion);
  const onSelectRegionRef = useRef(onSelectRegion);
  const validPoints = useMemo(
    () => points.filter((point) => point.latitude != null && point.longitude != null),
    [points],
  );
  selectedRegionRef.current = selectedRegion;
  onSelectRegionRef.current = onSelectRegion;

  useEffect(() => {
    const container = containerRef.current;
    if (!container || validPoints.length === 0) return undefined;

    const map = L.map(container, {
      scrollWheelZoom: false,
      preferCanvas: true,
    });
    L.tileLayer(TILE_URL, {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
    }).addTo(map);

    const bounds = L.latLngBounds([]);
    validPoints.forEach((point) => {
      const latitude = point.latitude;
      const longitude = point.longitude;
      if (latitude == null || longitude == null) return;
      bounds.extend([latitude, longitude]);
      const regionId = String(point.region_id);
      const selected = regionId === selectedRegionRef.current;
      const color = CATEGORY_COLORS[point.GeneralUseType] ?? FALLBACK_COLOR;
      const marker = L.circleMarker([latitude, longitude], {
        radius: Math.min(13, Math.max(5, 4 + Math.log2(point.building_count + 1))),
        color: selected ? '#0f172a' : '#ffffff',
        weight: selected ? 3 : 1.5,
        fillColor: color,
        fillOpacity: 0.82,
      }).addTo(map);
      marker.bindPopup(popupContent(point));
      marker.on('click', () => onSelectRegionRef.current(regionId));
      markerRefs.current.push({ marker, regionId });
    });

    if (bounds.getNorthEast().equals(bounds.getSouthWest())) {
      map.setView(bounds.getCenter(), 13);
    } else {
      map.fitBounds(bounds.pad(0.08), { maxZoom: 13 });
    }
    const resizeObserver = new ResizeObserver(() => map.invalidateSize());
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      map.remove();
      markerRefs.current = [];
    };
  }, [validPoints]);

  useEffect(() => {
    markerRefs.current.forEach(({ marker, regionId }) => {
      marker.setStyle({
        color: regionId === selectedRegion ? '#0f172a' : '#ffffff',
        weight: regionId === selectedRegion ? 3 : 1.5,
      });
    });
  }, [selectedRegion]);

  const categories = [...new Set(validPoints.map((point) => point.GeneralUseType))];

  if (!validPoints.length) {
    return <div className="gv-seg-map-empty">No coordinate-backed points are available for these filters.</div>;
  }

  return (
    <div className="gv-seg-map-wrap">
      <div ref={containerRef} className="gv-seg-map" role="application" aria-label="Interactive map of segmented grid points" />
      <div className="gv-seg-map-legend" aria-label="Map category legend">
        {categories.map((category) => (
          <span key={category}>
            <i style={{ backgroundColor: CATEGORY_COLORS[category] ?? FALLBACK_COLOR }} />
            {category}
          </span>
        ))}
      </div>
      <p className="gv-seg-map-caption">Circle size represents buildings. Click a point for grid details.</p>
    </div>
  );
}
