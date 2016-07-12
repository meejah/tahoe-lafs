FROM python:2.7
ARG furl
ARG nick

# FIXME should run "python setup.py sdist" ... somethingsomething stuff it in here...
ADD tahoe-lafs-1.11.0.post381.dev0.tar.gz /tahoe-src
RUN virtualenv /tahoevenv && /tahoevenv/bin/pip install --upgrade pip setuptools && /tahoevenv/bin/pip install /tahoe-src/tahoe-lafs-1.11.0.post381.dev0

# FIXME get introducer fURL dynamically from introducer container!
RUN /tahoevenv/bin/tahoe create-node --nickname $nick --introducer $furl --webport tcp:3456 /tahoe-storage

# XXX FIXME can haz templatez?
RUN echo "[node]" > /tahoe-storage/tahoe.cfg 
RUN echo nickname = $nick >> /tahoe-storage/tahoe.cfg 
RUN echo web.port = 3456 >> /tahoe-storage/tahoe.cfg 
RUN echo web.static = public_html >> /tahoe-storage/tahoe.cfg 


RUN echo "[client]" >> /tahoe-storage/tahoe.cfg 
RUN echo shares.needed = 1 >> /tahoe-storage/tahoe.cfg 
RUN echo shares.happy = 1 >> /tahoe-storage/tahoe.cfg 
RUN echo shares.total = 1 >> /tahoe-storage/tahoe.cfg 
RUN echo introducer.furl = $furl >> /tahoe-storage/tahoe.cfg

EXPOSE 3456

CMD /tahoevenv/bin/tahoe start /tahoe-storage -n
