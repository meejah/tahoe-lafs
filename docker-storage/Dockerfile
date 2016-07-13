FROM python:2.7
ARG furl
ARG nick

COPY tahoe-lafs.tar.gz /tahoe-lafs.tar.gz
RUN virtualenv /tahoevenv && /tahoevenv/bin/pip install --upgrade pip setuptools && /tahoevenv/bin/pip install --find-links=https://tahoe-lafs.org/deps/ /tahoe-lafs.tar.gz

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
