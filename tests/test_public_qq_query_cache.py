"""Transient API errors must not outlive renewed authorization."""
import ast
import base64
import inspect
import json
import time
import tempfile
import unittest
from functools import wraps
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Tuple


class QueryErrorCacheTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        source=Path(__file__).resolve().parents[1]/'gsuid_core/utils/cache.py'
        if not source.exists():self.skipTest('Isolated patched core checkout is not available')
        tree=ast.parse(source.read_text(encoding='utf-8'))
        decorator=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='gs_cache')
        self.cache={}
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        namespace={'inspect':inspect,'json':json,'time':time,'wraps':wraps,'Dict':Dict,'List':List,'Tuple':Tuple,'Path':Path,
                   'CACHE':self.cache,'IMAGE_CACHE':Path(temporary.name),'t':lambda key,**kwargs:key,
                   'base64':base64,'convert_img_sync':lambda p:p.read_bytes(),
                   'logger':SimpleNamespace(trace=lambda *args:None),'Image':SimpleNamespace(Image=type('UnusedImage',(),{}))}
        exec(compile(ast.Module(body=[decorator],type_ignores=[]),str(source),'exec'),namespace)
        self.gs_cache=namespace['gs_cache']

    async def test_hard_challenge_retries_after_cookie_is_saved(self):
        source=Path(__file__).resolve().parents[1]/'gsuid_core/utils/api/mys/request.py'
        tree=ast.parse(source.read_text(encoding='utf-8'))
        method=next(node for node in ast.walk(tree) if isinstance(node,ast.AsyncFunctionDef) and node.name=='get_hard_challenge_data')
        namespace={'gs_cache':self.gs_cache,'Union':__import__('typing').Union,'Dict':Dict,
                   'HardChallengeData':dict,'HARD_CHALLENGE':'mock-endpoint','cast':__import__('typing').cast}
        exec(compile(ast.Module(body=[method],type_ignores=[]),str(source),'exec'),namespace)
        calls=[]
        async def endpoint(*args,**kwargs):
            calls.append(kwargs)
            return -51 if len(calls)==1 else {'data':{'challenge':'available'}}
        client=SimpleNamespace(get_server_id=lambda *args:'mock-server',endpoint_request=endpoint)
        query=namespace['get_hard_challenge_data']
        self.assertEqual(await query(client,'test-uid'),-51)
        self.assertEqual(await query(client,'test-uid'),{'challenge':'available'})
        self.assertEqual(await query(client,'test-uid'),{'challenge':'available'})
        self.assertEqual(len(calls),2)

    async def test_async_error_is_retried_but_success_is_cached(self):
        calls=[]
        @self.gs_cache(360,skip_int=True)
        async def query(uid):
            calls.append(uid)
            return -999 if len(calls)==1 else {'success':True}
        self.assertEqual(await query('test-uid'),-999)
        self.assertEqual(self.cache,{})
        self.assertEqual(await query('test-uid'),{'success':True})
        self.assertEqual(await query('test-uid'),{'success':True})
        self.assertEqual(len(calls),2)

    async def test_existing_error_cache_is_ignored(self):
        @self.gs_cache(360,skip_int=True)
        async def query(uid):return {'success':True}
        self.cache[time.time()]={"query_'test-uid'":-999}
        self.assertEqual(await query('test-uid'),{'success':True})

    async def test_all_mys_cached_queries_skip_integer_errors(self):
        source=Path(__file__).resolve().parents[1]/'gsuid_core/utils/api/mys/request.py'
        tree=ast.parse(source.read_text(encoding='utf-8'))
        count=0
        for node in ast.walk(tree):
            if not isinstance(node,ast.AsyncFunctionDef):continue
            for decorator in node.decorator_list:
                if isinstance(decorator,ast.Call) and isinstance(decorator.func,ast.Name) and decorator.func.id=='gs_cache':
                    count+=1
                    self.assertIn('int',ast.unparse(node.returns))
                    self.assertTrue(any(k.arg=='skip_int' and isinstance(k.value,ast.Constant) and k.value.value is True for k in decorator.keywords),node.name)
        self.assertEqual(count,14)

    async def test_text_error_retries_and_success_is_cached(self):
        calls=[]
        @self.gs_cache(1800,skip_text=True)
        async def render(uid):
            calls.append(uid)
            return 'No Cookie' if len(calls)==1 else {'rendered':True}
        self.assertEqual(await render('test-uid'),'No Cookie')
        self.assertEqual(self.cache,{})
        self.assertEqual(await render('test-uid'),{'rendered':True})
        self.assertEqual(await render('test-uid'),{'rendered':True})
        self.assertEqual(len(calls),2)

    async def test_existing_text_error_is_ignored(self):
        @self.gs_cache(1800,skip_text=True)
        async def render(uid):return {'rendered':True}
        self.cache[time.time()]={"render_'test-uid'":'No Cookie'}
        self.assertEqual(await render('test-uid'),{'rendered':True})

    async def test_sync_text_error_retries(self):
        calls=[]
        @self.gs_cache(1800,skip_text=True)
        def render(uid):
            calls.append(uid)
            return 'No Cookie' if len(calls)==1 else {'rendered':True}
        self.assertEqual(render('test-uid'),'No Cookie')
        self.assertEqual(render('test-uid'),{'rendered':True})
        self.assertEqual(render('test-uid'),{'rendered':True})
        self.assertEqual(len(calls),2)

    async def test_base64_image_still_caches_with_skip_text(self):
        calls=[]
        @self.gs_cache(1800,skip_text=True)
        def render(uid):
            calls.append(uid)
            return 'base64://'+base64.b64encode(b'fake-image-data').decode()
        self.assertTrue(render('test-uid').startswith('base64://'))
        self.assertEqual(render('test-uid'),b'fake-image-data')
        self.assertEqual(len(calls),1)

    async def test_default_integer_caching_remains_unchanged(self):
        calls=[]
        @self.gs_cache(360)
        async def query(uid):
            calls.append(uid);return 7
        self.assertEqual(await query('test-uid'),7)
        self.assertEqual(await query('test-uid'),7)
        self.assertEqual(len(calls),1)

    async def test_sync_errors_also_retry(self):
        calls=[]
        @self.gs_cache(360,skip_int=True)
        def query(uid):
            calls.append(uid);return -999 if len(calls)==1 else {'success':True}
        self.assertEqual(query('test-uid'),-999)
        self.assertEqual(query('test-uid'),{'success':True})
        self.assertEqual(query('test-uid'),{'success':True})
        self.assertEqual(len(calls),2)
