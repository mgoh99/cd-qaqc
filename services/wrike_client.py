import os
import re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, date

WRIKE_TOKEN    = os.environ.get('WRIKE_TOKEN')
WRIKE_BASE_URL = 'https://www.wrike.com/api/v4'

# Persistent session with retry — handles SSL EOF / transient network errors
def _make_session():
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=1,
                  status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=['GET'])
    s.mount('https://', HTTPAdapter(max_retries=retry))
    return s

_session = _make_session()

FOLDER_B_DESIGN = 'IEAFNYJDI44OSHOZ'

CF = {
    'project_number': 'IEAFNYJDJUAJZVBN',
    'sqft':           'IEAFNYJDJUADEAVQ',
    'pm':             'IEAFNYJDJUADEJYZ',
    'designer':       'IEAFNYJDJUADEJY2',   # Lead Designer
}

# ── QAQC dashboard custom fields ──────────────────────────────────────────────
CF_TECH_DESIGNER = 'IEAFNYJDJUAL2B7F'   # Technical Designer (contact ID)
CF_DESIGNER      = 'IEAFNYJDJUAE2M32'   # Designer(s)  — comma-separated contact IDs
CF_CAD_TECH      = 'IEAFNYJDJUADFTU4'   # CAD Tech(s)  — comma-separated contact IDs
CF_ENGINEER      = 'IEAFNYJDJUAGZFSQ'   # Engineer     — plain text (firm name)


def _headers():
    return {'Authorization': f'Bearer {WRIKE_TOKEN}'}


def _cf(custom_fields, field_id):
    for cf in custom_fields:
        if cf['id'] == field_id:
            return cf.get('value')
    return None


def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], '%Y-%m-%d').date()
    except Exception:
        return None


def _get_child_ids(folder_id):
    """
    Fetch the parent folder directly to get its childIds.
    These are the permanent IEAFNYJDI-format IDs that work for direct fetching.
    """
    resp = _session.get(f'{WRIKE_BASE_URL}/folders/{folder_id}', headers=_headers())
    resp.raise_for_status()
    data = resp.json().get('data', [])
    if not data:
        return []
    return [cid for cid in data[0].get('childIds', []) if cid != folder_id]


def _fetch_project(project_id):
    """Fetch a single folder/project by ID."""
    resp = _session.get(f'{WRIKE_BASE_URL}/folders/{project_id}', headers=_headers())
    if resp.status_code == 200:
        data = resp.json().get('data', [])
        return data[0] if data else None
    return None


def _get_contact_map():
    resp = _session.get(f'{WRIKE_BASE_URL}/contacts', headers=_headers())
    resp.raise_for_status()
    contacts = resp.json().get('data', [])
    return {
        c['id']: f"{c.get('firstName', '')} {c.get('lastName', '')}".strip()
        for c in contacts
    }


def _names_from_ids(raw_value, contacts):
    """Resolve a comma-separated string of contact IDs to a display name string."""
    if not raw_value:
        return ''
    ids = [i.strip() for i in str(raw_value).split(',') if i.strip()]
    return ', '.join(contacts.get(i, '') for i in ids if contacts.get(i))


def _get_qaqc_task_dates(project_id):
    """Return (cd80_start, cd80_end, page_turn, permit_sub, issue_for_tender) for a project."""
    try:
        resp = _session.get(
            f'{WRIKE_BASE_URL}/folders/{project_id}/tasks',
            headers=_headers(),
            params={'descendants': True, 'subTasks': True, 'pageSize': 200}
        )
        resp.raise_for_status()
        cd80_start = cd80_end = page_turn = permit_sub = issue_for_tender = None
        for task in resp.json().get('data', []):
            title = task.get('title', '').strip().lower()
            d = task.get('dates', {})
            if title == 'draft cd 80% - id':
                cd80_start       = _parse_date(d.get('start'))
                cd80_end         = _parse_date(d.get('due'))
            elif title == 'internal page turn':
                page_turn        = _parse_date(d.get('due') or d.get('start'))
            elif title == 'permit submission':
                permit_sub       = _parse_date(d.get('due') or d.get('start'))
            elif title == 'issue for tender':
                issue_for_tender = _parse_date(d.get('due') or d.get('start'))
    except Exception:
        pass
    return cd80_start, cd80_end, page_turn, permit_sub, issue_for_tender


def build_qaqc_projects():
    """Return (with_tech_designer, without_tech_designer) lists for the QAQC dashboard.
    Only looks at B-Design projects.
    """
    contacts  = _get_contact_map()
    child_ids = _get_child_ids(FOLDER_B_DESIGN)

    with_tech    = []
    without_tech = []

    for pid in child_ids:
        proj = _fetch_project(pid)
        if not proj:
            continue

        cfl   = proj.get('customFields', [])
        title = proj.get('title', '')

        number = _cf(cfl, CF['project_number']) or ''
        if not number:
            m = re.match(r'\[(\d+)\]', title)
            number = m.group(1) if m else ''

        tech_designer_id   = _cf(cfl, CF_TECH_DESIGNER)
        tech_designer_name = contacts.get(tech_designer_id, '') if tech_designer_id else ''

        if not tech_designer_id:
            without_tech.append({'id': proj['id'], 'number': number, 'name': title})
            continue

        sqft_raw = _cf(cfl, CF['sqft'])
        sqft     = int(float(sqft_raw)) if sqft_raw else 0

        pm_id         = _cf(cfl, CF['pm'])
        pm            = contacts.get(pm_id, '') if pm_id else ''
        lead_designer = contacts.get(_cf(cfl, CF['designer']), '') if _cf(cfl, CF['designer']) else ''
        designer      = _names_from_ids(_cf(cfl, CF_DESIGNER), contacts)
        cad_tech      = _names_from_ids(_cf(cfl, CF_CAD_TECH), contacts)
        engineer      = _cf(cfl, CF_ENGINEER) or ''   # plain text — firm name

        cd80_start, cd80_end, page_turn, permit_sub, issue_for_tender = _get_qaqc_task_dates(pid)

        with_tech.append({
            'id':                proj['id'],
            'number':            number,
            'name':              title,
            'pm':                pm,
            'tech_designer':     tech_designer_name,
            'lead_designer':     lead_designer,
            'designer':          designer,
            'cad_tech':          cad_tech,
            'engineer':          engineer,
            'sqft':              sqft,
            'cd80_start':        cd80_start,
            'cd80_end':          cd80_end,
            'page_turn':         page_turn,
            'permit_submission': permit_sub,
            'issue_for_tender':  issue_for_tender,
        })

    # Sort by CD 80% start date (projects without dates go last)
    with_tech.sort(key=lambda p: p['cd80_start'] or date.max)
    return with_tech, without_tech
