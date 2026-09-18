import os
import requests


def used():
    return os.getcwd()


def orphan():
    return requests.get("x")
