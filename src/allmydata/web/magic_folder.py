from nevow import rend, url, tags as T
from allmydata.web.common import getxmlfile

class MagicFolderWebApi(rend.Page):
    """
    I provide the web-based API for Magic Folder status etc.
    """

    docFactory = getxmlfile("magic-folder-status.xhtml")

    def __init__(self, client):
        ##rend.Page.__init__(self, storage)
        super(MagicFolderWebApi, self).__init__(client)
        self.client = client


    def render_foo(self, ctx):
        ul = T.ul()
        for item in self.client._magic.downloader.get_status():
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

        for element in self.client._magic.uploader.get_status():
            ul[T.li[str(element)]]

        return ul

#    def renderHTTP(self, ctx):
#        return rend.Page.renderHTTP(self, ctx)


