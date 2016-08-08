#!/bin/bash

# XXX mostly just notes? this will blow away and re-start the
# docker-ized storage cluster

# huzzah! it works!

# there's one manual step though! when you create the introducer, we
# still have to manually copy the introducer-fURL from it to the
# storage-server

echo "building dist"
python setup.py sdist || exit $?
# kinda-bad; hopefully we've installed this in our "current" venv??
LATEST=$(python -c "import allmydata; print allmydata.__version__")
cp dist/tahoe-lafs-${LATEST}.tar.gz docker-introducer/tahoe-lafs.tar.gz
cp dist/tahoe-lafs-${LATEST}.tar.gz docker-storage/tahoe-lafs.tar.gz
cp dist/tahoe-lafs-${LATEST}.tar.gz docker-client/tahoe-lafs.tar.gz


echo "--------------------------------------------------------------------------------"
echo "nuking existing containers"
echo

docker rm -f tahoe-introducer
docker rm -f tahoe-storage0
docker rm -f tahoe-storage1
docker rm -f tahoe-alice
docker rm -f tahoe-bob


echo "--------------------------------------------------------------------------------"
echo "creating introducer"
echo

docker build --rm --tag tahoe-introducer docker-introducer/ || exit $?
docker run --name tahoe-introducer -h introducer0 -P -d tahoe-introducer || exit $?
echo "...waiting"
sleep 1
FURL=$(docker exec tahoe-introducer cat /tahoe-introducer/private/introducer.furl)
echo "fURL is" $FURL


echo "--------------------------------------------------------------------------------"
echo "creating storage nodes"
echo

docker build --rm --tag tahoe-storage0 --build-arg furl=${FURL} --build-arg nick=storage0 docker-storage/
docker build --rm --tag tahoe-storage1 --build-arg furl=${FURL} --build-arg nick=storage1 docker-storage/
docker run --name tahoe-storage0 -h storage0 -P -d --link tahoe-introducer:introducer tahoe-storage0
docker run --name tahoe-storage1 -h storage0 -P -d --link tahoe-introducer:introducer tahoe-storage1

echo "--------------------------------------------------------------------------------"
echo "create client nodes"
echo

docker build --rm --tag tahoe-alice --build-arg furl=${FURL} --build-arg nick=alice docker-client/
docker build --rm --tag tahoe-bob --build-arg furl=${FURL} --build-arg nick=bob docker-client/
docker run --name tahoe-alice -h alice -P -d --link tahoe-introducer:introducer tahoe-alice
docker run --name tahoe-bob -h bob -P -d --link tahoe-introducer:introducer tahoe-bob

echo "--------------------------------------------------------------------------------"
echo "alice creates a magic-folder, invites bob"
echo

docker exec tahoe-alice /tahoevenv/bin/tahoe -d /tahoe-client magic-folder create magic: alice /magic
INVITE=$(docker exec tahoe-alice /tahoevenv/bin/tahoe -d /tahoe-client magic-folder invite magic: bob)
docker exec tahoe-bob /tahoevenv/bin/tahoe -d /tahoe-client magic-folder join $INVITE /magic

#docker cp README.rst tahoe-alice:/magic/README.rst


echo "--------------------------------------------------------------------------------"
echo "done."
echo
echo "introducer address (web-api on :4560)"
docker inspect tahoe-introducer | grep IPAddress
echo "introducer fURL:"
docker exec tahoe-introducer cat /tahoe-introducer/private/introducer.furl

docker inspect tahoe-storage0 | grep IPAddress
docker inspect tahoe-storage1 | grep IPAddress
docker inspect tahoe-alice | grep IPAddress
docker inspect tahoe-bob | grep IPAddress
