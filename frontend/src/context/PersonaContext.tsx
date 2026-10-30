import React, { useState, useEffect } from 'react';
import {
  PersonaContext,
  PersonaType,
  EnergyUnit,
  NotificationPreferences,
} from './PersonaContextDef';

const DEFAULT_ENTITIES: Record<PersonaType, string> = {
  household: 'METER-1000',
  commercial: 'Panther_office_1',
  government: 'Bear & Aggregate',
};

const DEFAULT_NOTIFICATIONS: NotificationPreferences = {
  demandAlerts: true,
  reportNotifications: true,
  systemUpdates: false,
  insightsTips: true,
};

export const PersonaProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [currentPersona, setCurrentPersonaState] = useState<PersonaType | null>(() => {
    const saved = localStorage.getItem('gv_current_persona');
    if (saved === 'household' || saved === 'commercial' || saved === 'government') {
      return saved;
    }
    return null;
  });

  const [activeEntity, setActiveEntityState] = useState<string>(() => {
    if (currentPersona) {
      return localStorage.getItem(`gv_active_entity_${currentPersona}`) || DEFAULT_ENTITIES[currentPersona];
    }
    return 'METER-1000';
  });

  const [energyUnit, setEnergyUnitState] = useState<EnergyUnit>(() => {
    const saved = localStorage.getItem('gv_energy_unit');
    if (saved === 'kWh' || saved === 'MWh') {
      return saved;
    }
    return 'kWh';
  });

  const [notificationPreferences, setNotificationPreferencesState] = useState<NotificationPreferences>(() => {
    try {
      const saved = localStorage.getItem('gv_notification_prefs');
      if (saved) {
        return { ...DEFAULT_NOTIFICATIONS, ...JSON.parse(saved) };
      }
    } catch {
      // Fallback to defaults if parsing fails
    }
    return DEFAULT_NOTIFICATIONS;
  });

  const setPersona = (persona: PersonaType | null) => {
    setCurrentPersonaState(persona);
    if (persona) {
      localStorage.setItem('gv_current_persona', persona);
      const savedEntity = localStorage.getItem(`gv_active_entity_${persona}`) || DEFAULT_ENTITIES[persona];
      setActiveEntityState(savedEntity);
    } else {
      localStorage.removeItem('gv_current_persona');
    }
  };

  const setActiveEntity = (entity: string) => {
    setActiveEntityState(entity);
    if (currentPersona) {
      localStorage.setItem(`gv_active_entity_${currentPersona}`, entity);
    }
  };

  const setEnergyUnit = (unit: EnergyUnit) => {
    setEnergyUnitState(unit);
    localStorage.setItem('gv_energy_unit', unit);
  };

  const setNotificationPreferences = (
    prefs: NotificationPreferences | ((prev: NotificationPreferences) => NotificationPreferences)
  ) => {
    setNotificationPreferencesState((prev) => {
      const updated = typeof prefs === 'function' ? prefs(prev) : prefs;
      localStorage.setItem('gv_notification_prefs', JSON.stringify(updated));
      return updated;
    });
  };

  useEffect(() => {
    if (currentPersona) {
      const savedEntity = localStorage.getItem(`gv_active_entity_${currentPersona}`) || DEFAULT_ENTITIES[currentPersona];
      setActiveEntityState(savedEntity);
    }
  }, [currentPersona]);

  return (
    <PersonaContext.Provider
      value={{
        currentPersona,
        activeEntity,
        energyUnit,
        notificationPreferences,
        setPersona,
        setActiveEntity,
        setEnergyUnit,
        setNotificationPreferences,
      }}
    >
      {children}
    </PersonaContext.Provider>
  );
};
