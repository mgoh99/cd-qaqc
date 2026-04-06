"""
Supabase Auth module.
Handles login, token verification, refresh, and the @login_required decorator.
Uses Supabase GoTrue REST API (no SDK). No JWT secret required.
"""

import functools
import time
import requests
from flask import session, redirect, url_for, request
import config


class AuthError(Exception):
    pass


def login_user(email, password):
    url = f"{config.SUPABASE_URL.rstrip('/')}/auth/v1/token?grant_type=password"
    headers = {
        "apikey": config.SUPABASE_API_KEY,
        "Content-Type": "application/json",
    }
    resp = requests.post(url, json={"email": email, "password": password}, headers=headers, timeout=10)

    if resp.status_code != 200:
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            body = resp.json()
            msg = body.get("error_description") or body.get("msg") or "Login failed"
        else:
            msg = "Login failed"
        raise AuthError(msg)

    data = resp.json()
    return {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at": data.get("expires_at", int(time.time()) + 3600),
        "user_email": data.get("user", {}).get("email", email),
        "user_id": data.get("user", {}).get("id", ""),
    }


def get_user_from_token(access_token):
    url = f"{config.SUPABASE_URL.rstrip('/')}/auth/v1/user"
    headers = {
        "apikey": config.SUPABASE_API_KEY,
        "Authorization": f"Bearer {access_token}",
    }
    resp = requests.get(url, headers=headers, timeout=10)
    if resp.status_code != 200:
        raise AuthError("Invalid token")
    return resp.json()


def refresh_access_token(refresh_token):
    url = f"{config.SUPABASE_URL.rstrip('/')}/auth/v1/token?grant_type=refresh_token"
    headers = {
        "apikey": config.SUPABASE_API_KEY,
        "Content-Type": "application/json",
    }
    resp = requests.post(url, json={"refresh_token": refresh_token}, headers=headers, timeout=10)

    if resp.status_code != 200:
        raise AuthError("Session expired. Please log in again.")

    data = resp.json()
    return {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at": data.get("expires_at", int(time.time()) + 3600),
    }


def update_user_password(access_token, new_password):
    url = f"{config.SUPABASE_URL.rstrip('/')}/auth/v1/user"
    headers = {
        "apikey": config.SUPABASE_API_KEY,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    resp = requests.put(url, json={"password": new_password}, headers=headers, timeout=10)

    if resp.status_code != 200:
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            body = resp.json()
            msg = body.get("error_description") or body.get("msg") or "Password update failed"
        else:
            msg = "Password update failed"
        raise AuthError(msg)

    return resp.json()


def get_current_user():
    if "user_email" in session and "access_token" in session:
        return {
            "email": session["user_email"],
            "user_id": session.get("user_id", ""),
        }
    return None


def login_required(f):
    """
    Protects a route. Checks Flask session for a valid token.
    Uses expires_at to detect expiry; attempts refresh before redirecting to /login.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        access_token = session.get("access_token")
        refresh_token_val = session.get("refresh_token")
        expires_at = session.get("expires_at", 0)

        if not access_token:
            session["next_url"] = request.url
            return redirect(url_for("login_page"))

        if int(time.time()) >= expires_at:
            if refresh_token_val:
                try:
                    new_tokens = refresh_access_token(refresh_token_val)
                    session["access_token"] = new_tokens["access_token"]
                    session["refresh_token"] = new_tokens["refresh_token"]
                    session["expires_at"] = new_tokens["expires_at"]
                except AuthError:
                    session.clear()
                    session["next_url"] = request.url
                    return redirect(url_for("login_page"))
            else:
                session.clear()
                session["next_url"] = request.url
                return redirect(url_for("login_page"))

        return f(*args, **kwargs)

    return decorated
