import React from 'react';
import { AuthProvider, PersonaProvider } from './context';
import { AppRoutes } from './routes/AppRoutes';

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <PersonaProvider>
        <AppRoutes />
      </PersonaProvider>
    </AuthProvider>
  );
};

export default App;
