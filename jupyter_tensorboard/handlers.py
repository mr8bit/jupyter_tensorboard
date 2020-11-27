# -*- coding: utf-8 -*-

from tornado import web, gen
from tornado.httpclient import AsyncHTTPClient, HTTPRequest, HTTPError
from tornado.httputil import HTTPHeaders, parse_response_start_line
from notebook.base.handlers import IPythonHandler
from notebook.utils import url_path_join as ujoin
from notebook.base.handlers import path_regex

notebook_dir = None
nb_app_logger = None


def load_jupyter_server_extension(nb_app):

    global notebook_dir
    # notebook_dir should be root_dir of contents_manager
    notebook_dir = nb_app.contents_manager.root_dir

    global nb_app_logger
    nb_app_logger = nb_app.log

    web_app = nb_app.web_app
    base_url = web_app.settings['base_url']

    try:
        from .tensorboard_manager import manager
    except ImportError:
        nb_app.log.error("import tensorboard error, check tensorflow install")
        handlers = [
            (ujoin(
                base_url, r"/tensorboard.*"),
                TensorboardErrorHandler),
        ]
    else:
        web_app.settings["tensorboard_manager"] = manager
        from . import api_handlers

        handlers = [
            (ujoin(
                base_url, r"/tensorboard/(?P<name>\w+)%s" % path_regex),
                TensorboardHandler),
            (ujoin(
                base_url, r"/api/tensorboard"),
                api_handlers.TbRootHandler),
            (ujoin(
                base_url, r"/api/tensorboard/(?P<name>\w+)"),
                api_handlers.TbInstanceHandler),
        ]

    web_app.add_handlers('.*$', handlers)
    nb_app.log.info("jupyter_tensorboard extension loaded.")

fetch = AsyncHTTPClient().fetch

class TensorboardHandler(IPythonHandler):

    @gen.coroutine
    @web.authenticated
    def get(self, name, path):

        if path == "":
            uri = self.request.path + "/"
            if self.request.query:
                uri += "?" + self.request.query
            self.redirect(uri, permanent=True)
            return

        path = (path if self.request.query is None
            else "%s?%s" % (path, self.request.query))


        manager = self.settings["tensorboard_manager"]
        if name in manager:
            tb_port = manager[name].port

            request = HTTPRequest("http://127.0.0.1:%d%s" % (tb_port, path),
                 headers = self.request.headers,
                 header_callback = self._handle_headers,
                 streaming_callback = self._handle_chunk,
                 decompress_response = False)
            try:
                response = yield fetch(request)
            except HTTPError as e:
                nb_app_logger.warning(e)
                raise web.HTTPError(500)

            #response.rethrow()

            self.finish()

        else:
            raise web.HTTPError(404)

    def _handle_headers(self, headers):
        if hasattr(self, "_theaders"):
            if headers == "\r\n":
                for kv in self._theaders.get_all():
                    self.log.debug("%s:%s" % kv)
                    self.add_header(kv[0], kv[1])
                del self._theaders
                return
            try:
                self._theaders.parse_line(headers)
            except:
                return
        else:
            r = parse_response_start_line(headers)
            self.set_status(r.code, r.reason)
            self._theaders = HTTPHeaders()

    def _handle_chunk(self, chunk):
        self.write(chunk)
        self.flush()

class TensorboardErrorHandler(IPythonHandler):
    pass
