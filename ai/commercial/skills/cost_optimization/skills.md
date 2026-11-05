# Cost Optimization Skill

## Purpose
Use the cost-optimization specialist only for explicit schedule, dispatch, or
energy-cost optimization requests.

## Select this skill when
- The user explicitly asks to optimize, schedule, reschedule, dispatch, or
  minimize energy cost, including a clear follow-up to such a request.

## Constraints
- Use only the registered `cost_optimizer` capability.
- Require complete, validated schedule inputs; never invent jobs, tariffs,
  machine constraints, baselines, or battery parameters.
- Report feasibility and calculated cost accurately. Do not claim savings
  without a supplied baseline.
- A proposed schedule is not an equipment command and requires approval before
  use.
