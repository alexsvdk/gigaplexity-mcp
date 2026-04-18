---
name: gigaplexity-research-verification
description: "High-rigor research and fact-verification skill using Gigaplexity tools. MUST use when the task requires external facts, comparisons, due diligence, trend analysis, or any answer where confidence and citations matter."
argument-hint: "Research question, scope, constraints, and required depth"
---

# Gigaplexity Research & Verification Skill

## Purpose
Use this skill to produce **trustworthy, citation-backed, decision-ready** answers.
This skill is optimized for external information research, verification, and synthesis with clear uncertainty handling.

## MUST Use When
Use this skill **by default** when at least one condition is true:
- User asks for **research**, **analysis**, **comparison**, **fact-checking**, or **market/tech landscape**.
- Request depends on **current or external information** not guaranteed to be in workspace.
- Output will influence a **decision** (product, architecture, hiring, vendor, strategy).
- User explicitly asks for **sources**, **citations**, or “проверь информацию”.
- There is a risk of hallucination or high cost of being wrong.

## Do NOT Use As Primary Workflow When
- Task is pure local refactoring/debugging with no external facts.
- User asks for simple brainstorming with no requirement for factual accuracy.

## Tooling Strategy (Gigaplexity-first)
1. Start with `#tool:gigaplexity/ask` for fast orientation.
2. Use `#tool:gigaplexity/research` for multi-step deep coverage.
3. Use `#tool:gigaplexity/reason` to resolve contradictions and edge cases.
4. If evidence is thin or conflicting, expand with web tools.

## Research Quality Protocol

### 1) Scope & Success Criteria
- Restate objective, audience, and decision context.
- Define “done”: what exactly must be answered.
- Capture constraints: timeline, geography, industry, versions, budget/risk.

### 2) Evidence Collection
- Gather sources from **multiple independent domains**.
- Prefer primary/original sources (official docs, standards, papers, filings, vendor docs).
- Use secondary sources only to complement, never as single point of truth.

### 3) Verification & Triangulation
- Validate each key claim with at least 2 independent sources when possible.
- Mark unresolved conflicts explicitly and explain why.
- Separate **facts** from **interpretation**.

### 4) Source Quality Scoring (required for important claims)
For each critical claim, quickly score source quality:
- Authority (official/recognized?)
- Freshness (date and version relevance?)
- Specificity (direct evidence vs vague summary?)
- Independence (not circularly citing same origin?)
- Reproducibility (can reader verify?)

### 5) Uncertainty Handling
- Always include a short “Confidence” note.
- Use labels: High / Medium / Low confidence.
- Explain uncertainty drivers (missing data, conflicting reports, outdated docs).

### 6) Synthesis
- Build answer top-down: executive summary → findings → implications → recommendation.
- Keep claims compact and link each to evidence.
- Avoid citation dumping; cite only what supports a concrete statement.

## Language Policy
- Respond in the user’s language.
- Search in the language most likely to maximize evidence quality:
  - Global tech/business topics: English.
  - Local policy/legal/regional topics: local language + English cross-check.

## Output Contract (default)
Return in this structure:

1. **Executive Summary** (2–5 sentences)
2. **Findings** (grouped by theme)
3. **Conflicts & Uncertainty** (if any)
4. **Recommendation / Next Step**
5. **Sources** (clean list with links)

## Citation Discipline
- Every non-trivial factual claim should be attributable.
- Prefer inline citations near claims.
- If a source is weak, say so.
- Never fabricate a source or URL.

## Anti-Patterns (strictly avoid)
- Confident answer without evidence.
- One-source conclusions for high-impact decisions.
- Mixing assumptions and facts without labeling.
- Presenting stale information as current.

## Fast Invocation Template
Use this template when launching research:

"Research objective: <goal>. 
Context: <project/user constraints>. 
Need: <facts/comparison/verification>. 
Depth: quick | standard | deep. 
Output: executive summary, findings with citations, uncertainty note, recommendation."

## Completion Checklist
- [ ] Scope and constraints are explicit
- [ ] Key claims are source-backed
- [ ] Conflicts resolved or clearly flagged
- [ ] Confidence level provided
- [ ] Final recommendation is actionable
