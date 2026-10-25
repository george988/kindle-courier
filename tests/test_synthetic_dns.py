"""Offline regressions for synthetic egress DNS; no network or user state needed."""
import io, json, os, socket, sys, unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import courier_common as C

PUBLIC = '104.18.37.127'
def infos(*ips):
    return [(socket.AF_INET6 if ':' in ip else socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443)) for ip in ips]
def answer(qtype=1, ips=None, **changes):
    obj = {'Status': 0, 'TC': False, 'Question': [{'name': 'pbs.twimg.com', 'type': qtype}],
           'Answer': [{'name': 'pbs.twimg.com', 'type': qtype, 'data': ip} for ip in (ips or [])]}
    obj.update(changes)
    return json.dumps(obj).encode()
def response(body, status=200, mime='application/dns-json', location=None):
    r = Mock(status=status)
    r.read.return_value = body
    r.getheader.side_effect = lambda key: {'Content-Type': mime, 'Location': location}.get(key)
    return r

class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'KC_ALLOW_PRIVATE_FETCH': ''}); self.env.start()
        self.addCleanup(self.env.stop)
    def test_normal_public_uses_no_doh(self):
        with patch('socket.getaddrinfo', return_value=infos(PUBLIC)), patch.object(C, '_doh_public_addresses') as doh:
            self.assertEqual(C.resolve_vetted('pbs.twimg.com',443),PUBLIC); doh.assert_not_called()
    def test_synthetic_uses_public_result(self):
        with patch('socket.getaddrinfo', return_value=infos('198.18.0.1','198.19.255.254')), patch.object(C, '_doh_public_addresses', return_value=[PUBLIC]) as doh:
            self.assertEqual(C.resolve_vetted('pbs.twimg.com',443),PUBLIC); doh.assert_called_once_with('pbs.twimg.com')
    def test_private_and_mixed_answers_have_no_fallback(self):
        for ips in [('127.0.0.1',),('10.0.0.1',),('169.254.169.254',),('::1',),('fc00::1',),('100.64.0.1',),('224.0.0.1',),('198.18.0.1',PUBLIC),(PUBLIC,'10.0.0.1')]:
            with self.subTest(ips=ips), patch('socket.getaddrinfo',return_value=infos(*ips)), patch.object(C,'_doh_public_addresses') as doh:
                with self.assertRaises(C.FetchError): C.resolve_vetted('untrusted.example',443)
                doh.assert_not_called()
    def test_empty_dns_refused(self):
        with patch('socket.getaddrinfo',return_value=[]):
            with self.assertRaises(C.FetchError): C.resolve_vetted('empty.example',443)
    def test_doh_failure_not_silently_bypassed(self):
        with patch('socket.getaddrinfo',return_value=infos('198.18.0.1')), patch.object(C,'_doh_public_addresses',side_effect=C.FetchError('timeout')):
            with self.assertRaisesRegex(C.FetchError,'timeout'): C.resolve_vetted('pbs.twimg.com',443)
    def run_doh(self, responses):
        conn = Mock(); conn.getresponse.side_effect = responses
        with patch('http.client.HTTPSConnection',return_value=conn) as factory:
            result = C._doh_public_addresses('pbs.twimg.com')
        return result,conn,factory
    def test_verified_fixed_ip_bounded_queries(self):
        result,conn,factory=self.run_doh([response(answer(1,[PUBLIC])),response(answer(28,['2606:4700::6812:257f']))])
        self.assertEqual(result,[PUBLIC,'2606:4700::6812:257f'])
        for call in factory.call_args_list:
            self.assertEqual(call.args,('1.1.1.1',443)); self.assertEqual(call.kwargs['timeout'],10)
            self.assertTrue(call.kwargs['context'].check_hostname)
            import ssl
            self.assertEqual(call.kwargs['context'].verify_mode,ssl.CERT_REQUIRED)
        self.assertEqual(conn.close.call_count,2)
    def test_doh_rejects_bad_status_type_size_json_and_records(self):
        cases=[response(b'',302,location='http://127.0.0.1/'),response(b'',500),response(b'{}',mime='text/html'),
               response(b'x'*65537),response(b'invalid'),response(b'[]'),response(answer(Status=3)),
               response(answer(TC=True)),response(answer(1,[PUBLIC],Question=[{'name':'other.example','type':1}])),
               response(answer(1,[PUBLIC],Answer={})),response(answer(1,[PUBLIC],Answer=[None])),
               response(answer(1,['not-an-ip'])),response(answer(1,['127.0.0.1'])),
               response(answer(1,[PUBLIC,'169.254.169.254'])),response(answer(1,['::1']))]
        for r in cases:
            with self.subTest(response=r):
                with self.assertRaises(C.FetchError): self.run_doh([r])
    def test_private_aaaa_rejects_even_with_public_a(self):
        with self.assertRaises(C.FetchError): self.run_doh([response(answer(1,[PUBLIC])),response(answer(28,['fd00::1']))])
    def test_no_answers_refused(self):
        with self.assertRaises(C.FetchError): self.run_doh([response(answer(1)),response(answer(28))])
    def test_doh_timeout_closes_connection(self):
        conn=Mock(); conn.request.side_effect=TimeoutError('timed out')
        with patch('http.client.HTTPSConnection',return_value=conn):
            with self.assertRaises(C.FetchError): C._doh_public_addresses('pbs.twimg.com')
        conn.close.assert_called_once()
    def test_literals_invalid_names_never_query(self):
        for host in ['198.18.0.1','127.0.0.1','::1','',None,'example.com/path','name@pbs.twimg.com']:
            with self.subTest(host=host),patch('http.client.HTTPSConnection') as conn:
                with self.assertRaises(C.FetchError): C._doh_public_addresses(host)
                conn.assert_not_called()
    def test_download_pins_public_ip_and_tls_hostname(self):
        ctx=Mock(); sock=Mock(); ctx.wrap_socket.return_value=sock
        r=response(b'JPEG',mime='image/jpeg')
        with patch.object(C,'resolve_vetted',return_value=PUBLIC),patch('socket.create_connection',return_value=Mock()) as dial,patch('ssl.create_default_context',return_value=ctx),patch('http.client.HTTPSConnection.request',autospec=True,side_effect=lambda self,*a,**k:self.connect()),patch('http.client.HTTPSConnection.getresponse',return_value=r):
            self.assertEqual(C.safe_fetch('https://pbs.twimg.com/media/photo.jpg')[0],b'JPEG')
        self.assertEqual(dial.call_args.args[0],(PUBLIC,443)); self.assertEqual(ctx.wrap_socket.call_args.kwargs['server_hostname'],'pbs.twimg.com')
    def test_invalid_image_data_remains_a_failure(self):
        import tempfile
        import article2epub as A
        fetcher=Mock(); fetcher.get.return_value=b'not an image'
        with tempfile.TemporaryDirectory() as d:
            filename,reason,size=A.fetch_img(fetcher,'https://pbs.twimg.com/media/bad.jpg',d,'bad')
        self.assertIsNone(filename); self.assertIn('fetch/decode failed',reason)

    def test_redirect_to_private_is_revalidated(self):
        ctx=Mock(); ctx.wrap_socket.return_value=Mock()
        def dns(host,*args,**kw): return infos('127.0.0.1' if host=='127.0.0.1' else PUBLIC)
        with patch('socket.getaddrinfo',side_effect=dns),patch('socket.create_connection',return_value=Mock()),patch('ssl.create_default_context',return_value=ctx),patch('http.client.HTTPSConnection.request',autospec=True,side_effect=lambda self,*a,**k:self.connect()),patch('http.client.HTTPSConnection.getresponse',return_value=response(b'',302,location='https://127.0.0.1/')):
            with self.assertRaisesRegex(C.FetchError,'non-public address'): C.safe_fetch('https://pbs.twimg.com/media/photo.jpg')

if __name__=='__main__': unittest.main(verbosity=2)
