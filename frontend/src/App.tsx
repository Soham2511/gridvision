import React from 'react';
import { PersonaProvider } from './context';
import { AppRoutes } from './routes/AppRoutes';

export const App: React.FC = () => {
  return (
    <PersonaProvider>
      <AppRoutes />
    </PersonaProvider>
  );
};

export default App;
