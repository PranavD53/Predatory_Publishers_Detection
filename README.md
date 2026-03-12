## Predatory Publishers Detector

This project is a web-based tool that helps researchers quickly evaluate whether a journal might be **predatory** or **legitimate**, based mainly on its public website.

### What the app does

- **Takes a journal URL as input**
  - You paste the homepage or journal page URL into a simple, elegant web interface.

- **Fetches and analyses public information**
  - The backend visits the URL and works only with content that is publicly visible on the web page.
  - It reads things like titles, descriptions and visible text to build an internal representation of the journal.

- **Applies a trained machine‑learning model**
  - The model has been trained on a curated dataset of known predatory and legitimate journals.
  - Given the processed text, it predicts how similar the site looks to predatory or legitimate journals in that dataset.

- **Returns an easy-to-understand risk assessment**
  - A clear label such as **“Predatory”** or **“Legitimate”**.
  - A numeric **risk score** and **confidence indicator** to show how strong the model’s opinion is.

### What it is useful for

- Helping researchers do a **quick, automated first check** on unfamiliar journals.
- Raising **early warnings** for journals that look suspicious before authors decide where to submit.
- Supporting librarians, supervisors and students in conversations about journal quality.

### What it does *not* do

- It **does not** access paywalled, private, or login‑protected content.
- It **does not** guarantee legal or formal classification of any journal.
- It should **not** be used as the single deciding factor for publication decisions—always pair it with human judgment and institutional guidance.

### High‑level design (without implementation details)

1. A clean web interface collects the journal URL from the user.
2. A backend service retrieves the public page content and prepares it for analysis.
3. A machine‑learning model, trained offline on labelled examples, scores the journal.
4. The frontend displays the result in a clear and visually appealing way.

This repository contains all the components needed to run the application locally or deploy it as a private tool, without exposing any model internals, data processing secrets, or training data specifics. 
