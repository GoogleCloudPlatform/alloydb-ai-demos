import os
from dotenv import load_dotenv

load_dotenv()

instance_connection_name = os.getenv("instance_connection_name")
# e.g. 'project:region:instance'
db_user = os.getenv("db_user")  # e.g. 'my-db-user'
db_pass = os.getenv("db_pass") # e.g. 'my-db-password'
db_name = os.getenv("db_name")  # e.g. 'my-database'
schema_name = os.getenv("schema_name")