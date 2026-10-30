import React from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopHeader } from './TopHeader';

export const MainLayout: React.FC = () => {
  return (
    <div style={{ display: 'flex', minHeight: '100vh', width: '100%', backgroundColor: 'var(--gv-bg-app)' }}>
      {/* Persistent Left Sidebar */}
      <Sidebar />

      {/* Main App Container */}
      <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minWidth: 0, overflow: 'hidden' }}>
        <TopHeader />

        <main
          style={{
            flex: 1,
            overflowY: 'auto',
            paddingBottom: '2.5rem',
          }}
        >
          <div className="gv-container">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
};
