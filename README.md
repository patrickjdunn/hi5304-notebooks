# Data Science Coding Laboratory

**Python • R • SQL (PostgreSQL) in GitHub Codespaces**

This repository is designed to run in **GitHub Codespaces** with a fully preconfigured environment for **Python**, **R**, and **PostgreSQL (psql)**. No local installation is required.

---

## Getting Started in Codespaces

1. Click **Code → Codespaces → Create codespace on main**
2. Wait for the environment to finish building (this may take a few minutes the first time)
3. Once loaded, you are ready to work in:

   * Jupyter notebooks (Python or R)
   * The terminal (Python, R, or SQL via `psql`)

---

## Using Python and R in Jupyter Notebooks

This environment supports **both Python and R kernels**.

### How to switch kernels in a notebook

1. Open a `.ipynb` notebook
2. In the top menu, select **Kernel → Change Kernel**
3. Choose one of:

   * **Python 3** → for Python-based analysis
   * **R** → for R-based analysis

You can freely switch kernels depending on the notebook or lesson.

---

## Running Python, R, and SQL from the Terminal

Open a terminal in Codespaces (**Terminal → New Terminal**) and use the commands below.

### Python (terminal)

```bash
python --version
python
```

To exit Python:

```text
exit()
```

---

### R (terminal)

```bash
R --version
R
```

To exit R:

```text
q()
```

---

### PostgreSQL (psql)

The course database is already running in the background.

**Connect to PostgreSQL:**

```bash
psql -h db -p 5432 -U dataScience_user -d data_science
```

When prompted for a password, enter:

```text
data_science
```

**Helpful psql commands:**

```sql
\dt          -- list tables
\d table     -- describe a table
\q           -- quit psql
```

---

## Environment Sanity Check (Recommended)

If you ever want to confirm your environment is working correctly, run the following in the terminal:

```bash
python --version
psql --version
R --version
jupyter kernelspec list
```

Expected output includes:

* Python 3.x
* PostgreSQL client (`psql`)
* R
* Jupyter kernels: `python3` and `ir`

---

## Important Notes

* The **GitHub repository name**, **workspace folder**, and **database name** do not need to match.
* You do **not** need to install Python, R, or PostgreSQL locally.
* Everything runs inside Codespaces for consistency and reproducibility.

---

## Need Help?

If something does not work as expected:

1. Restart the notebook kernel
2. Reload the Codespaces window
3. Re-run the environment sanity check above



