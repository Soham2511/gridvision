import { useContext } from 'react';
import { PersonaContext, PersonaContextValue } from './PersonaContextDef';

export const usePersona = (): PersonaContextValue => {
  const context = useContext(PersonaContext);
  if (!context) {
    throw new Error('usePersona must be used within a PersonaProvider');
  }
  return context;
};
