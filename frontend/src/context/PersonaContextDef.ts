import { createContext } from 'react';

export type PersonaType = 'household' | 'commercial' | 'government';
export type EnergyUnit = 'kWh' | 'MWh';

export interface NotificationPreferences {
  demandAlerts: boolean;
  reportNotifications: boolean;
  systemUpdates: boolean;
  insightsTips: boolean;
}

export interface PersonaContextValue {
  currentPersona: PersonaType | null;
  activeEntity: string;
  energyUnit: EnergyUnit;
  notificationPreferences: NotificationPreferences;
  setPersona: (persona: PersonaType | null) => void;
  setActiveEntity: (entity: string) => void;
  setEnergyUnit: (unit: EnergyUnit) => void;
  setNotificationPreferences: (
    prefs: NotificationPreferences | ((prev: NotificationPreferences) => NotificationPreferences)
  ) => void;
}

export const PersonaContext = createContext<PersonaContextValue | undefined>(undefined);
