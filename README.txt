GraphColor Web Starter

Run locally:
1. Open a terminal in this folder.
2. Run: py -m pip install -r requirements.txt
3. Run: py -m streamlit run app.py

Online deployment:
1. Upload app.py and requirements.txt to a GitHub repository.
2. Sign in to Streamlit Community Cloud and connect GitHub.
3. Choose the repository, branch, and app.py, then deploy.

Important:
This starter uses SQLite on the app's local filesystem. For reliable persistent
shared data on a hosted public app, connect a managed database such as Supabase.
Anyone who can open this public demo can submit or import registrations. Do not
put private or real student data into a public demo until access controls and
persistent storage are configured.
