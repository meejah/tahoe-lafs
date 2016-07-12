#!/bin/bash

# XXX mostly just notes? this will blow away and re-start the
# docker-ized storage cluster

# huzzah! it works!

# there's one manual step though! when you create the introducer, we
# still have to manually copy the introducer-fURL from it to the
# storage-server

echo "building dist"
python setup.py sdist
# kinda-bad; hopefully we've installed this in our "current" venv??
LATEST=$(python -c "import allmydata; print allmydata.__version__")
cp dist/tahoe-lafs-${LATEST}.tar.gz docker-introducer/
cp dist/tahoe-lafs-${LATEST}.tar.gz docker-storage/

echo "nuking exiting containers"
docker rm -f tahoe-introducer
docker rm -f tahoe-storage0
docker rm -f tahoe-storage1

echo "creating introducer"
docker build --rm --tag tahoe-introducer docker-introducer/
docker run --name tahoe-introducer -h introducer0 -P -d tahoe-introducer
echo "...waiting"
sleep 1
FURL=$(docker exec tahoe-introducer cat /tahoe-introducer/private/introducer.furl)
echo "fURL is" $FURL

echo "creating storage nodes"
docker build --rm --tag tahoe-storage0 --build-arg furl=${FURL} --build-arg nick=storage0 docker-storage/
docker build --rm --tag tahoe-storage1 --build-arg furl=${FURL} --build-arg nick=storage1 docker-storage/
docker run --name tahoe-storage0 -h storage0 -P -d --link tahoe-introducer:introducer tahoe-storage0
docker run --name tahoe-storage1 -h storage0 -P -d --link tahoe-introducer:introducer tahoe-storage1

echo "done."
echo "introducer address (web-api on :4560)"
docker inspect tahoe-introducer | grep IPAddress
echo "introducer fURL:"
docker exec tahoe-introducer cat /tahoe-introducer/private/introducer.furl

docker inspect tahoe-storage0 | grep IPAddress
docker inspect tahoe-storage1 | grep IPAddress
