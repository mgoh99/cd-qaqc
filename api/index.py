import sys
import os
import json
import hashlib
import secrets
import base64
import requests
from datetime import date, timedelta
from flask import Flask, render_template, request, session, redirect, url_for, jsonify

# Ensure project root is on the path so `services`, `auth`, `config` can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from auth import login_required, login_user, get_current_user, get_user_from_token, update_user_password, AuthError

app = Flask(
    __name__,
    template_folder='../templates',
    static_folder='../static'
)
app.secret_key = config.FLASK_SECRET_KEY
app.permanent_session_lifetime = timedelta(seconds=config.SESSION_LIFETIME_SECONDS)


@app.context_processor
def inject_current_user():
    email = session.get("user_email", "")
    return {"current_user": {"email": email} if email else None}


# ── Jinja2 filters ────────────────────────────────────────────────────────────
@app.template_filter('currency')
def currency_filter(value):
    try:
        return f'{int(value):,}'
    except Exception:
        return value


# ── Auth Routes ───────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "GET":
        if get_current_user():
            return redirect(url_for("index"))
        error = request.args.get("error")
        return render_template("login.html", error=error)

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not email or not password:
        return render_template("login.html", error="Email and password are required.")

    try:
        tokens = login_user(email, password)
        session.permanent = True
        session["access_token"] = tokens["access_token"]
        session["refresh_token"] = tokens["refresh_token"]
        session["expires_at"] = tokens["expires_at"]
        session["user_email"] = tokens["user_email"]
        session["user_id"] = tokens["user_id"]

        next_url = session.pop("next_url", None) or url_for("index")
        return redirect(next_url)
    except AuthError as e:
        return render_template("login.html", error=str(e))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


@app.route("/auth/azure")
def auth_azure():
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    session["pkce_code_verifier"] = code_verifier

    site_url = request.url_root.rstrip("/")
    redirect_to = f"{site_url}/auth/callback"
    supabase_url = config.SUPABASE_URL.rstrip("/")
    oauth_url = (
        f"{supabase_url}/auth/v1/authorize"
        f"?provider=azure"
        f"&redirect_to={redirect_to}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=s256"
    )
    return redirect(oauth_url)


@app.route("/auth/callback")
def auth_callback():
    code = request.args.get("code")
    if code:
        code_verifier = session.pop("pkce_code_verifier", "")
        if not code_verifier:
            return redirect(url_for("login_page", error="Session expired. Please try again."))

        supabase_url = config.SUPABASE_URL.rstrip("/")
        resp = requests.post(
            f"{supabase_url}/auth/v1/token?grant_type=pkce",
            json={"auth_code": code, "code_verifier": code_verifier},
            headers={
                "apikey": config.SUPABASE_API_KEY,
                "Content-Type": "application/json",
            },
            timeout=10,
        )

        if resp.status_code != 200:
            error_msg = "Sign in failed"
            try:
                body = resp.json()
                error_msg = body.get("error_description") or body.get("msg") or error_msg
            except Exception:
                pass
            return redirect(url_for("login_page", error=error_msg))

        data = resp.json()
        user = data.get("user", {})
        session.permanent = True
        session["access_token"] = data["access_token"]
        session["refresh_token"] = data.get("refresh_token", "")
        session["expires_at"] = data.get("expires_at", 0)
        session["user_email"] = user.get("email", "")
        session["user_id"] = user.get("id", "")

        next_url = session.pop("next_url", None) or url_for("index")
        return redirect(next_url)

    return render_template("auth_callback.html")


@app.route("/auth/exchange-code", methods=["POST"])
def auth_exchange_code():
    data = request.get_json(force=True)
    code = data.get("code", "")
    if not code:
        return jsonify({"error": "No auth code provided"}), 400

    code_verifier = session.pop("pkce_code_verifier", "")
    if not code_verifier:
        return jsonify({"error": "Session expired. Please try again."}), 400

    supabase_url = config.SUPABASE_URL.rstrip("/")
    resp = requests.post(
        f"{supabase_url}/auth/v1/token?grant_type=pkce",
        json={"auth_code": code, "code_verifier": code_verifier},
        headers={
            "apikey": config.SUPABASE_API_KEY,
            "Content-Type": "application/json",
        },
        timeout=10,
    )

    if resp.status_code != 200:
        error_msg = "Sign in failed"
        try:
            body = resp.json()
            error_msg = body.get("error_description") or body.get("msg") or error_msg
        except Exception:
            pass
        return jsonify({"error": error_msg}), 401

    tokens = resp.json()
    user = tokens.get("user", {})
    session.permanent = True
    session["access_token"] = tokens["access_token"]
    session["refresh_token"] = tokens.get("refresh_token", "")
    session["expires_at"] = tokens.get("expires_at", 0)
    session["user_email"] = user.get("email", "")
    session["user_id"] = user.get("id", "")

    next_url = session.pop("next_url", None) or url_for("index")
    return jsonify({"redirect": next_url})


@app.route("/auth/token-login", methods=["POST"])
def auth_token_login():
    data = request.get_json(force=True)
    access_token = data.get("access_token", "")
    refresh_token_val = data.get("refresh_token", "")

    if not access_token:
        return jsonify({"error": "No access token provided"}), 400

    try:
        user = get_user_from_token(access_token)
        session.permanent = True
        session["access_token"] = access_token
        session["refresh_token"] = refresh_token_val
        session["expires_at"] = 0
        session["user_email"] = user.get("email", "")
        session["user_id"] = user.get("id", "")

        next_url = session.pop("next_url", None) or url_for("index")
        return jsonify({"success": True, "redirect": next_url})
    except Exception as e:
        return jsonify({"error": str(e)}), 401


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password_page():
    if request.method == "GET":
        access_token = request.args.get("access_token")
        refresh_token_val = request.args.get("refresh_token")
        if not access_token:
            return redirect(url_for("login_page"))
        return render_template(
            "reset_password.html",
            access_token=access_token,
            refresh_token=refresh_token_val or "",
        )

    access_token = request.form.get("access_token", "")
    refresh_token_val = request.form.get("refresh_token", "")
    new_password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not new_password or len(new_password) < 6:
        return render_template(
            "reset_password.html",
            access_token=access_token,
            refresh_token=refresh_token_val,
            error="Password must be at least 6 characters.",
        )

    if new_password != confirm_password:
        return render_template(
            "reset_password.html",
            access_token=access_token,
            refresh_token=refresh_token_val,
            error="Passwords do not match.",
        )

    try:
        update_user_password(access_token, new_password)
        return render_template("login.html", error=None, success="Password updated. Sign in with your new password.")
    except AuthError as e:
        return render_template(
            "reset_password.html",
            access_token=access_token,
            refresh_token=refresh_token_val,
            error=str(e),
        )


@app.route("/access-denied")
def access_denied_page():
    return render_template("access_denied.html")


# ── App Routes ────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def index():
    from services.wrike_client import build_qaqc_projects
    try:
        with_tech, without_tech = build_qaqc_projects()
    except Exception as e:
        return render_template('error.html', message=str(e)), 503

    today = date.today()

    def fmt(d):
        return d.strftime('%d %b %Y') if d else None

    display = []
    gantt_data = []

    for p in with_tech:
        cd80_active  = bool(p['cd80_start'] and p['cd80_end'] and p['cd80_start'] <= today <= p['cd80_end'])
        permit_past  = bool(p['permit_submission'] and p['permit_submission'] < today)

        dp = dict(p)
        dp['cd80_start_str']       = fmt(p['cd80_start'])
        dp['cd80_end_str']         = fmt(p['cd80_end'])
        dp['page_turn_str']        = fmt(p['page_turn'])
        dp['permit_sub_str']       = fmt(p['permit_submission'])
        dp['issue_for_tender_str'] = fmt(p['issue_for_tender'])
        dp['cd80_active']          = cd80_active
        dp['permit_past']          = permit_past
        display.append(dp)

        num = p['number']
        label = f"[{num}] {p['name']}"[:60] if num else p['name'][:60]
        gantt_data.append({
            'id':               p['id'],
            'number':           num,
            'label':            label,
            'cd80_start':       p['cd80_start'].isoformat()        if p['cd80_start']       else None,
            'cd80_end':         p['cd80_end'].isoformat()          if p['cd80_end']         else None,
            'page_turn':        p['page_turn'].isoformat()         if p['page_turn']        else None,
            'permit_sub':       p['permit_submission'].isoformat() if p['permit_submission'] else None,
            'issue_for_tender': p['issue_for_tender'].isoformat()  if p['issue_for_tender'] else None,
            'active':           cd80_active,
            'has_cd80':         bool(p['cd80_start'] and p['cd80_end']),
        })

    return render_template('qaqc.html',
        with_tech    = display,
        without_tech = without_tech,
        gantt_json   = json.dumps(gantt_data),
        today_iso    = today.isoformat(),
    )


if __name__ == '__main__':
    port = 5055
    print(f'\n  CD QAQC Tracker running at: http://localhost:{port}\n')
    app.run(debug=True, port=port)
