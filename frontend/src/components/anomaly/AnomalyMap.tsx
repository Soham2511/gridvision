import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AnomalyEntity,
  AnomalyEvent,
  AnomalySpatialCluster,
} from '../../services/anomalyService';

interface AnomalyMapProps {
  entities: AnomalyEntity[];
  events: AnomalyEvent[];
  selectedEventId: string;
  onSelectEvent: (eventId: string) => void;
}

interface ViewState {
  zoom: number;
  panX: number;
  panY: number;
}

interface BasemapTile {
  key: string;
  url: string;
  left: number;
  top: number;
  size: number;
}

const EARTH_RADIUS_KM = 6371.0088;
const MAX_MERCATOR_LATITUDE = 85.05112878;
const TILE_SIZE = 256;
const MAX_TILE_ZOOM = 19;
const OSM_TILE_URL =
  import.meta.env.VITE_OSM_TILE_URL ?? 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const COLORS: Record<AnomalyEvent['event_scope'], string> = {
  SINGLE_CUSTOMER: '#EF4444',
  LOCAL_AREA: '#F59E0B',
  MULTI_AREA: '#087EBD',
};

const project = (latitude: number, longitude: number): [number, number] => {
  const clampedLatitude = Math.max(
    -MAX_MERCATOR_LATITUDE,
    Math.min(MAX_MERCATOR_LATITUDE, latitude),
  );
  const radians = (clampedLatitude * Math.PI) / 180;
  return [
    (longitude + 180) / 360,
    (1 - Math.log(Math.tan(radians) + 1 / Math.cos(radians)) / Math.PI) / 2,
  ];
};

const eventRadiusPixels = (
  event: Pick<AnomalyEvent, 'latitude_center' | 'spatial_extent_km'>,
  scale: number,
): number => {
  const latitudeScale = Math.max(
    0.05,
    Math.cos((event.latitude_center * Math.PI) / 180),
  );
  const radiusKm = Math.max(0, event.spatial_extent_km) / 2;
  const radiusPixels =
    (radiusKm / (2 * Math.PI * EARTH_RADIUS_KM * latitudeScale)) * scale;
  return Math.max(event.spatial_extent_km > 0 ? 1 : 6, radiusPixels);
};

export const AnomalyMap: React.FC<AnomalyMapProps> = ({
  entities,
  events,
  selectedEventId,
  onSelectEvent,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ pointerId: number; x: number; y: number; moved: boolean } | null>(null);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [view, setView] = useState<ViewState>({ zoom: 1, panX: 0, panY: 0 });
  const [failedTileKeys, setFailedTileKeys] = useState<Set<string>>(() => new Set());

  const points = useMemo(
    () =>
      entities
        .filter(
          (entity) =>
            Number.isFinite(entity.latitude) &&
            Number.isFinite(entity.longitude) &&
            entity.latitude >= -90 &&
            entity.latitude <= 90 &&
            entity.longitude >= -180 &&
            entity.longitude <= 180,
        )
        .map((entity) => ({ entity, position: project(entity.latitude, entity.longitude) })),
    [entities],
  );
  const eventCustomers = useMemo(() => {
    const byCustomer = new Map<number, AnomalyEvent>();
    events.forEach((event) => {
      event.customer_ids.forEach((customerId) => byCustomer.set(customerId, event));
    });
    return byCustomer;
  }, [events]);
  const selectedEvent = events.find((event) => event.event_id === selectedEventId);
  const selectedEventScope = selectedEvent?.event_scope;
  const selectedEventCustomers = useMemo(
    () => new Set(selectedEvent?.customer_ids ?? []),
    [selectedEvent],
  );
  const bounds = useMemo(() => {
    if (!points.length) return null;
    const xs = points.map(({ position }) => position[0]);
    const ys = points.map(({ position }) => position[1]);
    return {
      minX: Math.min(...xs),
      maxX: Math.max(...xs),
      minY: Math.min(...ys),
      maxY: Math.max(...ys),
    };
  }, [points]);
  const tiles = useMemo<BasemapTile[]>(() => {
    const { width, height } = dimensions;
    if (!bounds || !width || !height) return [];

    const padding = 34;
    const spanX = Math.max(bounds.maxX - bounds.minX, 0.00001);
    const spanY = Math.max(bounds.maxY - bounds.minY, 0.00001);
    const scale =
      Math.min((width - padding * 2) / spanX, (height - padding * 2) / spanY) *
      view.zoom;
    const centerX = (bounds.minX + bounds.maxX) / 2;
    const centerY = (bounds.minY + bounds.maxY) / 2;
    const zoom = Math.max(
      0,
      Math.min(MAX_TILE_ZOOM, Math.round(Math.log2(scale / TILE_SIZE))),
    );
    const tileCount = 2 ** zoom;
    const tileSize = scale / tileCount;
    const minTileX = Math.floor(
      (centerX + (-width / 2 - view.panX) / scale) * tileCount,
    );
    const maxTileX = Math.floor(
      (centerX + (width / 2 - view.panX) / scale) * tileCount,
    );
    const minTileY = Math.max(
      0,
      Math.floor((centerY + (-height / 2 - view.panY) / scale) * tileCount),
    );
    const maxTileY = Math.min(
      tileCount - 1,
      Math.floor((centerY + (height / 2 - view.panY) / scale) * tileCount),
    );
    const result: BasemapTile[] = [];

    for (let tileY = minTileY; tileY <= maxTileY; tileY += 1) {
      for (let tileX = minTileX; tileX <= maxTileX; tileX += 1) {
        const wrappedX = ((tileX % tileCount) + tileCount) % tileCount;
        result.push({
          key: `${zoom}/${tileX}/${tileY}`,
          url: OSM_TILE_URL.replace('{z}', String(zoom))
            .replace('{x}', String(wrappedX))
            .replace('{y}', String(tileY)),
          left:
            width / 2 +
            (tileX / tileCount - centerX) * scale +
            view.panX,
          top:
            height / 2 +
            (tileY / tileCount - centerY) * scale +
            view.panY,
          size: tileSize,
        });
      }
    }
    return result;
  }, [bounds, dimensions, view]);

  useEffect(() => {
    const visibleTileKeys = new Set(tiles.map(({ key }) => key));
    setFailedTileKeys((previous) => {
      const current = new Set([...previous].filter((key) => visibleTileKeys.has(key)));
      return current.size === previous.size ? previous : current;
    });
  }, [tiles]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;
    const observer = new ResizeObserver(([entry]) => {
      setDimensions({
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      });
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const handleWheel = (event: WheelEvent) => {
      event.preventDefault();
      setView((current) => ({
        ...current,
        zoom: Math.min(
          20,
          Math.max(1, current.zoom * (event.deltaY < 0 ? 1.2 : 1 / 1.2)),
        ),
      }));
    };
    canvas.addEventListener('wheel', handleWheel, { passive: false });
    return () => canvas.removeEventListener('wheel', handleWheel);
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext('2d');
    const { width, height } = dimensions;
    if (!canvas || !context || !bounds || !width || !height) return;

    const pixelRatio = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * pixelRatio);
    canvas.height = Math.round(height * pixelRatio);
    context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    context.clearRect(0, 0, width, height);
    const padding = 34;
    const spanX = Math.max(bounds.maxX - bounds.minX, 0.00001);
    const spanY = Math.max(bounds.maxY - bounds.minY, 0.00001);
    const baseScale = Math.min(
      (width - padding * 2) / spanX,
      (height - padding * 2) / spanY,
    );
    const scale = baseScale * view.zoom;
    const centerX = (bounds.minX + bounds.maxX) / 2;
    const centerY = (bounds.minY + bounds.maxY) / 2;
    const toScreen = (x: number, y: number): [number, number] => [
      width / 2 + (x - centerX) * scale + view.panX,
      height / 2 + (y - centerY) * scale + view.panY,
    ];

    context.strokeStyle = 'rgba(255,255,255,0.42)';
    context.lineWidth = 1;
    for (let fraction = 0.2; fraction < 1; fraction += 0.2) {
      const x = width * fraction;
      const y = height * fraction;
      context.beginPath();
      context.moveTo(x, 0);
      context.lineTo(x, height);
      context.moveTo(0, y);
      context.lineTo(width, y);
      context.stroke();
    }

    events.forEach((event) => {
      const color = COLORS[event.event_scope];
      const clusters: Array<Pick<
        AnomalySpatialCluster,
        'latitude_center' | 'longitude_center' | 'spatial_extent_km'
      >> = event.spatial_clusters?.length
        ? event.spatial_clusters
        : [event];
      clusters.forEach((cluster) => {
        const center = project(cluster.latitude_center, cluster.longitude_center);
        const [x, y] = toScreen(center[0], center[1]);
        const radius = eventRadiusPixels(cluster, scale);
        context.beginPath();
        context.arc(x, y, radius, 0, 2 * Math.PI);
        context.fillStyle = `${color}20`;
        context.fill();
        context.setLineDash([5, 4]);
        context.lineWidth = event.event_id === selectedEventId ? 2.5 : 1.25;
        context.strokeStyle = color;
        context.stroke();
        context.setLineDash([]);
      });
    });

    [false, true].forEach((selectedPass) => {
      points.forEach(({ entity, position }) => {
        const isSelectedEventCustomer = selectedEventCustomers.has(entity.OBJECTID);
        if (isSelectedEventCustomer !== selectedPass) return;
        const [x, y] = toScreen(position[0], position[1]);
        if (x < -5 || x > width + 5 || y < -5 || y > height + 5) return;
        const event = eventCustomers.get(entity.OBJECTID);
        const color = isSelectedEventCustomer
          ? COLORS[selectedEventScope ?? event?.event_scope ?? 'SINGLE_CUSTOMER']
          : event ? COLORS[event.event_scope] : '#7C8B99';
        context.beginPath();
        context.arc(x, y, isSelectedEventCustomer ? 5 : event ? 3.2 : 1.8, 0, 2 * Math.PI);
        context.fillStyle = color;
        context.fill();
        if (event || isSelectedEventCustomer) {
          context.lineWidth = isSelectedEventCustomer ? 1.5 : 0.8;
          context.strokeStyle = '#FFFFFF';
          context.stroke();
        }
      });
    });

    context.fillStyle = '#52616B';
    context.font = '11px system-ui, sans-serif';
    context.fillText('Longitude →', width - 94, height - 10);
    context.save();
    context.translate(14, 78);
    context.rotate(-Math.PI / 2);
    context.fillText('Latitude →', 0, 0);
    context.restore();
  }, [bounds, dimensions, eventCustomers, events, points, selectedEventCustomers, selectedEventId, selectedEventScope, view]);

  const eventAt = (x: number, y: number): AnomalyEvent | undefined => {
    const canvas = canvasRef.current;
    const { width, height } = dimensions;
    if (!canvas || !bounds || !width || !height) return undefined;
    const padding = 34;
    const spanX = Math.max(bounds.maxX - bounds.minX, 0.00001);
    const spanY = Math.max(bounds.maxY - bounds.minY, 0.00001);
    const scale =
      Math.min((width - padding * 2) / spanX, (height - padding * 2) / spanY) *
      view.zoom;
    const centerX = (bounds.minX + bounds.maxX) / 2;
    const centerY = (bounds.minY + bounds.maxY) / 2;
    const toScreen = (position: [number, number]): [number, number] => [
      width / 2 + (position[0] - centerX) * scale + view.panX,
      height / 2 + (position[1] - centerY) * scale + view.panY,
    ];
    let closestPoint: { event: AnomalyEvent; distance: number } | undefined;
    for (const { entity, position } of points) {
      const event = eventCustomers.get(entity.OBJECTID);
      if (!event) continue;
      const [pointX, pointY] = toScreen(position);
      const distance = Math.hypot(pointX - x, pointY - y);
      if (distance <= 9 && (!closestPoint || distance < closestPoint.distance)) {
        closestPoint = { event, distance };
      }
    }
    if (closestPoint) return closestPoint.event;
    let closestBoundary: { event: AnomalyEvent; distance: number } | undefined;
    for (const event of events) {
      const clusters: Array<Pick<
        AnomalySpatialCluster,
        'latitude_center' | 'longitude_center' | 'spatial_extent_km'
      >> = event.spatial_clusters?.length
        ? event.spatial_clusters
        : [event];
      clusters.forEach((cluster) => {
        const [eventX, eventY] = toScreen(
          project(cluster.latitude_center, cluster.longitude_center),
        );
        const distance = Math.hypot(eventX - x, eventY - y);
        const boundaryRadius = eventRadiusPixels(cluster, scale);
        const boundaryDistance = Math.abs(distance - boundaryRadius);
        if (
          boundaryDistance <= 7 &&
          (!closestBoundary || boundaryDistance < closestBoundary.distance)
        ) {
          closestBoundary = { event, distance: boundaryDistance };
        }
      });
    }
    return closestBoundary?.event;
  };

  return (
    <div>
      <div
        ref={containerRef}
        style={{
          position: 'relative',
          width: '100%',
          height: 'clamp(280px, 42vw, 430px)',
          minHeight: 280,
          overflow: 'hidden',
          border: '1px solid var(--gv-border-subtle)',
          borderRadius: 'var(--gv-radius-md)',
          background: '#F3F7F8',
        }}
      >
        <div
          aria-hidden="true"
          style={{ position: 'absolute', inset: 0, overflow: 'hidden', zIndex: 0 }}
        >
          {tiles.map((tile) => (
            <img
              key={tile.key}
              src={tile.url}
              alt=""
              draggable={false}
              onError={() =>
                setFailedTileKeys((previous) => new Set(previous).add(tile.key))
              }
              style={{
                position: 'absolute',
                left: tile.left,
                top: tile.top,
                width: tile.size,
                height: tile.size,
                maxWidth: 'none',
                userSelect: 'none',
              }}
            />
          ))}
        </div>
        <canvas
          ref={canvasRef}
          aria-label={`Geographic customer distribution with ${points.length} customer locations; ${eventCustomers.size} affected customers`}
          role="img"
          onPointerDown={(pointerEvent) => {
            dragRef.current = {
              pointerId: pointerEvent.pointerId,
              x: pointerEvent.clientX,
              y: pointerEvent.clientY,
              moved: false,
            };
            pointerEvent.currentTarget.setPointerCapture(pointerEvent.pointerId);
          }}
          onPointerMove={(pointerEvent) => {
            const drag = dragRef.current;
            if (!drag || drag.pointerId !== pointerEvent.pointerId) return;
            const deltaX = pointerEvent.clientX - drag.x;
            const deltaY = pointerEvent.clientY - drag.y;
            if (Math.abs(deltaX) + Math.abs(deltaY) > 2) drag.moved = true;
            if (drag.moved) {
              setView((current) => ({
                ...current,
                panX: current.panX + deltaX,
                panY: current.panY + deltaY,
              }));
              drag.x = pointerEvent.clientX;
              drag.y = pointerEvent.clientY;
            }
          }}
          onPointerUp={(pointerEvent) => {
            const drag = dragRef.current;
            if (drag && !drag.moved) {
              const rect = pointerEvent.currentTarget.getBoundingClientRect();
              const event = eventAt(
                pointerEvent.clientX - rect.left,
                pointerEvent.clientY - rect.top,
              );
              if (event) onSelectEvent(event.event_id);
            }
            dragRef.current = null;
          }}
          onPointerCancel={() => {
            dragRef.current = null;
          }}
          style={{
            display: 'block',
            position: 'absolute',
            inset: 0,
            zIndex: 1,
            width: '100%',
            height: '100%',
            cursor: dragRef.current?.moved ? 'grabbing' : 'grab',
            touchAction: 'none',
          }}
        />
        <div
          style={{
            position: 'absolute',
            zIndex: 2,
            top: 10,
            right: 10,
            display: 'flex',
            gap: 4,
            padding: 4,
            borderRadius: 6,
            background: 'rgba(255,255,255,0.94)',
            boxShadow: '0 1px 5px #0002',
          }}
        >
          <button type="button" aria-label="Zoom in" onClick={() => setView((current) => ({ ...current, zoom: Math.min(20, current.zoom * 1.25) }))}>+</button>
          <button type="button" aria-label="Zoom out" onClick={() => setView((current) => ({ ...current, zoom: Math.max(1, current.zoom / 1.25) }))}>−</button>
          <button type="button" onClick={() => setView({ zoom: 1, panX: 0, panY: 0 })}>Reset view</button>
        </div>
        {!points.length && (
          <div
            role="status"
            style={{ position: 'absolute', inset: '45% 1rem auto', textAlign: 'center' }}
          >
            Customer coordinates are unavailable for this dataset.
          </div>
        )}
        {tiles.length > 0 && failedTileKeys.size === tiles.length && (
          <div
            role="status"
            style={{
              position: 'absolute',
              zIndex: 2,
              left: 10,
              bottom: 10,
              maxWidth: '75%',
              padding: '6px 9px',
              borderRadius: 5,
              background: 'rgba(255,255,255,0.94)',
              color: '#52616B',
              fontSize: '0.72rem',
            }}
          >
            OpenStreetMap tiles could not be loaded. Customer locations and event
            overlays remain available without the basemap.
          </div>
        )}
        <a
          href="https://www.openstreetmap.org/copyright"
          target="_blank"
          rel="noreferrer"
          aria-label="OpenStreetMap copyright and attribution"
          style={{
            position: 'absolute',
            zIndex: 3,
            right: 7,
            bottom: 5,
            padding: '2px 5px',
            borderRadius: 3,
            background: 'rgba(255,255,255,0.88)',
            color: '#52616B',
            fontSize: '0.65rem',
            textDecoration: 'none',
          }}
        >
          © OpenStreetMap contributors
        </a>
      </div>
      <p className="gv-text-subtle" style={{ margin: '0.55rem 0 0', fontSize: '0.75rem' }}>
        Showing all {points.length.toLocaleString()} customer coordinates in Web Mercator
        projection over OpenStreetMap. Dashed circles show estimated impact extent for each
        spatial cluster, while affected customers are highlighted individually. Drag to pan,
        scroll to zoom, or select a marker/boundary to inspect its event.
      </p>
    </div>
  );
};
