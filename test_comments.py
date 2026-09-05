import os
os.environ["TRUSTED_HOSTS"] = "localhost"
from app import app
with app.test_client() as client:
    resp = client.get('/api/cats/00000000-0000-4000-8000-000000000001/comments', headers={"Host": "localhost"})
    print("STATUS /comments:", resp.status_code)
    print("JSON:", resp.json)
