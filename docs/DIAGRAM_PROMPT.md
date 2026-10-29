# Architecture diagram prompt (Google Gemini image generation)

Paste the block below into Gemini in one go. If the result is cluttered, send the refinement prompts afterwards. A Mermaid fallback is at the end.

```text
Create a clean architectural flowchart diagram.

VISUAL STYLE: white or very light grey background, flat vector look, rounded rectangles, one consistent muted palette: navy for orchestration, teal for agents, amber for human approval, grey for data and governance, purple for MLflow and observability. Thin directional arrows, readable labels, generous spacing, landscape 16:9. No photographic elements, no decorative clip art, no icons of people, no shadows or gradients. Spell all text exactly as given below.

TITLE (top, left aligned): "Multi-agent claims automation on Databricks: LangGraph + MLflow + Unity Catalog"

LAYOUT, left to right:
1. Small white box with navy outline: "User request". Arrow to:
2. Navy rounded rectangle: "Supervisor / router". Arrows fan out to a column of five teal rounded rectangles (the specialist agents), stacked vertically, top to bottom:
   - "SQL analyst"
   - "Policy RAG"
   - "Coverage checker"
   - "Fraud / SIU screener"
   - "Underwriting risk with reason codes"
3. Arrows from all five agents converge into one navy rounded rectangle: "Writer".
4. Arrow to a navy rounded rectangle: "Critic". From Critic, a curved loop-back arrow returns to the agent column, labelled "fail: retry max 2".
5. Arrow from Critic to a prominent AMBER rounded rectangle: "Approval gate" with the sub-label "Claims authority matrix: auto / adjuster / senior adjuster / manager / SIU".
6. Arrow from the Approval gate to a white box with navy outline: "Final answer + audit record".

GREY BAND (below the agent column, spanning under the agents): titled "Unity Catalog", containing four short items in a row: "Curated tables (applicants, policies, claims, policy_docs)", "PII column masks", "UC functions (Managed MCP)", "Risk model registry (champion alias)". Thin dotted lines connect the band up to the agents that use it.

PURPLE BAND (across the full bottom of the diagram): titled "MLflow", containing four items in a row: "Tracing per node", "Prompt registry", "Evaluation (6 layers) and release gate", "Cost ledger".

FAR RIGHT: a small grey rounded box: "Model Serving endpoint (scale-to-zero)", with a thin dotted line to the Supervisor / router group indicating that the whole graph is served from it.

LEGEND (bottom right, small): colour swatches with labels: navy "Orchestration", teal "Agents", amber "Human approval", grey "Data and governance", purple "MLflow / observability".

Keep arrows thin and avoid crossings where possible. Do not add any text that is not listed above.
```

## Refinement prompts (send after the first result)

1. Reduce the text size and increase spacing between all boxes. Keep every label exactly as written, and make sure nothing overlaps or is cut off.
2. Make all arrows orthogonal (right angles only), avoid arrow crossings, and route the "fail: retry max 2" loop-back arrow above the diagram so it does not cross the agent column.
3. Render the amber "Approval gate" as the most visually prominent element: larger, thicker outline, with the authority matrix text clearly readable. Keep everything else in muted tones.

## Mermaid fallback

```mermaid
flowchart LR
    U[User request] --> S[Supervisor / router]
    S --> A1[SQL analyst]
    S --> A2[Policy RAG]
    S --> A3[Coverage checker]
    S --> A4[Fraud / SIU screener]
    S --> A5[Underwriting risk with reason codes]
    A1 --> W[Writer]
    A2 --> W
    A3 --> W
    A4 --> W
    A5 --> W
    W --> C[Critic]
    C -. "fail: retry max 2" .-> S
    C --> G{{"Approval gate<br/>Claims authority matrix:<br/>auto / adjuster / senior adjuster / manager / SIU"}}
    G --> O[Final answer + audit record]

    subgraph UC[Unity Catalog]
        T[Curated tables: applicants, policies, claims, policy_docs]
        M[PII column masks]
        F[UC functions - Managed MCP]
        R[Risk model registry - champion alias]
    end
    A1 -.-> T
    A2 -.-> T
    A3 -.-> T
    A4 -.-> T
    A5 -.-> R
    T --- M

    subgraph ML[MLflow]
        TR[Tracing per node]
        PR[Prompt registry]
        EV[Evaluation and release gate]
        CL[Cost ledger]
    end
    W -.-> TR

    SRV[Model Serving endpoint, scale-to-zero] -.-> S

    classDef orch fill:#1f3a5f,color:#fff,stroke:#1f3a5f;
    classDef agent fill:#2a9d8f,color:#fff,stroke:#2a9d8f;
    classDef human fill:#f0b429,color:#000,stroke:#b8860b;
    classDef data fill:#d9dde2,color:#000,stroke:#8a929b;
    classDef obs fill:#7b5ea7,color:#fff,stroke:#7b5ea7;
    class S,W,C orch;
    class A1,A2,A3,A4,A5 agent;
    class G human;
    class T,M,F,R,SRV data;
    class TR,PR,EV,CL obs;
```
