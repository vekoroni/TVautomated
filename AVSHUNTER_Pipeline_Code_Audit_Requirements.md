**AUDIT REQUIREMENTS SPECIFICATION**

*Systematic Pipeline Code Audit --- Finding the Next "Phase C Problem"
Before It Costs Money*

  ----------------- -----------------------------------------------------
  **Document        AVSHUNTER Pipeline --- Systematic Code Audit
  Title**           Requirements

  **Prepared For**  Claude Code (audit execution)

  **Prepared By**   Business Analysis --- AVSHUNTER-Intelligence

  **Document Type** Audit Requirements Specification (precedes
                    remediation)

  **Status**        Draft --- Ready for Engineering Estimation

  **Trigger**       Confirmed Phase C control-state defect (see companion
                    Requirements: Forward-Looking Control State)

  **Sequencing**    This audit runs BEFORE the forward-control fix is
                    implemented --- findings here may change or add to
                    that fix\'s scope
  ----------------- -----------------------------------------------------

**1. Executive Summary**

The forward-looking control-state defect identified in
WyckoffEngine_3101_v2.py was not found by design review --- it was found
by accident, while investigating one specific losing trade (EMBJ). The
pipeline\'s own commit history shows this class of problem is not new:
the codebase already contains multiple prior fixes for structurally
similar issues (canonical enum drift, forced confidence floors, silent
ambiguity mislabeled as directional signal). That history is valuable
evidence that more instances of the same underlying failure pattern
likely still exist, undiscovered, elsewhere in the pipeline.

This document specifies a structured audit --- to be performed BEFORE
the forward-control fix is built --- that systematically reviews the
pipeline codebase for the same class of defect, using the Phase C bug
and the pipeline\'s own historical fix-comments as a template for what
to look for. The audit produces a findings report only; it does not
implement any fixes. Its output may expand or reorder the scope of the
Phase C fix itself.

**2. Background --- Why This Class of Bug Is Worth Hunting
Systematically**

Three confirmed, code-verified facts motivate this audit:

-   The Phase C Spring/UTAD tie (55/55) is a silent ambiguity being
    passed downstream as if it were a real directional signal --- found
    only via a manual trade post-mortem, not a code review.

-   The pipeline\'s own in-code changelog documents at least two prior
    instances of the same broad category of problem: canonical enum
    string drift causing silent comparison failures
    (WyckoffEngine_3101_v2.py, "FIX 2", BUYERS_IN_CONTROL vs BUYERS),
    and forced confidence floors masking genuine uncertainty ("FIX 1",
    phase_confidence/event_confidence previously always ≥70). Both were
    significant enough to warrant a dated fix and a comment explaining
    the impact.

-   A separate, already-fixed defect in
    wyckoff_crabel_precor_logic_v2.py (FIX-PRECOR-C-EQUIL) shows that
    ambiguous/neutral evidence was previously being misread as a
    confident directional call at meaningful scale --- 300 of 515
    signals in one run.

The common thread across all of these: uncertainty in an upstream module
gets silently converted into false confidence somewhere downstream. That
is a systemic failure pattern, not a one-off bug, and it is exactly the
kind of issue that is cheap to find via a targeted, taxonomy-driven code
review and expensive to find via live trading losses.

**3. Audit Objectives**

-   Systematically identify other locations in the pipeline where the
    same failure pattern --- lagging/uncertain evidence silently treated
    as confident and/or directional --- may exist, using the confirmed
    Phase C bug as the reference pattern.

-   Mine the codebase\'s own existing FIX/changelog comments as a
    primary evidence source --- the engineers who wrote this code have
    already found and documented several instances of this exact class
    of problem; the audit should treat those comments as a map of where
    else to look, not just historical trivia.

-   Produce a single, prioritized findings report with code citations,
    so that remediation work (including but not limited to the Phase C
    fix already scoped) can be planned and sequenced by severity and
    blast radius.

-   Explicitly NOT fix anything during this phase --- the audit\'s job
    is to find and document, not to modify code.

**4. Scope**

**4.1 In scope --- the entire AVSHUNTER pipeline codebase**

This audit covers every pipeline script in the AVSHUNTER project root,
not a fixed enumerated file list. Claude Code has direct filesystem
access and must perform its own discovery pass (directory listing / file
search) to identify the full set of .py modules before beginning the
taxonomy review, rather than assuming the scope is limited to whichever
files a person happened to reference in conversation.

Known modules that MUST be included once discovered (non-exhaustive ---
discovery should not stop at this list):

-   Wyckoff / structural scoring: WyckoffEngine_3101_v2.py,
    wyckoff_crabel_precor_logic_v2.py

-   Volatility forecasting: garch_runner.py

-   Morning gate / authorisation: morning_gate.py,
    morning_thesis_validator.py --- the hard authorisation boundary; any
    silent-ambiguity bug here has direct capital impact and should be
    treated as high-priority regardless of where it falls alphabetically

-   ML confidence layer: ml_confidence_engine.py,
    run_ml_on_vanguard_output.py --- worth specific attention to whether
    the heuristic-prior fallback (used while under the 10-outcome
    retrain threshold) has the same "forced non-null confidence" pattern
    already fixed once in the Wyckoff engine

-   Execution Intelligence Layer (EIL) --- wherever its source lives;
    EIL verdicts feed directly into trade/no-trade decisions

-   Supporting scripts: avshunter_trade_journal.py,
    avshunter_ticker_probe.py, compounding_tracker.py,
    confirmation_ingester.py, and any other .py file discovered in the
    project root or its subfolders

If Claude Code\'s discovery pass finds modules not named above, they are
still in scope --- this list is a floor, not a ceiling.

**4.2 Out of scope**

-   Implementing any fix, including the already-scoped Phase C
    forward-control fix --- that remains a separate, subsequent
    workstream.

-   Performance/latency profiling (functional correctness only in this
    pass).

-   UI/spreadsheet output formatting issues --- this audit is about
    signal-generation logic, not presentation layers.

-   Non-Python assets (data files, workbooks, config files) except where
    read directly by in-scope code to determine a threshold or default
    value.

**5. Issue Taxonomy --- What the Audit Is Specifically Looking For**

The audit must classify every finding against this taxonomy, derived
directly from the confirmed Phase C defect and the pipeline\'s own fix
history. This is not a generic code-quality review --- it is a targeted
hunt for this specific family of problems.

  ----------------- -------------------------------- -----------------------------------
  **Pattern**       **Description**                  **Known instance in this codebase**

  **Lagging         A function whose only inputs are \_determine_control() driving
  evidence treated  backward-looking                 Spring/UTAD direction
  as forward        (trailing-window price/volume/OI 
  signal**          features) is used to answer a    
                    forward-looking question (what   
                    happens next) without any actual 
                    forward-looking input.           

  **Silent          When evidence is genuinely       Spring=55 / UTAD=55 in
  coin-flip on      ambiguous, the code assigns two  \_score_phase_c_events()
  ambiguity**       competing outcomes near-equal    
                    scores instead of emitting an    
                    explicit low-confidence/UNKNOWN  
                    state.                           

  **Forced          A confidence/score value is      WyckoffEngine "FIX 1" ---
  confidence        floored at a minimum (e.g.       previously always ≥70, since
  floors**          always ≥70) regardless of actual removed; verify no equivalent floor
                    evidence quality, hiding genuine remains in precor or garch_runner
                    uncertainty from downstream      
                    consumers.                       

  **Canonical enum  One module emits a string/enum   WyckoffEngine "FIX 2" ---
  / contract        value that a downstream module   BUYERS_IN_CONTROL vs BUYERS; verify
  drift**           doesn\'t recognise, causing a    no other enum family has the same
                    silent comparison failure rather unresolved drift
                    than an error.                   

  **Ambiguous flag  A flag intended as advisory      wyckoff_crabel_precor_logic_v2.py
  treated as veto   (e.g. "conflicts present") gets  FIX-PRECOR-C-EQUIL --- EQUILIBRIUM
  (or vice versa)** silently treated as a hard block misread as SELL_SETUP
                    downstream, or a value intended  
                    as neutral gets treated as       
                    directional.                     

  **Unwired         A module computes a genuine      Verify truth_confidence /
  uncertainty       uncertainty/contradiction signal contradictions are actually
  signals**         but a downstream consumer never  consumed everywhere they\'re
                    actually reads or acts on it.    produced, not just in the
                                                     originating module

  **Unjustified     Hardcoded thresholds (e.g.       Multiple instances in WyckoffEngine
  magic numbers /   UNKNOWN_THRESHOLD = 40.0,        phase-scoring functions --- catalog
  thresholds**      separation \< 10, ROC \> 30%)    each, note which have empirical
                    with no comment tracing them to  justification and which don\'t
                    backtested justification.        

  **Inconsistent    Different functions handle       \_insufficient_data() vs. other
  missing-data      insufficient/missing data        modules\' missing-data paths ---
  handling**        differently (return UNKNOWN vs.  verify consistency
                    force a default vs. error),      
                    which can produce inconsistent   
                    behavior at the same failure     
                    point across modules.            
  ----------------- -------------------------------- -----------------------------------

**6. Audit Methodology**

1.  Mine existing changelogs first. Every module in scope should be
    scanned for its own header changelog / dated FIX comments (the
    pattern already used throughout this codebase, e.g. "FIX 1"--"FIX 4"
    in WyckoffEngine_3101_v2.py, "FIX-PRECOR-C-EQUIL" in the precor
    module). Each documented historical fix should be treated as
    confirmed evidence that the surrounding logic family is
    failure-prone, and nearby/similar logic not covered by that specific
    fix should be reviewed with extra scrutiny.

2.  Apply the taxonomy (Section 5) function-by-function. For every
    function that produces a score, confidence, verdict, or state,
    ask: (a) what happens when the evidence is genuinely ambiguous, (b)
    is that ambiguity ever silently converted into a confident-looking
    output, (c) is there a forced default/floor that could mask a true
    unknown.

3.  Trace cross-module contracts. Wherever one module\'s output (e.g.
    control_state) becomes another module\'s input (e.g. precor fusion),
    verify the receiving module\'s handling of every possible value the
    sending module can emit --- the enum-drift bug (FIX 2) shows this
    exact seam has failed before.

4.  Quantify where possible. Where feasible without new data pulls,
    estimate how often an ambiguous-path branch fires historically (as
    was done for FIX-PRECOR-C-EQUIL\'s 300/515), not just that it exists
    in the code. A finding with a frequency estimate is more actionable
    than a theoretical one.

5.  Cite everything. Every finding must reference exact file, function
    name, and approximate line number --- no finding should be reported
    without a code citation, consistent with how the Phase C defect was
    substantiated.

**7. Deliverable --- Audit Findings Report**

A single structured report (format: table below, one row per finding)
with no code changes included. Required columns:

  --------------- -------------------------- -------------------------- ---------------- ----------
  **Column**      **Content**                **Example**                **Example        **Req.**
                                                                        (cont.)**        

  **File :        Exact code citation        WyckoffEngine_3101_v2.py :                  Yes
  Function :                                 \_score_phase_c_events() :                  
  Line**                                     \~693                                       

  **Pattern**     Which Section 5 taxonomy   Silent coin-flip on                         Yes
                  row applies                ambiguity                                   

  **Finding       Plain-English description  Spring/UTAD scored 55/55                    Yes
  description**   of the issue               when control is                             
                                             EQUILIBRIUM/SHIFTING                        

  **Evidence**    Quantified where possible  Confirmed via code read;                    Where
                                             historical frequency not                    possible
                                             yet measured                                

  **Severity**    Critical/High/Medium/Low   High                                        Yes
                  per 7.1                                                                

  **Suggested     Not a fix --- a            Covered by companion fix                    Yes
  next step**     recommendation for         requirements doc                            
                  follow-up (e.g. "scope                                                 
                  into forward-control fix",                                             
                  "needs its own                                                         
                  requirements doc")                                                     
  --------------- -------------------------- -------------------------- ---------------- ----------

**7.1 Severity definitions**

  -------------- ----------------------------------------------------------
  **Severity**   **Definition**

  **Critical**   Directly affects live trade direction or sizing with no
                 existing safeguard; capital at risk today. (e.g. an
                 unfixed equivalent of FIX-PRECOR-C-EQUIL still active
                 somewhere.)

  **High**       Affects confidence/verdict quality in a way that could
                 plausibly cause a wrong directional call, similar in
                 nature to the confirmed Phase C defect, but not yet
                 quantified at scale.

  **Medium**     A real instance of the taxonomy pattern, but with limited
                 blast radius (rare code path, low-impact field, or already
                 partially mitigated elsewhere).

  **Low**        Code-quality / hygiene issue consistent with the taxonomy
                 in spirit (e.g. an unjustified magic number) but with no
                 clear evidence of causing a wrong output.
  -------------- ----------------------------------------------------------

**8. Acceptance Criteria**

6.  Every .py file discovered in the AVSHUNTER project root (per Section
    4.1\'s discovery-first approach) has been reviewed
    function-by-function against the Section 5 taxonomy --- not sampled,
    and not limited to the modules named as examples in Section 4.1.

7.  Every existing FIX/changelog comment in scope has been explicitly
    cross-referenced: either "no further instances of this pattern found
    nearby" or a new finding logged.

8.  The findings report uses the exact schema in Section 7, with no
    finding missing a code citation.

9.  Findings are severity-tagged per Section 7.1 and sorted Critical →
    Low in the delivered report.

10. The report explicitly states, for each in-scope file, either its
    finding count or an explicit "no issues found" --- silence on a file
    is not an acceptable report state.

11. No source files are modified as part of this deliverable.

**9. Risks & Assumptions**

-   Assumption: the pipeline\'s own historical FIX comments are accurate
    and complete records of what was previously found --- the audit
    treats them as a starting map, not as proof that all instances of a
    given pattern were fully remediated at the time.

-   Risk: if Claude Code\'s discovery pass misses modules (e.g. files in
    an unexpected subfolder, or dynamically imported modules), coverage
    could be silently partial despite this document specifying
    full-pipeline scope. Mitigation: the delivered report must
    explicitly list every file it actually reviewed, so any gap versus
    what\'s really in the repo is visible and checkable rather than
    assumed complete.

-   Risk: quantifying historical frequency (Section 6, step 4) may not
    be possible for every finding without access to historical run data
    --- where not possible, the finding should still be reported with a
    qualitative severity estimate rather than omitted.

**10. Relationship to the Companion Fix Requirements**

The previously delivered "Wyckoff Control-State Determination ---
Forward-Looking Signal Integration" requirements document specifies the
fix for the one confirmed instance of this pattern (Phase C
Spring/UTAD). This audit is intentionally sequenced before that fix is
built, because:

-   The audit may surface the same underlying pattern in a form that
    changes how the fix should be architected (e.g. if the same
    ambiguity-to-confidence conversion exists in Phase D or Phase E
    scoring, a shared/reusable forward-bias utility may be the better
    design than a Phase-C-only patch).

-   The audit may surface higher-severity findings elsewhere (e.g. in
    the morning gate or EIL, once those files are supplied) that should
    be prioritized ahead of the Phase C fix given real capital is at
    stake at the gate/execution layer specifically.

Recommended sequencing: run this audit → review findings → confirm or
re-prioritize the Phase C fix scope → proceed to implementation.
