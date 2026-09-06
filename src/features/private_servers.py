import threading
from urllib.parse import urlencode, urlparse

import requests

from classes.operation_result import OperationResult


API_ROOT = 'https://games.roblox.com'


def _failure(code, message, detail=''):
    return OperationResult.failure(code, 'Private Server Manager', message, detail=detail)


def _get(session, path, params, cancel):
    for attempt in range(3):
        if cancel.is_set():
            return _failure('CANCELLED', 'Request cancelled.')
        try:
            response = session.get(API_ROOT + path, params=params, timeout=(5, 10),
                                   allow_redirects=False)
        except requests.Timeout:
            return _failure('NETWORK_TIMEOUT', 'Roblox did not respond in time. Try again.')
        except requests.RequestException:
            return _failure('NETWORK_ERROR', 'Could not connect to Roblox. Check your connection.')
        if response.status_code == 429:
            if attempt < 2:
                try:
                    delay = min(15, max(1, float(response.headers.get('Retry-After', 2 ** (attempt + 1)))))
                except (ValueError, TypeError):
                    delay = 2 ** (attempt + 1)
                if cancel.wait(delay):
                    return _failure('CANCELLED', 'Request cancelled.')
                continue
            return _failure('RATE_LIMITED', 'Roblox is rate limiting requests. Please try again later.')
        if response.status_code == 401:
            return _failure('COOKIE_INVALID', 'Roblox rejected this account cookie. Sign in again.')
        if response.status_code == 403:
            return _failure('COOKIE_INVALID', 'Roblox rejected this account cookie. Sign in again.')
        if response.status_code != 200:
            detail = f'HTTP {response.status_code} for {path}'
            codes = []
            try:
                errors = response.json().get('errors', [])
                codes = [_positive_id(error.get('code')) for error in errors if isinstance(error, dict)]
                codes = [code for code in codes if code]
                if codes:
                    detail += '\nRoblox error code(s): ' + ', '.join(codes[:10])
            except (ValueError, AttributeError, TypeError):
                pass
            if (response.status_code == 400 and codes == ['8']
                    and path.startswith('/v1/vip-servers/')
                    and _positive_id(path.rsplit('/', 1)[-1])):
                return _failure('PRIVATE_SERVERS_DISABLED',
                                'The creator has disabled private servers for this game.', detail)
            if response.status_code == 400 and any(code in ('9001', '9002') for code in codes):
                return _failure('COOKIE_INVALID', 'Roblox rejected this account cookie. Sign in again.', detail)
            return _failure('PRIVATE_SERVER_REQUEST_FAILED', 'Roblox could not return the private servers.',
                            detail)
        try:
            data = response.json()
        except ValueError:
            return _failure('PRIVATE_SERVER_RESPONSE_INVALID', 'Roblox returned an unreadable response.')
        if not isinstance(data, dict):
            return _failure('PRIVATE_SERVER_RESPONSE_INVALID', 'Roblox returned an unexpected response format.')
        return OperationResult.success(data=data)


def _positive_id(value):
    text = str(value or '')
    return text if text.isascii() and text.isdecimal() and int(text) > 0 else ''


def _link_value(data):
    for key in ('link', 'privateServerLink', 'shareLink'):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        value = value.strip()
        if value.startswith('/'):
            value = 'https://www.roblox.com' + value
        elif value.startswith(('roblox.com/', 'www.roblox.com/')):
            value = 'https://' + value
        parsed = urlparse(value)
        if parsed.scheme == 'https' and parsed.hostname in ('roblox.com', 'www.roblox.com'):
            return value
    return ''


def server_link(detail, entry=None, fallback_place_id=''):
    entry = entry or {}
    for data in (detail, entry):
        link = _link_value(data)
        if link:
            return link
    game = detail.get('game') or {}
    root = game.get('rootPlace') or {}
    place_id = (_positive_id(root.get('id')) or _positive_id(entry.get('placeId'))
                or _positive_id(fallback_place_id))
    code = ''
    for data in (detail, entry):
        for key in ('joinCode', 'linkCode', 'privateServerLinkCode'):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                code = value.strip()
                break
        if code:
            break
    if place_id and code:
        return f'https://www.roblox.com/games/{place_id}?' + urlencode({'privateServerLinkCode': code})
    return ''


def generate_link(cookie, server_id, place_id='', cancel=None):
    cancel = cancel or threading.Event()
    server_id = _positive_id(server_id)
    if not cookie:
        return _failure('ACCOUNT_COOKIE_MISSING', 'This account has no saved cookie. Sign in again.')
    if not server_id:
        return _failure('PRIVATE_SERVER_ID_INVALID', 'Roblox did not provide a valid private server ID.')
    if place_id and not _positive_id(place_id):
        return _failure('PLACE_ID_INVALID', 'Roblox did not provide a valid Place ID for this server.')
    if cancel.is_set():
        return _failure('CANCELLED', 'Request cancelled.')
    with requests.Session() as session:
        session.headers['Cookie'] = f'.ROBLOSECURITY={cookie}'
        try:
            token_response = session.post('https://auth.roblox.com/v2/logout', timeout=(5, 10),
                                          allow_redirects=False)
        except requests.Timeout:
            return _failure('NETWORK_TIMEOUT', 'Roblox did not respond in time. Try again.')
        except requests.RequestException:
            return _failure('NETWORK_ERROR', 'Could not connect to Roblox. Check your connection.')
        token = token_response.headers.get('x-csrf-token')
        if not token:
            if token_response.status_code in (401, 403):
                return _failure('COOKIE_INVALID', 'Roblox rejected this account cookie. Sign in again.')
            return _failure('CSRF_TOKEN_FAILED', 'Roblox could not authorize the link change. Try again.')
        session.headers['X-CSRF-TOKEN'] = token
        path = f'/v1/vip-servers/{server_id}'
        for attempt in range(3):
            if cancel.is_set():
                return _failure('CANCELLED', 'Request cancelled.')
            try:
                response = session.patch(API_ROOT + path, json={'newJoinCode': True}, timeout=(5, 10),
                                         allow_redirects=False)
            except requests.Timeout:
                return _failure('NETWORK_TIMEOUT', 'Roblox did not respond in time. Try again.')
            except requests.RequestException:
                return _failure('NETWORK_ERROR', 'Could not connect to Roblox. Check your connection.')
            if response.status_code == 429 and attempt < 2:
                if cancel.wait(2 ** (attempt + 1)):
                    return _failure('CANCELLED', 'Request cancelled.')
                continue
            if response.status_code in (401, 403):
                return _failure('COOKIE_INVALID', 'Roblox rejected this account cookie. Sign in again.')
            if response.status_code != 200:
                return _failure('PRIVATE_SERVER_LINK_FAILED', 'Roblox could not generate the server link.',
                                f'HTTP {response.status_code} for {path}')
            try:
                detail = response.json()
            except ValueError:
                detail = {}
            if not isinstance(detail, dict):
                detail = {}
            link = server_link(detail, fallback_place_id=place_id)
            if not link:
                detail_result = _get(session, path, {}, cancel)
                if not detail_result:
                    return detail_result
                link = server_link(detail_result.data, fallback_place_id=place_id)
            if link:
                return OperationResult.success(data=link)
            return _failure('PRIVATE_SERVER_LINK_UNAVAILABLE',
                            'Roblox generated the join code but did not return a usable link.')
        return _failure('RATE_LIMITED', 'Roblox is rate limiting requests. Please try again later.')


def load_servers(cookie, user_id, place_id='', cancel=None, on_progress=None):
    cancel = cancel or threading.Event()
    if not cookie:
        return _failure('ACCOUNT_COOKIE_MISSING', 'This account has no saved cookie. Sign in again.')
    if place_id and not _positive_id(place_id):
        return _failure('PLACE_ID_INVALID', 'Enter a positive numeric Place ID or leave the field empty.')
    if place_id and not _positive_id(user_id):
        return _failure('ACCOUNT_ID_MISSING', 'Refresh this account before searching by Place ID.')
    path = (f'/v1/games/{place_id}/private-servers' if place_id
            else '/v1/private-servers/my-private-servers')
    with requests.Session() as session:
        session.headers['Cookie'] = f'.ROBLOSECURITY={cookie}'
        rows = []
        seen_ids = set()
        cursors = set()
        cursor = ''
        for page in range(100):
            params = ({'limit': 10, 'cursor': cursor} if place_id else
                      {'itemsPerPage': 10, 'privateServersTab': 'MyPrivateServers', 'cursor': cursor})
            result = _get(session, path, params, cancel)
            if not result:
                return result
            data = result.data
            entries = data.get('data')
            if not isinstance(entries, list):
                return _failure('PRIVATE_SERVER_RESPONSE_INVALID',
                                'Roblox returned an unexpected server list. Check the Console for details.',
                                'The response did not contain a data list.')
            for entry in entries:
                if not isinstance(entry, dict):
                    return _failure('PRIVATE_SERVER_RESPONSE_INVALID', 'Roblox returned an invalid server entry.')
                if place_id and str((entry.get('owner') or {}).get('id')) != str(user_id):
                    continue
                # Listing IDs are not interchangeable with VIP server IDs.
                id_field = 'vipServerId' if place_id else 'privateServerId'
                server_id = _positive_id(entry.get(id_field))
                if not server_id:
                    return _failure('PRIVATE_SERVER_RESPONSE_INVALID',
                                    'Roblox returned a server without a valid private server ID.',
                                    f'Missing or invalid {id_field} in {path}.')
                if server_id in seen_ids:
                    continue
                seen_ids.add(server_id)
                detail_result = _get(session, f'/v1/vip-servers/{server_id}', {}, cancel)
                if not detail_result:
                    if detail_result.code == 'PRIVATE_SERVERS_DISABLED':
                        continue
                    return detail_result
                detail = detail_result.data
                game = detail.get('game') or {}
                root = game.get('rootPlace') or {}
                rows.append({
                    'id': server_id,
                    'place_id': (_positive_id(root.get('id')) or _positive_id(entry.get('placeId'))
                                 or _positive_id(place_id)),
                    'game': str(game.get('name') or root.get('name') or root.get('id') or 'Unknown Game'),
                    'name': str(detail.get('name') or entry.get('name') or server_id),
                    'status': 'Active' if detail.get('active') else 'Inactive',
                    'link': server_link(detail, entry, place_id),
                })
                if not rows[-1]['link']:
                    print(f"[WARNING] Private server {server_id} has no usable join link. "
                          f"Detail fields: {', '.join(sorted(detail))}. "
                          f"List fields: {', '.join(sorted(entry))}.")
                if on_progress and not cancel.is_set():
                    on_progress([dict(rows[-1])])
            cursor = data.get('nextPageCursor')
            if not cursor:
                return OperationResult.success(data=rows)
            if not isinstance(cursor, str) or cursor in cursors:
                return _failure('PRIVATE_SERVER_RESPONSE_INVALID', 'Roblox returned a repeated or invalid page cursor.')
            cursors.add(cursor)
        return _failure('PRIVATE_SERVER_PAGE_LIMIT', 'Too many server pages. Narrow the search with a Place ID.')


def start_load(manager, username, place_id, on_done, on_progress=None):
    account = dict(manager.accounts.get(username, {}))
    cancel = threading.Event()

    def worker():
        try:
            cookie = account.get('cookie', '')
            result = load_servers(cookie, account.get('user_id'), place_id, cancel, on_progress)
        except Exception as exc:
            # Do not log requests or response bodies, which can contain private links or cookies.
            result = _failure('PRIVATE_SERVER_UNEXPECTED_ERROR',
                              'Private servers could not be loaded. Check the Console for details.',
                              f'Unexpected {type(exc).__name__} while loading servers.')
        if not cancel.is_set():
            try:
                on_done(result)
            except RuntimeError:
                pass

    threading.Thread(target=worker, daemon=True, name='PrivateServerManager').start()
    return cancel


def start_generate_link(manager, username, server_id, place_id, on_done):
    account = dict(manager.accounts.get(username, {}))
    cancel = threading.Event()

    def worker():
        try:
            result = generate_link(account.get('cookie', ''), server_id, place_id, cancel)
        except Exception as exc:
            result = _failure('PRIVATE_SERVER_UNEXPECTED_ERROR',
                              'The private server link could not be generated. Check the Console for details.',
                              f'Unexpected {type(exc).__name__} while generating a server link.')
        if not cancel.is_set():
            try:
                on_done(result)
            except RuntimeError:
                pass

    threading.Thread(target=worker, daemon=True, name='PrivateServerLink').start()
    return cancel
