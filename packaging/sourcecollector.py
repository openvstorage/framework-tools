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

    def __init__(self, product, release=None, revision=None, artifact_only=False):
        """
        Initializes a source collector
        :param product: The product that needs to be packaged
        :param release: The release name that needs to be packaged
        * 'develop': package develop branch
        * 'experimental': packages the given revision. The revision parameter must be passed
        * 'master': package master
        * 'hotfix': packages the given revision, but treat it like a release package (aka like master)
        :param revision: Specifies an exact revision (coincides with a specific branch)
        * If the revision parameter is specified, the only valid releases are 'experimental' and 'hotfix'.
        :param artifact_only: Specifies whether the package should only be built and not uploaded.
        * The package name will contain a commit hash to distinguish different builds
        """
        print 'Validating input parameters'
        settings = self.get_settings()
        if revision is not None:
            if release not in ['experimental', 'hotfix']:
                raise ValueError('If a revision is given, the release should be \'experimental\' or \'hotfix\'')
        elif release in ['experimental', 'hotfix']:
            raise ValueError('The \'experimental\' and \'hotfix\' releases must have a revision')
        if release is not None and release not in settings['releases']:
            raise ValueError('Release {0} is invalid. Should be in {1}'.format(release, settings['releases']))

        self.product = product
        self.release = release
        self.release_repo = None  # Release repo to upload the package to
        self.revision = revision
        self.artifact_only = artifact_only

        self.settings = settings
        self.repository = self.settings['repositories']['code'][product]
        # Set some pathing information
        self.working_directory = self.settings['base_path'].format(self.product)
        self.path_code = self.path_code.format(self.working_directory)
        self.path_package = self.path_package.format(self.working_directory)
        self.path_metadata = self.path_metadata.format(self.working_directory)

        ####################################
        # Set when data has been collected #
        ####################################
        # Source collection
        self.code_settings = None  # settings.json fetched from the repository
        self.version = None  # Version of the package the build (found in settings.jon on the repository)
        self.package_name = None  # Name of the package to build (found in settings.jon on the repository)
        self.tags = None  # Tags for the package to build (found in settings.json on the repository)
        self.revision_hash = None  # Revision hash of the repository
        self.revision_date = None  # Revision data of the repository
        self.tag_data = None  # Tag data of the repository
        # Build related data
        self.changelog = None  # Contents for the changelog file
        self.increment_build = True  # Flag if the build should be incremented (building the changelog might set this to False)

        self.version_string = None
        self.metadata = None

        self._create_destination_directories()

    @staticmethod
    def get_settings():
        """
        Retrieves the current settings
        :return: Settings dict
        :rtype: dict
        """
        return SourceCollector.json_loads('{0}/{1}'.format(os.path.dirname(os.path.realpath(__file__)), 'settings.json'))

    def collect(self):
        """
        Executes the source collecting logic
        General steps:
        1. Figure out correct code revision, update code repo to that revision
        2. Tag that revision, if required
        3. Generate changelog, if required
        4. Generate version schema
        5. Build 'upstream source package'
        6. Use this 'upstream source package' for building distribution specific packages
        """
        print 'Working directory: {0}'.format(self.working_directory)

        # Collect all information about the source
        self._collect_sources()
        # Build changelog
        self._build_changelog()
        # Generate a version string
        self._generate_version_string()
        # Save changelog
        self._write_changelog()
        # Tag revision
        self._tag_revision()
        # Building archive
        self._build_archive()
        # Get the repository to push too
        self._get_release_repo()
        return self.product, self.release_repo, self.version_string, self.revision_date, self.code_settings['package_name'], self.code_settings.get('tags', [])

    def _create_destination_directories(self):
        """
        Creates all directories required for the SourceCollector/packager
        :return: None
        :rtype: NoneType
        """
        print 'Creating the required directories'
        for directory in [self.path_code, self.path_metadata, self.path_package]:
            if not os.path.exists(directory):
                print 'Creating directory {0}'.format(directory)
                os.makedirs(directory)

    def _get_release_repo(self):
        """
        Get the repository to push the would-be packages to
        :return: The name of the repository
        :rtype: str
        """
        # Get the repository to push too
        release = self.release
        # Hotfix has to be uploaded to Unstable (unless the hotfix release has been given)
        if release == 'hotfix':
            release = 'master'
        if release in self.settings['branch_map']:
            self.release_repo = self.settings['branch_map'][release]
        else:
            # Should not happen
            print 'Mapping release to a release repository was not possible. Setting the release repo to the specified release ({0})'.format(self.release)
            self.release_repo = self.release
        return self.release_repo

    def _build_archive(self):
        """
        Build a tar archive of the repository
        :return: None
        :rtype: NoneType
        """
        # Validation
        if self.code_settings is None:
            raise RuntimeError('Sources have not yet been collected')
        if self.version_string is None:
            raise RuntimeError('Version string has not been generated')

        print 'Building archive'
        SourceCollector.run(command="tar -czf {0}/{1}_{2}.tar.gz {3}".format(self.path_package,
                                                                             self.code_settings['package_name'],
                                                                             self.version_string,
                                                                             self.code_settings['source_contents'].format(self.code_settings['package_name'], self.version_string)),
                            working_directory=self.path_code)
        SourceCollector.run(command='rm -f CHANGELOG.txt',
                            working_directory=self.path_code)
        print 'Archive: {0}/{1}_{2}.tar.gz'.format(self.path_package, self.code_settings['package_name'], self.version_string)
        print 'Done'

    def _collect_sources(self):
        """
        Collect data about the repository
        - Checkout the latest code
        - Checkout the requested release
        - Collects revision data
        - Build the version string
        - Loads in all tag data
        :return: Returns the revision data and version
        :rtype: tuple(str, str str)
        """
        print 'Collecting sources'

        # Update the metadata repo
        print 'Updating metadata'
        print 'Checking out master at {0}'.format(self.path_metadata)
        SourceCollector._git_checkout_to(path=self.path_metadata,
                                         revision='master',
                                         repo=self.repository)
        print 'Checking out {0} at {1}'.format(self.release if self.revision is None else self.revision, self.path_code)
        SourceCollector._git_checkout_to(path=self.path_code,
                                         revision=self.release if self.revision is None else self.revision,
                                         repo=self.repository)
        self.checked_out = True
        # Get current revision and date
        print 'Fetch current revision'
        revision_hash, revision_date = SourceCollector.run(command='git show HEAD --pretty --format="%h|%at" -s',
                                                           working_directory=self.path_code).strip().split('|')
        self.revision_hash = revision_hash
        self.revision_date = datetime.fromtimestamp(float(revision_date))
        print 'Revision hash: {0}'.format(self.revision_hash)
        print 'Revision date: {0}'.format(self.revision_date)

        # Build version
        self.code_settings = SourceCollector.json_loads('{0}/packaging/settings.json'.format(self.path_code))
        self.version = '{0}.{1}'.format(self.code_settings['version']['major'], self.code_settings['version']['minor'])
        print 'Version: {0}'.format(self.version)

        # Load tag information
        self.tag_data = []
        print 'Loading tags'
        for raw_tag in SourceCollector.run(command='git show-ref --tags',
                                           working_directory=self.path_metadata).splitlines():
            parts = raw_tag.strip().split(' ')
            rev_hash = parts[0]
            tag = parts[1].replace('refs/tags/', '')
            match = re.search('^(?P<version>[0-9]+?\.[0-9]+?)\.(?P<build>[0-9]+?)([-.](.+))?$', tag)
            if match:
                match_dict = match.groupdict()
                tag_version = match_dict['version']
                tag_build = match_dict['build']
                self.tag_data.append({'version': tag_version,  # 2.7  \__ 2.7.8
                                      'build': int(tag_build),  # 8   /
                                      'rev_hash': rev_hash})
        return self.revision_hash, self.revision_date, self.version, self.tag_data

    def _tag_revision(self):
        """
        Create tags for the current repository
        Tags will only be created when:
        - It is not an arifact-only build
        - The release is either hotfix/master
        - The build should be incremented (changes detected)
        :return: None
        :rtype: NoneType
        """
        # Validation
        if self.version_string is None:
            # Version string needs the revision hash, so not validating this here
            raise RuntimeError('Version string has not been generated')

        if self.release in ['master', 'hotfix'] and self.increment_build is True and self.artifact_only is False:
            print 'Tagging revision'
            SourceCollector.run(command='git tag -a {0} {1} -m "Added tag {0} for changeset {1}"'.format(self.version_string, self.revision_hash),
                                working_directory=self.path_metadata)
            SourceCollector.run(command='git push origin --tags',
                                working_directory=self.path_metadata)

    def _build_changelog(self):
        """
        Generates changelog file contents that will be included in the package
        The normal flow will only build changelogs when the release is either master or hotfix (as these packages would be uploaded)
        :return: The contents of the file, whether changes were found, whether the build number should be incremented
        :rtype: tuple(list[str], bool, bool)
        """
        if any(item is None for item in [self.tag_data, self.code_settings]):
            raise RuntimeError('Sources have not yet been collected')
        increment_build = True
        changes_found = False
        changelog = []
        if self.release in ['master', 'hotfix']:
            print 'Generating changelog'
            changelog.append(self.code_settings['product_name'])
            changelog.append('===============')
            changelog.append('')
            changelog.append('For the full changelog, see https://github.com/openvstorage')
            changelog.append('')
            log_target = 'master' if self.release == 'master' else self.revision
            log = SourceCollector.run(command='git --no-pager log origin/{0} --date-order --pretty --format="%at|%H|%s"'.format(log_target),
                                      working_directory=self.path_code)
            for log_line in log.strip().splitlines():
                if 'Added tag ' in log_line and ' for changeset ' in log_line:
                    continue

                timestamp, log_hash, description = log_line.split('|', 2)
                try:
                    description.encode('ascii')
                except UnicodeDecodeError:
                    continue
                active_tag = None
                for tag in self.tag_data:
                    if tag['rev_hash'] == log_hash:
                        active_tag = tag
                if active_tag is not None:
                    if changes_found is False:
                        increment_build = False
                changes_found = True

        self.changelog = changelog
        self.increment_build = increment_build

        return changelog, changes_found, increment_build

    def _write_changelog(self):
        """
        Writes away the changelog
        - Will add an extra line when the build should have been incremented
        :return:
        """
        # Validation
        if any(item is None for item in [self.changelog]):
            raise RuntimeError('Changelog has not yet been generated')
        if self.version_string is None:
            raise RuntimeError('No version string has been generated')

        print 'Writing CHANGELOG file'
        if len(self.changelog) > 0:
            if self.increment_build is True:
                self.changelog.append('\n{0}\n'.format(self.version_string))
        with open('{0}/CHANGELOG.txt'.format(self.path_code), 'w') as changelog_file:
            changelog_file.write('\n'.join(self.changelog))

    def _generate_version_string(self):
        """
        Generates a version string which will be used to identify the package
        - Looks at previous builds
        - Will the increment the last-built package's build number if changes have been detected
        :return:
        """
        # Validation
        if any(item is None for item in [self.tag_data, self.version, self.revision_hash]):
            raise RuntimeError('No sources have been collected')

        print 'Generating build'
        builds = sorted(tag['build'] for tag in self.tag_data if tag['version'] == self.version)
        if len(builds) > 0:
            build = builds[-1]
            if (self.revision is None or self.release == 'hotfix') and self.increment_build is True:
                build += 1
            else:
                print 'No need to increment build'
        else:
            build = 0
        print 'Build: {0}'.format(build)

        suffix = ''
        # Generate a suffix for artifact-only builds or develop/experimental builds to distinguish them from release builds
        if self.release in ['develop', 'experimental'] or (self.artifact_only is True and self.release != 'hotfix'):
            print 'Generating a suffix'
            suffix = 'dev.{0}.{1}'.format(int(time.time()), self.revision_hash)

        self.version_string = '{0}.{1}{2}'.format(self.version, build, '-{0}'.format(suffix))
        print 'Full version: {0}'.format(self.version_string)

        return self.version_string

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
                print 'Debug - Running command: {0}'.format(command)
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
