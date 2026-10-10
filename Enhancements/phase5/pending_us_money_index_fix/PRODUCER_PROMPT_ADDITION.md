# US Money Index producer: wording to add to the LLM prompt

Add to the output-format section of the prompt that writes `avshunter_us_money_index.json`:

> In `current_state`, the fields `regime_change_since_monday`, `monetisation_change_since_monday` and
> `risk_off_transition` are JSON booleans (`true` or `false`), never text. Put any explanation in a separate text
> field with the same name plus `_detail`, for example:
>
> ```json
> "risk_off_transition": true,
> "risk_off_transition_detail": "CONFIRMED_WITH_AI_SOX_MULTI_SESSION_FAILURE_AND_AI_REVENUE_FINANCING_REPRICING; NO_BROAD_SYSTEMIC_UPGRADE"
> ```

Then check each new packet before the Evening:

```
venv\Scripts\python.exe scripts\validate_us_money_index.py
```

`ACCEPTED` lists each flag and how it was read; `REFUSED` gives the field and reason, so the packet can be
regenerated before the run. Since 7 Oct the producer had been writing `risk_off_transition` as text (all earlier
packets in `dropbox/macro/Archive` carry `true`), and the pipeline refused the whole packet (verification G2-03).
