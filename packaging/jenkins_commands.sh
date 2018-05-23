#!/bin/bash
# Code to be executed within jenkins for packaging jobs
find ${WORKSPACE} -name *.pyc -exec rm {} \;
find ${WORKSPACE} -name .coverage -exec rm {} \;

PYTHONPATH=:${WORKSPACE}
cd ${WORKSPACE}
ARGS="--product=""${product}"" --release=""${release}"
if [ "${artifact_only}" == "true" ]
then
  ARGS="${ARGS} --artifact-only"
fi
if [ "${no_upload}" == "true" ]
then
  ARGS="${ARGS} --no-upload"
fi
if [ "${dry_run}" == "true" ]
then
  ARGS="${ARGS} --dry-run"
fi
if [ "${pip}" == "true" ]
then
  ARGS="${ARGS} --pip"
fi
if [ -n "${revision}" ] ; then
  ARGS="${ARGS} --revision=""${revision}"" --hotfix-release=""${hotfix_release}"
fi

bash packaging/docker/install_docker.sh ${ARGS}

echo "Packaging complete"
