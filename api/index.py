import sys
import os
import json
from datetime import date
from flask import Flask, render_template

# Ensure project root is on the path so `services` can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

app = Flask(
    __name__,
    template_folder='../templates',
    static_folder='../static'
)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key')


# ── Jinja2 filters ────────────────────────────────────────────────────────────
@app.template_filter('currency')
def currency_filter(value):
    try:
        return f'{int(value):,}'
    except Exception:
        return value


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route('/')
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

        # Include ALL TD projects in the Gantt (even those without CD80 dates yet)
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
