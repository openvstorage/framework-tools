# Copyright (C) 2016 iNuron NV
#
# This file is part of Open vStorage Open Source Edition (OSE),
# as available from
#
#      http://www.openvstorage.org and
#      http://www.openvstorage.com.
#
# This file is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License v3 (GNU AGPLv3)
# as published by the Free Software Foundation, in version 3 as it comes
# in the LICENSE.txt file of the Open vStorage OSE distribution.
#
# Open vStorage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY of any kind.

"""
SourceCollector module
"""

import os
import re
import time
import json
from datetime import datetime
from subprocess import check_output, CalledProcessError


class SourceCollector(object):
    """
    SourceCollector class

    Responsible for creating a source archive which will contain:
    * All sources for that version
    * Metadata regarding the version
    * Full changelog
    It will also update the repo with all required version tags, if appropriate
    """
    path_code = '{0}/code'
    path_package = '{0}/package'
    path_metadata = '{0}/metadata'

    def __init__(self):
        """
        Dummy init method, SourceCollector is static
        """
        raise NotImplementedError('SourceCollector is a static class')

    @staticmethod
    def get_settings():
        """
        Retrieves the current settings
        :return: Settings dict
        :rtype: dict
        """
        return SourceCollector.json_loads('{0}/{1}'.format(os.path.dirname(os.path.realpath(__file__)), 'settings.json'))

    @classmethod
    def get_paths(cls, product, settings=None):
        """
        Returns the working directory, path to the code, path to the package and path to the metadata
        :param product: Product to process
        :param settings: Settings to use, defaults to the provided settings in the settings.json
        :return:
        """
        if settings is None:
            settings = cls.get_settings()
        working_directory = settings['base_path'].format(product)
        path_code = SourceCollector.path_code.format(working_directory)
        path_package = SourceCollector.path_package.format(working_directory)
        path_metadata = SourceCollector.path_metadata.format(working_directory)
        return working_directory, path_code, path_package, path_metadata

    @classmethod
    def collect(cls, product, release=None, revision=None, artifact_only=False):
        """
        Executes the source collecting logic

        General steps:
        1. Figure out correct code revision, update code repo to that revision
        2. Tag that revision, if required
        3. Generate changelog, if required
        4. Generate version schema
        5. Build 'upstream source package'
        6. Use this 'upstream source package' for building distribution specific packages

        @param product: The product that needs to be packaged
        @param release: The releasename that needs to be packaged
        * 'develop': package develop branch
        * 'experimental': packages the given revision. The revision parameter must be passed
        * 'master': package master
        * 'hotfix': packages the given revision, but treat it like a release package (aka like master)
        @param revision: Specifies an exact revision
        * If the revision parameter is specified, the only valid releases are 'experimental' and 'hotfix'.
        @param artifact_only: Specifies whether the package should only be built and not uploaded.
        * The package name will contain a commit hash to distinguish different builds
        """
        print 'Validating input parameters'
        settings = cls.get_settings()
        if revision is not None:
            if release not in ['experimental', 'hotfix']:
                raise ValueError('If a revision is given, the release should be \'experimental\' or \'hotfix\'')
        elif release in ['experimental', 'hotfix']:
            raise ValueError('The \'experimental\' and \'hotfix\' releases must have a revision')
        if release is not None and release not in settings['releases']:
            raise ValueError('Release {0} is invalid. Should be in {1}'.format(release, settings['releases']))

        working_directory, path_code, path_package, path_metadata = cls.get_paths(product, settings)
        print 'Working directory: {0}'.format(working_directory)

        print 'Collecting sources'
        for directory in [path_code, path_metadata, path_package]:
            if not os.path.exists(directory):
                print 'Creating directory {0}'.format(directory)
                os.makedirs(directory)

        # Update the metadata repo
        print 'Updating metadata'
        repository = settings['repositories']['code'][product]
        print 'Checking out master at {0}'.format(path_metadata)
        SourceCollector._git_checkout_to(path=path_metadata,
                                         revision='master',
                                         repo=repository)
        print 'Checking out {0} at {1}'.format(release if revision is None else revision, path_code)
        SourceCollector._git_checkout_to(path=path_code,
                                         revision=release if revision is None else revision,
                                         repo=repository)

        # Get current revision and date
        print 'Fetch current revision'
        revision_hash, revision_date = SourceCollector.run(command='git show HEAD --pretty --format="%h|%at" -s',
                                                           working_directory=path_code).strip().split('|')
        revision_date = datetime.fromtimestamp(float(revision_date))
        print 'Revision hash: {0}'.format(revision_hash)
        print 'Revision date: {0}'.format(revision_date)

        # Build version
        code_settings = SourceCollector.json_loads('{0}/packaging/settings.json'.format(path_code))
        version = '{0}.{1}'.format(code_settings['version']['major'],
                                   code_settings['version']['minor'])
        print 'Version: {0}'.format(version)

        # Load tag information
        tag_data = []
        print 'Loading tags'
        for raw_tag in SourceCollector.run(command='git show-ref --tags',
                                           working_directory=path_metadata).splitlines():
            parts = raw_tag.strip().split(' ')
            rev_hash = parts[0]
            tag = parts[1].replace('refs/tags/', '')
            match = re.search('^(?P<version>[0-9]+?\.[0-9]+?)\.(?P<build>[0-9]+?)([-.](.+))?$', tag)
            if match:
                match_dict = match.groupdict()
                tag_version = match_dict['version']
                tag_build = match_dict['build']
                tag_data.append({'version': tag_version,   # 2.7  \__ 2.7.8
                                 'build': int(tag_build),  # 8    /
                                 'rev_hash': rev_hash})

        # Build changelog
        increment_build = True
        changes_found = False
        changelog = []
        if release in ['master', 'hotfix'] and artifact_only is False:
            print 'Generating changelog'
            changelog.append(code_settings['product_name'])
            changelog.append('===============')
            changelog.append('')
            changelog.append('For the full changelog, see https://github.com/openvstorage')
            changelog.append('')
            log_target = 'master' if release == 'master' else revision
            log = SourceCollector.run(command='git --no-pager log origin/{0} --date-order --pretty --format="%at|%H|%s"'.format(log_target),
                                      working_directory=path_code)
            for log_line in log.strip().splitlines():
                if 'Added tag ' in log_line and ' for changeset ' in log_line:
                    continue

                timestamp, log_hash, description = log_line.split('|', 2)
                try:
                    description.encode('ascii')
                except UnicodeDecodeError:
                    continue
                active_tag = None
                for tag in tag_data:
                    if tag['rev_hash'] == log_hash:
                        active_tag = tag
                if active_tag is not None:
                    if changes_found is False:
                        increment_build = False
                changes_found = True

        # Build build_number
        print 'Generating build'
        builds = sorted(tag['build'] for tag in tag_data if tag['version'] == version)
        if len(builds) > 0:
            build = builds[-1]
            if (revision is None or release == 'hotfix') and increment_build is True:
                build += 1
            else:
                print 'No need to increment build'
        else:
            build = 0
        print 'Build: {0}'.format(build)

        suffix = None
        # Generate a suffix for artifact-only builds or develop/experimental builds to distinguish them from release builds
        if release in ['develop', 'experimental'] or artifact_only is True:
            print 'Generating a suffix'
            suffix = 'dev.{0}.{1}'.format(int(time.time()), revision_hash)

        # Save changelog
        print 'Writing CHANGELOG file'
        if len(changelog) > 0:
            if increment_build is True:
                changelog.append('\n{0}.{1}{2}\n'.format(version, build, '-{0}'.format(suffix) if suffix is not None else ''))
        with open('{0}/CHANGELOG.txt'.format(path_code), 'w') as changelog_file:
            changelog_file.write('\n'.join(changelog))

        version_string = '{0}.{1}{2}'.format(version, build, '-{0}'.format(suffix) if suffix is not None else '')
        print 'Full version: {0}'.format(version_string)

        # Tag revision
        if release in ['master', 'hotfix'] and increment_build is True and artifact_only is False:
            print 'Tagging revision'
            SourceCollector.run(command='git tag -a {0} {1} -m "Added tag {0} for changeset {1}"'.format(version_string, revision_hash),
                                working_directory=path_metadata)
            SourceCollector.run(command='git push origin --tags',
                                working_directory=path_metadata)

        # Building archive
        print 'Building archive'
        SourceCollector.run(command="tar -czf {0}/{1}_{2}.tar.gz {3}".format(path_package,
                                                                             code_settings['package_name'],
                                                                             version_string,
                                                                             code_settings['source_contents'].format(
                                                                                 code_settings['package_name'],
                                                                                 version_string)
                                                                             ),
                            working_directory=path_code)
        SourceCollector.run(command='rm -f CHANGELOG.txt',
                            working_directory=path_code)
        print 'Archive: {0}/{1}_{2}.tar.gz'.format(path_package, code_settings['package_name'], version_string)
        print 'Done'

        if release == 'hotfix':
            release = 'master'
        if release in settings['branch_map']:
            release = settings['branch_map'][release]
        return product, release, version_string, revision_date, code_settings['package_name'], code_settings.get('tags', [])

    @staticmethod
    def _git_checkout_to(path, revision, repo):
        """
        Updates a given repo to a certain revision, cloning if it does not exist yet
        """
        if not os.path.exists('{0}/.git'.format(path)):
            SourceCollector.run('git clone {0} {1}'.format(repo, path), path)
        SourceCollector.run('git pull --all --prune || true', path)
        SourceCollector.run('git checkout {0}'.format(revision), path)
        SourceCollector.run('git pull --prune', path)
        SourceCollector.run('git fetch --tags', path)

    @staticmethod
    def run(command, working_directory, print_only=False, debug=True):
        """
        Runs a comment, returning the output
        """
        if print_only is True:
            print command
        else:
            if debug is True:
                print command
            try:
                return check_output(command, shell=True, cwd=working_directory)
            except CalledProcessError as cpe:
                # CalledProcessError doesn't include the output in its __str__
                #  making debug harder
                raise RuntimeError('{0}. \n Output: \n {1} \n'.format(cpe, cpe.output))

    @staticmethod
    def json_loads(path):
        """
        Loads json from a path
        """
        with open(path, 'r') as config_file:
            return json.loads(config_file.read())
