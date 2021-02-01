# -*- coding: utf-8 -*-

import json
import os

from tornado import web, gen
from notebook.base.handlers import APIHandler

from .handlers import notebook_dir


def _trim_notebook_dir(dir):
    if not dir.startswith("/"):
        return os.path.join(
            "<notebook_dir>", os.path.relpath(dir, notebook_dir)
        )
    return dir


class TbRootHandler(APIHandler):

    @web.authenticated
    def get(self):
        terms = [
            {
                'name': entry.name,
                'logdir': _trim_notebook_dir(entry.logdir),
                "reload_time": entry.reload_interval,
            } for entry in
            self.settings["tensorboard_manager"].values()
        ]
        self.finish(json.dumps(terms))

    @gen.coroutine
    @web.authenticated
    def post(self):
        data = self.get_json_body()
        reload_interval = data.get("reload_interval", None)
        entry = (
            yield self.settings["tensorboard_manager"]
            .new_instance(data["logdir"], reload_interval=reload_interval)
        )

        yield gen.sleep(2)

        self.finish(json.dumps({
                'name': entry.name,
                'logdir':  _trim_notebook_dir(entry.logdir),
                'reload_time': entry.reload_interval}))


class TbInstanceHandler(APIHandler):

    SUPPORTED_METHODS = ('GET', 'DELETE')

    @web.authenticated
    def get(self, name):
        manager = self.settings["tensorboard_manager"]
        if name in manager:
            entry = manager[name]
            self.finish(json.dumps({
                'name': entry.name,
                'logdir':  _trim_notebook_dir(entry.logdir),
                'reload_time': entry.reload_interval}))
        else:
            raise web.HTTPError(
                404, "TensorBoard instance not found: %r" % name)

    @web.authenticated
    def delete(self, name):
        manager = self.settings["tensorboard_manager"]
        if name in manager:
            manager.terminate(name, force=True)
            self.set_status(204)
            self.finish()
        else:
            raise web.HTTPError(
                404, "TensorBoard instance not found: %r" % name)
