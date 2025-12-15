# /spike

Create a time-boxed investigation or research task.

## Usage

```
/spike <description>
```

## What This Does

Creates a spike (research/investigation) work item. Spikes are for:
- Investigating unknowns before implementation
- Researching libraries, tools, or approaches
- Understanding unfamiliar code or systems
- Prototyping solutions

Spikes are categorized as "planning" with priority 40 (medium-low) since they're exploratory.

## Behavior

1. Create spike: `ijoka feature create planning "<description>" --type spike --priority 40`
2. Optionally link to active feature if investigating for it
3. Output: Spike ID with reminder to document findings

## Instructions

Run these commands to create a spike:

```bash
# 1. Get current active feature (optional parent)
ACTIVE=$(curl -s http://localhost:8000/features/active | jq -r '.features[0].id // empty')

# 2. Create the spike
SPIKE_RESPONSE=$(ijoka feature create planning "$ARGUMENTS" --type spike --priority 40 --json)
SPIKE_ID=$(echo "$SPIKE_RESPONSE" | jq -r '.feature.id')

# 3. Optionally link to active feature
if [ -n "$ACTIVE" ]; then
  curl -s -X POST "http://localhost:8000/features/$SPIKE_ID/link/$ACTIVE"
  echo "Spike $SPIKE_ID created and linked to feature $ACTIVE"
else
  echo "Spike $SPIKE_ID created (standalone investigation)"
fi

echo ""
echo "Remember to document your findings before completing this spike!"
```

## Example

```
/spike Investigate WebSocket vs SSE for real-time updates
```

Creates a spike to research the trade-offs between WebSocket and SSE.

## When to Use

- When you don't know how to approach a problem
- When you need to evaluate multiple options
- When working with unfamiliar technology
- When requirements are unclear and need investigation
- When you encounter "I need to research this first" situations

## Completing a Spike

When done investigating, complete the spike with findings:

```bash
# Mark spike complete with a summary of findings
ijoka feature complete --note "Findings: SSE is simpler but WebSocket supports bidirectional. Recommend SSE for our use case."
```

The findings will be attached to the spike for future reference.
