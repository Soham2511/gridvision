# Renewable Skill

## Purpose
Use the renewable specialist for solar, wind, battery, and renewable-energy
scenario questions.

## Select this skill when
- The request asks about renewable sizing, generation, costs, payback,
  renewable integration, or battery scenarios.
- Renewable context is needed to interpret a short follow-up in the recent
  conversation.

## Constraints
- Use only the registered `renewable_scenario_read` capability.
- Do not infer system size, roof area, consumption, tariff, CAPEX, wind capacity,
  or battery parameters that the user has not supplied.
- Distinguish calculations from live research and cite research when returned.
- Mark illustrative assumptions and unavailable inputs clearly; do not present
  estimates as quotes or guaranteed savings.
