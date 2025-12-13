# /next-feature

Start working on the next available feature from the Ijoka graph database.

## What This Command Does

1. Queries Memgraph for the next pending feature (highest priority, unblocked)
2. Calls `ijoka_start_feature` to set it as active
3. Displays the feature details and any defined steps
4. Optionally sets up a plan with `ijoka_set_plan`

## Usage

Run `/next-feature` to automatically pick up the next task.

Optionally specify a category: `/next-feature security`

## Example

User: `/next-feature`

Claude will:
1. Call `ijoka_status` to see available features
2. Find next pending feature (highest priority)
3. Call `ijoka_start_feature` to activate it
4. Display the feature details
5. Ask if you want to create a step plan

## Priority Order

When no category is specified, features are selected by:
1. **Priority value** - Higher numbers first (100, 90, 80...)
2. **Creation order** - Earlier created features first (tie-breaker)

When category specified:
- Filter to only that category
- Then apply priority ordering

## Instructions for Claude

When the user runs this command:

1. **Get current status** - Call `ijoka_status`
   - Check if there's already an active feature
   - If yes, ask: "You have an active feature. Complete it first or switch?"

2. **Find next feature** - From the status response:
   - Filter to `status: pending` features
   - If category specified (in $ARGUMENTS), filter by category
   - Select highest priority unblocked feature
   - If no features available, suggest `/add-feature`

3. **Start the feature** - Call `ijoka_start_feature` with the feature_id

4. **Display feature info**:
   ```
   ## Starting Feature

   **Description:** [description]
   **Category:** [category]
   **Priority:** [priority]

   ### Verification Steps
   1. [step 1]
   2. [step 2]
   ...
   ```

5. **Offer to create plan** - Ask if they want to set up a detailed plan:
   - If yes, help define steps and call `ijoka_set_plan`
   - If no, proceed with implementation

6. **Begin work** - Start implementing the feature

## Important Rules

- Only work on ONE feature at a time
- Complete each step before moving on
- Test thoroughly before marking as complete
- Use `ijoka_checkpoint` to report progress
- Use `/complete-feature` when done
