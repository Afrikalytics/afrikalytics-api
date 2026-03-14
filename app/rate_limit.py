"""
Configuration du rate limiter (SlowAPI).
Extrait de main.py pour etre importable par les routers sans import circulaire.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
