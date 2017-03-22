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
    * Versioning metadata
    * Full changelog
    It will also update the repo with all required versioning tags, if appropriate
    """

    package_path = '{0}/package'
    repo_path_code = '{0}/code'
    repo_path_metadata = '{0}/metadata'

    def __init__(self):
        """
        Dummy init method, SourceCollector is static
        """
        raise NotImplementedError('SourceCollector is a static class')

    @staticmethod
    def collect(product, release=None, revision=None):
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
        """

        settings = SourceCollector.json_loads('{0}/{1}'.format(os.path.dirname(os.path.realpath(__file__)), 'settings.json'))
        repository = settings['repositories']['code'][product]
        working_directory = settings['base_path'].format(product)
        repo_path_code = SourceCollector.repo_path_code.format(working_directory)
        repo_path_metadata = SourceCollector.repo_path_metadata.format(working_directory)
        package_path = SourceCollector.package_path.format(working_directory)

        print 'Validating input parameters'
        if revision is not None:
            if release not in ['experimental', 'hotfix']:
                raise ValueError('If a revision is given, the release should be \'experimental\' or \'hotfix\'')
        elif release in ['experimental', 'hotfix']:
            raise ValueError('The \'experimental\' and \'hotfix\' releases must have a revision')
        if release is not None and release not in settings['releases']:
            raise ValueError('Release {0} is invalid. Should be in {1}'.format(release, settings['releases']))

        print 'Collecting sources'
        for directory in [repo_path_code, repo_path_metadata, package_path]:
            if not os.path.exists(directory):
                os.makedirs(directory)

        # Update the metadata repo
        print '  Updating metadata'
        SourceCollector._git_checkout_to(path=repo_path_metadata,
                                         revision='master',
                                         repo=repository)
        SourceCollector._git_checkout_to(path=repo_path_code,
                                         revision=release if revision is None else revision,
                                         repo=repository)

        # Get current revision and date
        print '  Fetch current revision'
        revision_hash, revision_date = SourceCollector.run(command='git show HEAD --pretty --format="%h|%at" -s',
                                                           working_directory=repo_path_code).strip().split('|')
        revision_date = datetime.fromtimestamp(float(revision_date))
        print '    Revision: {0}'.format(revision_hash)

        # Build version
        code_settings = SourceCollector.json_loads('{0}/packaging/settings.json'.format(repo_path_code))
        destination_tags = code_settings.get('tags', [])
        version = '{0}.{1}'.format(code_settings['version']['major'],
                                   code_settings['version']['minor'])
        print '  Version: {0}'.format(version)

        # Load tag information
        tag_data = []
        print '  Loading tags'
        for raw_tag in SourceCollector.run(command='git show-ref --tags',
                                           working_directory=repo_path_metadata).splitlines():
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
        if release in ['master', 'hotfix']:
            print '  Generating changelog'
            changelog.append(code_settings['product_name'])
            changelog.append('===============')
            changelog.append('')
            changelog.append('For the full changelog, see https://github.com/openvstorage')
            changelog.append('')
            log_target = 'master' if release == 'master' else revision
            log = SourceCollector.run(command='git --no-pager log origin/{0} --date-order --pretty --format="%at|%H|%s"'.format(log_target),
                                      working_directory=repo_path_code)
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

        # Build buildnumber
        print '  Generating build'
        builds = sorted(tag['build'] for tag in tag_data if tag['version'] == version)
        if len(builds) > 0:
            build = builds[-1]
            if (revision is None or release == 'hotfix') and increment_build is True:
                build += 1
            else:
                print '    No need to increment build'
        else:
            build = 0
        print '    Build: {0}'.format(build)

        suffix = None
        if release in ['develop', 'experimental']:
            suffix = 'dev.{0}.{1}'.format(int(time.time()), revision_hash)

        # Save changelog
        if len(changelog) > 0:
            if increment_build is True:
                changelog.append('\n{0}.{1}{2}\n'.format(version, build, '-{0}'.format(suffix) if suffix is not None else ''))
        with open('{0}/CHANGELOG.txt'.format(repo_path_code), 'w') as changelog_file:
            changelog_file.write('\n'.join(changelog))

        version_string = '{0}.{1}{2}'.format(version, build, '-{0}'.format(suffix) if suffix is not None else '')
        print '  Full version: {0}'.format(version_string)

        # Tag revision
        if release in ['master', 'hotfix'] and increment_build is True:
            print '  Tagging revision'
            SourceCollector.run(command='git tag -a {0} {1} -m "Added tag {0} for changeset {1}"'.format(version_string, revision_hash),
                                working_directory=repo_path_metadata)
            SourceCollector.run(command='git push origin --tags',
                                working_directory=repo_path_metadata)

        # Building archive
        print '  Building archive'
        SourceCollector.run(command="tar -czf {0}/{1}_{2}.tar.gz {3}".format(package_path,
                                                                             code_settings['package_name'],
                                                                             version_string,
                                                                             code_settings['source_contents'].format(
                                                                                 code_settings['package_name'],
                                                                                 version_string)
                                                                             ),
                            working_directory=repo_path_code)
        SourceCollector.run(command='rm -f CHANGELOG.txt',
                            working_directory=repo_path_code)
        print '    Archive: {0}/{1}_{2}.tar.gz'.format(package_path, code_settings['package_name'], version_string)
        print 'Done'

        if release == 'hotfix':
            release = 'master'
        if release in settings['branch_map']:
            release = settings['branch_map'][release]
        return product, release, version_string, revision_date, code_settings['package_name'], destination_tags

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
    def run(command, working_directory, print_only=False):
        """
        Runs a comment, returning the output
        """
        if print_only is True:
            print command
        else:
            cur_dir = os.getcwd()
            os.chdir(working_directory)
            try:
                return check_output(command, shell=True)
            except CalledProcessError as cpe:
                # CalledProcessError doesn't include the output in its __str__
                #  making debug harder
                raise RuntimeError('{0}. \n Output: \n {1} \n'.format(cpe, cpe.output))
            finally:
                # return to previous directory, easier to test interactive
                os.chdir(cur_dir)

    @staticmethod
    def json_loads(path):
        """
        Loads json from a path
        """
        with open(path, 'r') as config_file:
            return json.loads(config_file.read())
