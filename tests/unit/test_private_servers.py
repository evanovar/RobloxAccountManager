import threading
import unittest
from unittest.mock import Mock, patch

from features import private_servers


def response(data, status=200):
    result = Mock(status_code=status, headers={})
    result.json.return_value = data
    return result


def detail(server_id):
    return {'id': server_id, 'name': 'My Server', 'active': True,
            'game': {'name': 'Test Game', 'rootPlace': {'id': 123}}, 'joinCode': 'abc'}


class PrivateServerTests(unittest.TestCase):
    def run_load(self, responses, place=''):
        session = Mock()
        session.headers = {}
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        session.get.side_effect = responses
        with patch.object(private_servers.requests, 'Session', return_value=session):
            result = private_servers.load_servers('test-cookie', 99, place)
        return result, session

    def test_pagination_deduplicates_server_ids(self):
        result, session = self.run_load([
            response({'data': [{'privateServerId': 1, 'id': 3527577077}], 'nextPageCursor': 'next'}),
            response(detail(1)),
            response({'data': [{'privateServerId': 1}, {'privateServerId': 2}]}),
            response(detail(2)),
        ])
        self.assertTrue(result)
        self.assertEqual([row['id'] for row in result.data], ['1', '2'])
        self.assertEqual(session.get.call_count, 4)
        self.assertEqual(result.data[0]['link'], 'https://www.roblox.com/games/123?privateServerLinkCode=abc')
        self.assertEqual(session.get.call_args_list[2].kwargs['params']['cursor'], 'next')
        self.assertTrue(session.get.call_args_list[1].args[0].endswith('/vip-servers/1'))
        self.assertEqual(session.get.call_args_list[0].kwargs['params']['privateServersTab'], 'MyPrivateServers')
        self.assertEqual(session.get.call_args_list[0].kwargs['params']['itemsPerPage'], 10)

    def test_link_uses_listing_place_when_detail_root_is_missing(self):
        self.assertEqual(private_servers.server_link({'joinCode': 'abc'}, {'placeId': 123}),
                         'https://www.roblox.com/games/123?privateServerLinkCode=abc')
        self.assertEqual(private_servers.server_link({'joinCode': 'abc'}, {}, '123'),
                         'https://www.roblox.com/games/123?privateServerLinkCode=abc')
        self.assertEqual(private_servers.server_link(
            {'privateServerLink': '/share?code=abc&type=Server'}),
            'https://www.roblox.com/share?code=abc&type=Server')
        self.assertEqual(private_servers.server_link(
            {'linkCode': 'abc'}, {'placeId': 123}),
            'https://www.roblox.com/games/123?privateServerLinkCode=abc')

    def test_servers_are_delivered_one_at_a_time(self):
        session = Mock()
        session.headers = {}
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        session.get.side_effect = [response({'data': [{'privateServerId': i} for i in range(1, 12)]})] + [
            response(detail(i)) for i in range(1, 12)]
        batches = []
        with patch.object(private_servers.requests, 'Session', return_value=session):
            result = private_servers.load_servers('test', 99, on_progress=lambda rows: batches.append(
                (len(rows), session.get.call_count)))
        self.assertTrue(result)
        self.assertEqual(batches[0], (1, 2))
        self.assertEqual(len(batches), 11)
        self.assertEqual(len(result.data), 11)

    def test_generic_id_is_never_used_for_details(self):
        result, session = self.run_load([response({'data': [{'id': 3527577077}]})])
        self.assertEqual(result.code, 'PRIVATE_SERVER_RESPONSE_INVALID')
        self.assertEqual(session.get.call_count, 1)

    def test_disabled_servers_are_skipped_across_pages(self):
        result, session = self.run_load([
            response({'data': [{'privateServerId': 1}, {'privateServerId': 2}], 'nextPageCursor': 'next'}),
            response({'errors': [{'code': 8}]}, 400),
            response(detail(2)),
            response({'data': [{'privateServerId': 3}]}),
            response(detail(3)),
        ])
        self.assertTrue(result)
        self.assertEqual([row['id'] for row in result.data], ['2', '3'])
        self.assertEqual(session.get.call_count, 5)

    def test_all_disabled_servers_return_empty_list(self):
        result, _ = self.run_load([
            response({'data': [{'privateServerId': 1}]}),
            response({'errors': [{'code': 8}]}, 400),
        ])
        self.assertTrue(result)
        self.assertEqual(result.data, [])

    def test_other_detail_errors_are_not_silenced(self):
        result, _ = self.run_load([
            response({'data': [{'privateServerId': 1}]}),
            response({'errors': [{'code': 4}]}, 400),
        ])
        self.assertEqual(result.code, 'PRIVATE_SERVER_REQUEST_FAILED')

    def test_listing_error_eight_is_not_skipped(self):
        result, _ = self.run_load([response({'errors': [{'code': 8}]}, 400)])
        self.assertEqual(result.code, 'PRIVATE_SERVER_REQUEST_FAILED')

    def test_http_error_includes_roblox_error_code(self):
        result, _ = self.run_load([response({'errors': [{'code': 4, 'message': 'Private data'}]}, 400)])
        self.assertIn('Roblox error code(s): 4', result.detail)
        self.assertNotIn('Private data', result.detail)

    def test_place_search_filters_other_owners(self):
        result, session = self.run_load([
            response({'data': [{'vipServerId': 1, 'owner': {'id': 12}},
                               {'vipServerId': 2, 'owner': {'id': 99}}]}),
            response(detail(2)),
        ], '123')
        self.assertTrue(result)
        self.assertEqual([row['id'] for row in result.data], ['2'])
        self.assertEqual(session.get.call_count, 2)

    def test_server_id_is_not_used_as_join_code(self):
        data = detail(567)
        data.pop('joinCode')
        self.assertEqual(private_servers.server_link(data), '')
        data['link'] = 'https://www.roblox.com/share?code=abc&type=Server'
        self.assertEqual(private_servers.server_link(data), data['link'])
        data['link'] = 'https://example.com/not-roblox'
        self.assertEqual(private_servers.server_link(data), '')

    def test_authorization_and_malformed_responses(self):
        result, _ = self.run_load([response({}, 401)])
        self.assertEqual(result.code, 'COOKIE_INVALID')
        result, _ = self.run_load([response({}, 403)])
        self.assertEqual(result.code, 'COOKIE_INVALID')
        result, _ = self.run_load([response({'errors': [{'code': 9002}]}, 400)])
        self.assertEqual(result.code, 'COOKIE_INVALID')
        result, _ = self.run_load([response({'unexpected': []})])
        self.assertEqual(result.code, 'PRIVATE_SERVER_RESPONSE_INVALID')

    def test_rate_limits_bounded_and_cancellable(self):
        cancel = Mock()
        cancel.is_set.return_value = False
        cancel.wait.return_value = False
        session = Mock()
        session.get.return_value = response({}, 429)
        result = private_servers._get(session, '/test', {}, cancel)
        self.assertEqual(result.code, 'RATE_LIMITED')
        self.assertEqual(session.get.call_count, 3)
        event = threading.Event()
        event.set()
        session.reset_mock()
        result = private_servers._get(session, '/test', {}, event)
        self.assertEqual(result.code, 'CANCELLED')
        session.get.assert_not_called()

    def test_invalid_input_and_missing_cookie(self):
        self.assertEqual(private_servers.load_servers('', 99).code, 'ACCOUNT_COOKIE_MISSING')
        self.assertEqual(private_servers.load_servers('test', 99, '../invalid').code, 'PLACE_ID_INVALID')

    def test_generate_link_uses_csrf_and_patch(self):
        session = Mock()
        session.headers = {}
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        token_response = response({}, 403)
        token_response.headers = {'x-csrf-token': 'token'}
        session.post.return_value = token_response
        session.patch.return_value = response({
            'link': 'https://www.roblox.com/share?code=test&type=Server'
        })
        with patch.object(private_servers.requests, 'Session', return_value=session):
            result = private_servers.generate_link('cookie', 123, 456)
        self.assertTrue(result)
        self.assertEqual(result.data, 'https://www.roblox.com/share?code=test&type=Server')
        self.assertEqual(session.headers['X-CSRF-TOKEN'], 'token')
        self.assertEqual(session.patch.call_args.kwargs['json'], {'newJoinCode': True})

    def test_generate_link_fetches_detail_after_empty_patch_response(self):
        session = Mock()
        session.headers = {}
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        token_response = response({}, 403)
        token_response.headers = {'x-csrf-token': 'token'}
        session.post.return_value = token_response
        session.patch.return_value = response({})
        session.get.return_value = response({'joinCode': 'abc'})
        with patch.object(private_servers.requests, 'Session', return_value=session):
            result = private_servers.generate_link('cookie', 123, 456)
        self.assertTrue(result)
        self.assertEqual(result.data, 'https://www.roblox.com/games/456?privateServerLinkCode=abc')

    def test_generate_link_detects_invalid_cookie(self):
        session = Mock()
        session.headers = {}
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        session.post.return_value = response({}, 401)
        with patch.object(private_servers.requests, 'Session', return_value=session):
            result = private_servers.generate_link('cookie', 123, 456)
        self.assertEqual(result.code, 'COOKIE_INVALID')
        session.patch.assert_not_called()
