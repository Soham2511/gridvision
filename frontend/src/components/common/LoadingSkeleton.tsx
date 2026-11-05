import React from 'react';

interface LoadingSkeletonProps {
  height?: string;
  width?: string;
  count?: number;
}

export const LoadingSkeleton: React.FC<LoadingSkeletonProps> = ({
  height = '20px',
  width = '100%',
  count = 1,
}) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', width: '100%' }}>
      {Array.from({ length: count }).map((_, index) => (
        <div
          key={index}
          style={{
            height,
            width,
            borderRadius: 'var(--gv-radius-md)',
            background: 'linear-gradient(90deg, #F1F5F9 25%, #E2E8F0 50%, #F1F5F9 75%)',
            backgroundSize: '200% 100%',
            animation: 'skeleton-shimmer 1.5s infinite',
          }}
        />
      ))}
      <style>{`
        @keyframes skeleton-shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
      `}</style>
    </div>
  );
};
