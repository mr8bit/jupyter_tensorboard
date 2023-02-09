# -*- coding: utf-8 -*-
import os
import time
import itertools
import urllib
from collections import namedtuple

from tornado import gen, httpclient
from tornado.httpclient import HTTPError

from .handlers import nb_app_logger

import subprocess

import pkg_resources
import importlib

import atexit


def cleanup_instances():
    manager.terminate_all()


atexit.register(cleanup_instances)


def get_free_tcp_port():
    import socket
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.bind(('', 0))
    addr, port = tcp.getsockname()
    tcp.close()
    return port


@gen.coroutine
def create_tb_app(logdir, reload_interval, purge_orphaned_data):
    client = httpclient.AsyncHTTPClient()

    try:
        importlib.reload(pkg_resources)
        _ = pkg_resources.get_distribution('tensorboard')
        tensorboard_version = _.version
        tensorboard_version = tensorboard_version.split('a')[0]
        print("tensorboard version user",tensorboard_version)
    except pkg_resources.DistributionNotFound:
        nb_app_logger.error("import tensorboard failed, "
                            "check tensorboard installation")

    port = get_free_tcp_port()
    argv = [
        "tensorboard",
        "--port", str(port),
        "--logdir", logdir,
        "--reload_interval", str(reload_interval),
        "--purge_orphaned_data", str(purge_orphaned_data),
    ]
    if not os.environ.get("JUPYTER_TENSORBOARD_DISABLE_BINDALL", False):
        if tensorboard_version < "2.0.0":
            argv.extend(["--host", "0.0.0.0"])
        else:
            argv.extend(["--bind_all"])

    if tensorboard_version >= "2.3.0":
        argv.extend(["--reload_multifile", "true"])

    if tensorboard_version >= "2.12.0":
        argv.extend(["--load_fast", "false"])

    nb_app_logger.info("Start tensorboard with: %s" % ' '.join(argv))
    tb_proc = subprocess.Popen(argv)

    elpased = 0
    while elpased < 60:
        elpased += 1
        yield gen.sleep(1)
        try:
            req = httpclient.HTTPRequest("http://127.0.0.1:%d/" % port)
            yield client.fetch(req)
        except ConnectionRefusedError as e:
            nb_app_logger.info("Waiting for tensorboard: %s" % e.strerror)
            continue
        except HTTPError as e:
            nb_app_logger.info("Waiting for tensorboard: "
                               "Tensorboard status code is %s, "
                               "entering sleep for 1 second" %
                               e.code)
            continue
        nb_app_logger.info("Waiting for tensorboard: Tensorboard status code "
                           "is 200, so stop waiting")
        break

    return tb_proc, port


from .handlers import notebook_dir  # noqa

TensorBoardInstance = namedtuple(
    'TensorBoardInstance',
    ['name', 'logdir', 'process', 'port', 'reload_interval']
)


class TensorboardManger(dict):

    def __init__(self):
        self._logdir_dict = {}

    def _next_available_name(self):
        for n in itertools.count(start=1):
            name = "%d" % n
            if name not in self:
                return name

    @gen.coroutine
    def new_instance(self, logdir, reload_interval):
        if not os.path.isabs(logdir) and notebook_dir:
            logdir = os.path.join(notebook_dir, logdir)

        if logdir not in self._logdir_dict:
            purge_orphaned_data = True
            reload_interval = reload_interval or 30
            pid, port = yield create_tb_app(
                logdir=logdir, reload_interval=reload_interval,
                purge_orphaned_data=purge_orphaned_data)

            manager.add_instance(logdir, pid, port, reload_interval)

        return self._logdir_dict[logdir]

    def add_instance(self, logdir, process, port, reload_interval):
        name = self._next_available_name()
        instance = TensorBoardInstance(
            name,
            logdir,
            process,
            port,
            reload_interval
        )
        self[name] = instance
        self._logdir_dict[logdir] = instance

    def terminate(self, name, force=True):
        if name in self:
            instance = self[name]
            if instance.process is not None:
                try:
                    if force:
                        instance.process.kill()
                    else:
                        instance.process.terminate()
                    instance.process.wait(5)
                except subprocess.TimeoutExpired:
                    pass

            del self[name], self._logdir_dict[instance.logdir]
        else:
            raise Exception("There's no tensorboard instance named %s" % name)

    def terminate_all(self, force=True):
        for i in list(self.keys()):
            try:
                self.terminate(i, force)
            except Exception:
                pass


manager = TensorboardManger()
