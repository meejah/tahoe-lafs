import simplejson  # XXX why not built-in "json"

from twisted.web.server import UnsupportedMethod

from nevow import rend, url, tags as T
from nevow.inevow import IRequest

from allmydata.web.common import getxmlfile, get_arg, WebError


class MagicFolderWebApi(rend.Page):
    """
    I provide the web-based API for Magic Folder status etc.
    """

    docFactory = getxmlfile("magic-folder-status.xhtml")

    def __init__(self, client):
        super(MagicFolderWebApi, self).__init__(client)
        self.client = client

    def render_magic_status(self, ctx):
        ul = T.ul()
        for item in self.client._magic_folder.downloader.get_status():
            prct = item.progress.progress  # XXX hmm, smells bad
            prog = T.div(style='width: 100%; height: 2px; background-color: #aaa;')[
                T.div(style='width: %f%%; height: 2px; background-color: #e66; border-right: 5px solid #f00;' % prct),
            ]
            took = ''
            if item.finished_at and item.started_at:
                took = ' (took ' + str(item.finished_at - item.started_at) + 's)'
            ul[
                T.li[
                    str(item.relpath_u), ': ', str(item.status),
                    ' started ', str(item.started_at),
                    ' finished at ', str(item.finished_at),
                    took,
                    prog,
                ]
            ]

        for element in self.client._magic_folder.uploader.get_status():
            ul[T.li[str(element)]]

        return ul

    def _render_json(self, req):
        req.setHeader("content-type", "application/json")

        data = []
        for item in self.client._magic_folder.uploader.get_status():
            d = dict(
                path=item.relpath_u,
                status=item.status,
                kind='upload',
            )
            for nm in ['started_at', 'finished_at', 'queued_at']:
                if getattr(item, nm) is not None:
                    d[nm] = getattr(item, nm)
            d['percent_done'] = item.progress.progress
            data.append(d)

        for item in self.client._magic_folder.downloader.get_status():
            d = dict(
                path=item.relpath_u,
                status=item.status,
                kind='download',
            )
            for nm in ['started_at', 'finished_at', 'queued_at']:
                if getattr(item, nm) is not None:
                    d[nm] = getattr(item, nm)
            d['percent_done'] = item.progress.progress
            data.append(d)

        return simplejson.dumps(data)

    def renderHTTP(self, ctx):
        req = IRequest(ctx)
        t = get_arg(req, "t", None)
        if req.method != 'POST':
            raise UnsupportedMethod(('POST',))

        token = get_arg(req, "token", None)
        # XXX need constant-time comparison?
        if token is None or token != self.client.get_auth_token():
            raise WebError("Missing or invalid token.", 400)

        if t is None:
            return rend.Page.renderHTTP(self, ctx)

        t = t.strip()
        if t == 'json':
            return self._render_json(req)

        raise WebError("'%s' invalid type for 't' arg" % (t,), 400)


