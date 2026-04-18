---
name: gigaplexity-file-intelligence
description: "File intelligence skill for understanding documents, images, and audio through Gigaplexity `ask` attachments. MUST use when user asks to analyze/compare/summarize local files (PDF, DOC, image, audio, code/text) with evidence-aware outputs."
argument-hint: "Goal + absolute file paths + expected output format"
---

# Gigaplexity File Intelligence Skill

## Purpose
Use this skill to extract reliable insights from user files (docs/images/audio), then produce concise, structured outputs aligned with the task (summary, Q&A, comparison, due diligence, extraction).

## MUST Use When
Use this skill **immediately** if user intent includes any of these:
- “прочитай/разбери файл”, “что в этом PDF/DOC?”, “проанализируй картинку/аудио”.
- Need to summarize or compare **attached/local files**.
- Need factual extraction from file content (entities, dates, obligations, risks, action items).
- Need multimodal understanding (document + image, or image-only, audio-only).

## Core Capability Constraint (critical)
Gigaplexity `ask` supports attachments, but **all files in one request must be from the same category**:
- Document/text/code files
- Images
- Audio

If user gives mixed categories, split into multiple passes and then synthesize.

## Workflow

### 1) Input Validation
- Ensure file paths are absolute and files exist.
- Determine category for each file.
- If categories mixed: batch by category and process separately.

### 2) Intent Clarification (if needed)
Ask minimal clarifying questions only when output target is ambiguous:
- summary vs extraction vs comparison vs risk review
- desired language and level (brief / detailed)

### 3) File Analysis via Gigaplexity
- Use `#tool:gigaplexity/ask` with `file_paths`.
- Provide a precise task prompt (what to extract, what to ignore, desired format).
- For large/complex files, run iterative passes:
  - pass A: global summary
  - pass B: targeted extraction
  - pass C: contradiction/risk scan

### 4) Verification Pass
- For high-stakes tasks (legal/finance/security), request explicit evidence snippets from file content.
- If content is unclear, state uncertainty and what additional file/context is needed.

### 5) Synthesis
- Merge per-file or per-batch findings.
- Highlight agreements, conflicts, missing info, and next actions.

## Prompt Patterns (ready to use)

### A) Document Summary
"Analyze attached document(s). Return:
1) 5-bullet executive summary,
2) key entities/dates/amounts,
3) obligations and risks,
4) open questions.
Do not invent missing facts."

### B) Image Analysis
"Describe attached image(s) in detail, then extract actionable facts relevant to: <goal>. Distinguish observable facts from assumptions."

### C) Audio Analysis
"Transcribe and summarize attached audio. Return speakers (if inferable), key points, decisions, action items, timestamps when possible, and uncertainty notes."

### D) Multi-file Comparison (same category)
"Compare attached files and return: common points, differences, contradictions, and recommendation."

## Output Contract (default)
1. **What was analyzed** (files/categories)
2. **Executive Summary**
3. **Extracted Facts** (structured)
4. **Risks / Contradictions / Gaps**
5. **Next Actions**

## Quality Rules
- Never claim a file says something unless model output supports it.
- Separate observed content from inferred interpretation.
- Keep outputs decision-friendly: short, structured, and actionable.
- If source quality is insufficient, explicitly say what is missing.

## Anti-Patterns (strictly avoid)
- Mixing file categories in one `ask` call.
- Vague “looks good” summaries without concrete extracted facts.
- Ignoring ambiguities in OCR/audio or low-quality images.
- Overconfident conclusions in high-risk contexts.

## Completion Checklist
- [ ] File category rule respected (single category per request)
- [ ] Output matches requested task type
- [ ] Facts and uncertainties clearly separated
- [ ] Contradictions/gaps explicitly listed
- [ ] Recommendation or next steps provided
