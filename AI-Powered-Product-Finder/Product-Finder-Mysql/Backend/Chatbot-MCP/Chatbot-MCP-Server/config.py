import os
from dotenv import load_dotenv

load_dotenv()

instance_connection_name = os.getenv("instance_connection_name")
db_user = os.getenv("db_user") 
db_pass = os.getenv("db_pass")
db_name = os.getenv("db_name")
