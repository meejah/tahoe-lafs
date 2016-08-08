# build this:
#    docker build --rm --tag tahoe-introducer .
# run this:
#   docker run --name tahoe-introducer -h introducer0 -P -d tahoe-introducer 
# confirm, visit: http://<container-ip>:4560
# get IP: docker inspect tahoe-introducer | grep IPAddress
# figure stuff out:
# docker exec tahoe-introducer ls /tahoe-introducer/

FROM tahoe-base

RUN /tahoevenv/bin/tahoe create-introducer /tahoe-introducer
COPY introducer.port /tahoe-introducer/introducer.port
COPY tahoe.cfg /tahoe-introducer/tahoe.cfg
EXPOSE 4560 5555

CMD /tahoevenv/bin/tahoe start /tahoe-introducer -n


# now can "do stuff" with e.g. alice or bob:
# cat README.rst | docker exec -i tahoe-alice /tahoevenv/bin/tahoe -d /tahoe-client put -
