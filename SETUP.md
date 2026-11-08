# Setting up Claugineer + Claude as your race engineer

Claugineer records every lap you drive in **Automobilista 2** or **RaceRoom** and writes an analysis to files. Claude reads those files and debriefs you like a race engineer: where you're losing time, one change for the next run, tyres, fuel.

You need: a Windows PC with AMS2 and/or RaceRoom, a Claude account (Pro or higher), and the **Claude desktop app**.

---

## Part 1 – Install the app (10 minutes)

1. **Download** this repo: green **Code** button → **Download ZIP**.
2. **Unzip** it to a simple folder, e.g. `C:\Claugineer`. Avoid OneDrive/Desktop folders.
   Check that `install.bat` sits directly in `C:\Claugineer` and not one folder deeper (GitHub zips add a `Claugineer-main` folder; move its contents up or just use that folder).
3. Double-click **`install.bat`**. It finds Python 3.9+ (or installs it), creates a **Claugineer** desktop shortcut and runs a connection check. If Windows SmartScreen warns you, choose *More info → Run anyway*.
4. **AMS2 only:** Options → System → **Shared Memory = Project CARS 2**. RaceRoom needs nothing.
5. Optional: run **`sim.bat`** to see a simulated session in the dashboard.

**Every time you drive:** start **Claugineer** from the desktop *before* going on track and leave its window open. Dashboard: http://localhost:8770.

First real drive: run `doctor.bat` with the car on track and check the numbers look sensible.

---

## Part 2 – Set up Claude as your engineer (5 minutes)

1. Go to **claude.ai → Projects → Create project**. Name it e.g. *Race Engineer*.
2. Open **`claude-setup/project-instructions.md`** from this repo. Replace `<YOUR NAME>` and `<YOUR CLAUGINEER FOLDER>` (e.g. `C:\Claugineer`) with your own, then paste the whole text into the project's **Instructions**.
3. Add **`claude-setup/engineer-quick-reference.md`** to the project's **files/knowledge**.
4. Open the **Claude desktop app** on the PC you race on. Start a chat in the project and **connect your Claugineer folder** (e.g. `C:\Claugineer`) when it asks, or via the folder/attachment option. This lets Claude read your laps directly.

---

## Part 3 – Using it

- Start a chat in the project: *"AMS2, MINI JCW at Donington National, 30 min practice."*
- Drive. When you're back in the pits, say *"in the pits"*. Claude reads the new laps and gives you a chart, where the time is, and **one** change for the next run.
- Click on any chart or track map in the dashboard to leave a note (*"understeer here"*). Claude answers it in the next debrief.
- At the end, ask Claude to **write the session notes**. It saves `<track>-<car>-notes.md` in your project, and next time picks up where you left off.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| No laps recorded | Claugineer must be running before you leave the pits. AMS2: Shared Memory = Project CARS 2. Run `doctor.bat`. |
| "Run install.bat first" | Run `install.bat` in the same folder. |
| Claude can't see your files | Open the chat in the Claude **desktop app** on the racing PC and connect the Claugineer folder. |
| Dashboard won't open | Something else is using port 8770: change `"port"` in `config.json`. |
| Online races record the wrong car | Put your in-game name in `config.json` → `"player_name"`. |

`config.json` is created the first time the app runs. `config.example.json` shows all the options. Your recordings live in `data\` and never leave your PC unless you share them.
