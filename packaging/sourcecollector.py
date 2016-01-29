# Copyright 2014 iNuron NV
#
# Licensed under the Open vStorage Modified Apache License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/license
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
SourceCollector module
"""

import os
import re
import time
import json
from datetime import datetime
from subprocess import check_output


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
    def collect(product, release=None, revision=None, suffix=None):
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
        * 'experimental': packages the given revision, or whatever is in the code repo if no revision was given
        * 'master': package master (unstable)
        * all others: package from the branch named after the release
        @param revision: Specifies an exact revision
        * If the revision parameter is specified, the only valid release is 'experimental'.
        * If release is None, the release will be loaded form the specified revision
        @param suffix: An optional suffix for releases different from 'experimental' and 'master'
        * If none given, the release will be used as suffix
        """

        settings = SourceCollector.json_loads('{0}/{1}'.format(os.path.dirname(os.path.realpath(__file__)), 'settings.json'))
        repository = settings['repositories']['code'][product]
        working_directory = settings['base_path'].format(product)
        repo_path_code = SourceCollector.repo_path_code.format(working_directory)
        repo_path_metadata = SourceCollector.repo_path_metadata.format(working_directory)
        package_path = SourceCollector.package_path.format(working_directory)

        print 'Validating input parameters'
        if revision is not None:
            if release not in [None, 'experimental']:
                raise ValueError('If a revision is given, the release should either be empty or \'experimental\'')
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
        known_branches = []
        for branch in SourceCollector.run(command='git branch -r',
                                          working_directory=repo_path_metadata).splitlines():
            if 'origin/HEAD' in branch:
                continue
            known_branches.append(branch.strip().replace('origin/', ''))
        if release not in [None, 'experimental'] and release not in known_branches:
            raise ValueError('Unknown release')

        if release != 'experimental' or revision is not None:
            SourceCollector._git_checkout_to(path=repo_path_code,
                                             revision=release if revision is None else revision,
                                             repo=repository)
            if release != 'experimental' and revision is not None:
                release = SourceCollector.run(command='git branch | grep "*"',
                                              working_directory=repo_path_code).strip().lstrip('* ')
                if release not in settings['releases']:
                    raise ValueError('Release {0} is invalid. Should be in {1}'.format(settings['releases']))

        # Get parent branches
        branches = ['master']
        if release not in [None, 'experimental', 'master']:
            branches.append(release)

        # Get suffix
        if release == 'experimental':
            suffix = 'exp'
        elif release == 'master':
            suffix = 'rev'
        elif suffix is None:
            suffix = release

        # Get current revision and date
        print '  Fetch current revision'
        revision_number = SourceCollector.run(command='git rev-list HEAD | wc -l',
                                              working_directory=repo_path_code).strip()
        revision_hash, revision_date = SourceCollector.run(command='git show HEAD --pretty --format="%h|%at" -s',
                                                           working_directory=repo_path_code).strip().split('|')
        if revision is not None:
            if revision_hash != revision:
                raise RuntimeError('Could not match requested hash. Got {0}, expected {1}'.format(revision_hash, revision))
        revision_date = datetime.fromtimestamp(float(revision_date))
        current_revision = '{0}.{1}'.format(revision_number, revision_hash)
        print '    Revision: {0}'.format(current_revision)

        # Build version
        code_settings = SourceCollector.json_loads('{0}/packaging/settings.json'.format(repo_path_code))
        version = '{0}.{1}.{2}'.format(code_settings['version']['major'],
                                       code_settings['version']['minor'],
                                       code_settings['version']['patch'])
        print '  Version: {0}'.format(version)

        # Load tag information
        tag_data = []
        print '  Loading tags'
        for raw_tag in SourceCollector.run(command='git show-ref --tags',
                                           working_directory=repo_path_metadata).splitlines():
            parts = raw_tag.strip().split(' ')
            rev_hash = parts[0]
            tag = parts[1].replace('refs/tags/', '')
            match = re.search('^(?P<version>[0-9]+?\.[0-9]+?\.[0-9]+?)(-(?P<suffix>.+)\.(?P<build>[0-9]+))?$', tag)
            if match:
                match_dict = match.groupdict()
                tag_version = match_dict['version']
                tag_build = match_dict['build']
                tag_suffix = match_dict['suffix']
                tag_data.append({'version': tag_version,
                                 'build': int(tag_build),
                                 'suffix': tag_suffix,
                                 'rev_hash': rev_hash})

        # Build changelog
        increment_build = True
        changes_found = False
        other_changes = False
        changelog = []
        if release not in ['experimental', 'master']:
            print '  Generating changelog'
            changelog.append(code_settings['product_name'])
            changelog.append('=============')
            changelog.append('')
            changelog.append('This changelog is generated based on DVCS. Due to the nature of DVCS the')
            changelog.append('order of changes in this document can be slightly different from reality.')
            changelog.append('')
            log = SourceCollector.run(command='git --no-pager log origin/{0} --date-order --pretty --format="%at|%H|%s"'.format(release),
                                      working_directory=repo_path_code)
            for log_line in log.strip().splitlines():
                if 'Added tag ' in log_line and ' for changeset ' in log_line:
                    continue

                timestamp, log_hash, description = log_line.split('|')
                try:
                    description.encode('ascii')
                except UnicodeDecodeError:
                    continue
                log_date = datetime.fromtimestamp(float(timestamp))
                active_tag = None
                for tag in tag_data:
                    if tag['rev_hash'] == log_hash and tag['suffix'] >= suffix:
                        active_tag = tag
                if active_tag is not None:
                    if changes_found is False:
                        increment_build = False
                    if other_changes is True:
                        changelog.append('* Internal updates')
                    changelog.append('\n{0}{1}\n'.format(active_tag['version'],
                                                         '-{0}.{1}'.format(active_tag['suffix'], active_tag['build']) if active_tag['suffix'] is not None else ''))
                    other_changes = False
                if re.match('^OVS\-[0-9]{1,5}', description):
                    changelog.append('* {0} - {1}'.format(log_date.strftime('%Y-%m-%d'), description))
                else:
                    other_changes = True
                changes_found = True
            if other_changes is True:
                changelog.append('* Other internal updates')

        # Build buildnumber
        print '  Generating build'
        if release == 'experimental':
            build = int(time.time())
        elif release == 'master':
            build = current_revision
        else:
            builds = sorted(tag['build'] for tag in tag_data if tag['version'] == version and tag['suffix'] == suffix)
            if len(builds) > 0:
                build = builds[-1]
                if revision is None and increment_build is True:
                    build += 1
                else:
                    print '    No need to increment build'
            else:
                build = 1
        print '    Build: {0}'.format(build)

        # Save changelog
        if len(changelog) > 0:
            if increment_build is True:
                changelog.insert(5, '\n{0}{1}\n'.format(version, '-{0}.{1}'.format(suffix, build) if suffix is not None else ''))
        with open('{0}/CHANGELOG.txt'.format(repo_path_code), 'w') as changelog_file:
            changelog_file.write('\n'.join(changelog))

        # Version string. Examples:
        # * Experimental build
        #     1.2.0-exp.<timestamp>
        # * Master branch
        #     1.2.0-rev.<revision>
        # * Other branches (releases)
        #     1.2.0-<release>.<build>

        version_string = '{0}{1}'.format(version, '-{0}.{1}'.format(suffix, build) if suffix is not None else '')
        print '  Full version: {0}'.format(version_string)

        # Tag revision
        if release not in ['experimental', 'master'] and revision is None and increment_build is True:
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

        if release in settings['branch_map']:
            release = settings['branch_map'][release]
        return product, release, version_string, revision_date, code_settings['package_name']

    @staticmethod
    def _git_checkout_to(path, revision, repo):
        """
        Updates a given repo to a certain revision, cloning if it does not exist yet
        """
        if not os.path.exists('{0}/.git'.format(path)):
            SourceCollector.run('git clone {0} {1}'.format(repo, path), path)
        SourceCollector.run('git pull --all --prune', path)
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
            os.chdir(working_directory)
            return check_output(command, shell=True)

    @staticmethod
    def json_loads(path):
        """
        Loads json from a path
        """
        with open(path, 'r') as config_file:
            return json.loads(config_file.read())
