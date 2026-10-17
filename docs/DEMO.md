# Recording the demo video (2–3 minutes)

The six beats from the brief, with what to have on screen. Record on a design partner's data if
you have it. If you use Demo Co, say so on screen: it's synthetic, and the app shows a banner saying so.

## Set-up (once, before recording)

Use a fresh database: the programme runs once per database. In PowerShell, from `backend/`, start
the API on its own demo database:

```
$env:DATABASE_URL = "sqlite:///./demo.db"
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python -m uvicorn app.main:app
```

In a second terminal, also in `backend/` and with the same `DATABASE_URL`, prepare Demo Co up to the
first beat you want to perform live. For example, to sign graduation on camera:

```
$env:DATABASE_URL = "sqlite:///./demo.db"
.venv\Scripts\python -m demo --stop-before graduate
```

Other pause points: `approve-handbook`, `autonomy`, `swap`. To make new invoices arrive during a
take: `.venv\Scripts\python -m demo live 10`. Add `--decide` to also report what the mentor did.
Start the web app from `web/` with `npm run dev` and open http://localhost:3000. Pick the acting
person from "Acting as" in the header (Sarah = mentor, Morgan = manager). To start over, stop the
API and delete `backend/demo.db`.

## The beats

| Time | Show | Where |
| --- | --- | --- |
| 0:00 | A real team's documents become the agent's handbook; the manager approves it | **Orientation**: the five policies, the questionnaire, the handbook with source chips. Click a chip to show the passage, switch to Morgan, approve |
| 0:25 | A sealed prediction revealed beside what the expert actually did | **Today**: a card showing "What you did" and "What the intern would have done" |
| 0:55 | A one-tap lesson, and the rule it creates changing later predictions | **Today**: tap a lesson (0.03 s). Then **What I've learned**: edit a rule and show "This changed N predictions in your backlog" |
| 1:25 | The track record crossing the bar; the manager signs graduation | **Task board**: the proposal with the error bound under α and all checks green. Sarah signs supervised; later Morgan signs autonomy |
| 1:50 | Supervised mode drafting an action; an unusual case handed back with a reason | **Autonomy**: approve a draft in one tap. In hand-backs, an over-limit invoice: "always hand back: amount above 5000 GBP" |
| 2:15 | A new model swapped in and re-certified in minutes; the manager view | **Task board** as Morgan: swap the model, show the history line "re-certified on the frozen record". Then **Manager**: cases handled, hours returned, net saving |

## Tips

- Keep the browser at about 1280 px wide; every screen fits without horizontal scrolling.
- The track record PDF (Task board → Track record) makes a good closing still.
- The founder video is separate: just you, talking plainly to camera.
