---
id: task-5
priority: low
status: pending
dependencies: [task-4]
labels: [testing, e2e]
---

# Test: End-to-end session continuity

## Objective

Manually test the complete cross-session continuity workflow.

## Test Workflow

**Session 1:**
1. Start Claude Code session
2. Create a test feature via ijoka_create_feature
3. Make a git commit
4. End session

**Session 2:**
1. Start new session in same project
2. Verify context shows:
   - Previous session summary
   - Commit from Session 1
   - Step progress (if any)

## Validation Queries

```cypher
-- Check session ancestry
MATCH (s2:Session)-[:CONTINUED_FROM]->(s1:Session)
RETURN s1.id, s2.id

-- Check commits linked
MATCH (s:Session)-[:MADE_COMMITS]->(c:Commit)
RETURN s.id, c.hash, c.message

-- Full lineage
MATCH (s2)-[:CONTINUED_FROM]->(s1)
OPTIONAL MATCH (s1)-[:MADE_COMMITS]->(c)
RETURN s1.id, s2.id, c.hash
```

## Acceptance Criteria

- [ ] CONTINUED_FROM relationship created
- [ ] Commit node exists with correct data
- [ ] MADE_COMMITS and IMPLEMENTED_IN relationships correct
- [ ] SessionStart context displays correctly
