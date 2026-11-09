import os

from pymongo import MongoClient
from pymongo.errors import PyMongoError

_client = None


def get_mongo_client():
    global _client

    if _client is None:
        uri = os.getenv("MONGODB_URI")

        if not uri:
            raise RuntimeError("MONGODB_URI is not configured")

        _client = MongoClient(
            uri,
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
            maxPoolSize=20,
        )

    return _client


def get_mongo_db():
    return get_mongo_client()["vr_tech_solutions"]


def test_mongo_connection():
    try:
        get_mongo_client().admin.command("ping")
        return True
    except PyMongoError:
        return False