# Claude Setup Prompt for Scanner

Copy and paste the following prompt into Claude to set up your scanner mission.

---

I want to set up "scanner", an automated opportunity discovery engine. Your goal is to generate a `mission.yaml` file based on my natural language description of who I am and what I am looking for.

### 1. My Mission
[INSERT YOUR MISSION HERE - e.g., "I am a PhD student in AI looking for research internships, hackathons with compute credits, and funding for my startup."]

### 2. Instructions for Claude
Based on my mission above, please generate a complete `mission.yaml` file. Follow these rules:

1.  **Profile**: Extract my name, role, location, and background.
2.  **Alignment**: Create 2-3 alignment sections (e.g., "Core Mission", "Current Project") that summarize my goals.
3.  **Preferences**:
    *   Set `locations` based on my preference (default to "Remote" if not specified).
    *   Set `categories` (event, funding, research, internship).
    *   **Crucial**: Generate 15-20 specific `search_queries` for Tavily. Use keywords like "2026", "application open", "credits", and specific tech stacks mentioned.
4.  **Eligibility**:
    *   **Rules**: Write 3-5 natural language rejection rules (e.g., "Reject if undergrad-only", "Reject if requires US residency").
    *   **Hard Reject Patterns**: Write 3-5 regex patterns for fast-path rejection (e.g., `undergrad(uate)? (only|students only)`).
5.  **Email**: Use placeholder `you@example.com` for `to`.

### 3. Output Format
Return ONLY the YAML block. No prose.

---

**After Claude generates the YAML:**
1. Save it as `mission.yaml` in the scanner root directory.
2. Run `python -m scanner run` to start scanning.
