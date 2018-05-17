# Copyright (C) 2018 iNuron NV
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
Packager module
"""

import os
import shutil
from packaging.sourcecollector import SourceCollector


class Packager(object):
    """
    Base class for packagers
    """

    DISTRO_OPTIONS = ['redhat', 'debian']
    PACKAGE_SUFFIX_OPTIONS = ['.rpm', '.deb']

    def __init__(self, source_collector, dry_run=False, distro='', package_suffix=''):
        """
        Creates an instance of a DebianPacker
        This instance is tied to a SourceCollector instance which holds all product information
        :param source_collector: SourceCollector instance
        :param dry_run: Run the source collector in dry run mode
        :param distro: Distro to package for. Can be 'debian' or 'redhat'
        * This will not do any impacting changes (like uploading/tagging)
        """
        if distro not in self.DISTRO_OPTIONS:
            raise ValueError('Distro "{0}" is not a valid option. Possible options are: {1}'.format(distro, ', '.join(self.DISTRO_OPTIONS)))
        if package_suffix not in self.PACKAGE_SUFFIX_OPTIONS:
            raise ValueError('Suffix "{0}" is not a valid option. Possible options are: {1}'.format(package_suffix, ', '.join(self.PACKAGE_SUFFIX_OPTIONS)))
        self.distro = distro
        self.package_suffix = package_suffix
        self.source_collector = source_collector
        self.dry_run = dry_run

        # Milestone
        self.packaged = False
        self.package_folder = os.path.join(self.source_collector.path_package, self.distro)

    def package(self):
        """
        Packages the related product.
        """
        raise NotImplementedError('Packaging logic has to be implemented. It must set self.packaged to True when finished')

    def prepare_artifact(self):
        """
        Prepares the current package to be stored as an artifact on Jenkins
        :return: None
        :rtype: NoneType
        """
        # Get the current workspace directory
        workspace_folder = os.environ['WORKSPACE']
        artifact_folder = os.path.join(workspace_folder, 'artifacts')
        # Clear older artifacts
        if os.path.exists(artifact_folder):
            shutil.rmtree(artifact_folder)
        shutil.copytree(self.package_folder, artifact_folder)

    def upload(self, add, hotfix_release=None):
        """
        Uploads a given set of packages
        :param add: Should the package be added to the repository
        :param hotfix_release: Which release to hotfix for (Add should still be True when wanting to add it to the repository)
        """
        if self.packaged is False:
            raise RuntimeError('Product has not yet been packaged. Unable to upload it')
        # Validation
        release_repo = self.source_collector.release_repo
        package_tags = self.source_collector.package_tags
        if any(item is None for item in [release_repo, package_tags]):
            raise RuntimeError('The given source collector has not yet collected all of the required information')

        settings = self.source_collector.settings

        package_info = settings['repositories']['packages'].get(self.distro, [])
        for destination in package_info:
            server = destination['ip']
            tags = destination.get('tags', [])
            if len(set(tags).intersection(package_tags)) == 0:
                print 'Skipping {0} ({1}). {2} requested'.format(server, tags, package_tags)
                continue
            user = destination['user']
            base_path = destination['base_path']
            pool_path = os.path.join(base_path, self.distro, 'pool/main')

            print 'Publishing to {0}@{1}'.format(user, server)
            print 'Determining upload path'
            if hotfix_release:
                upload_path = os.path.join(base_path, hotfix_release)
            else:
                upload_path = os.path.join(base_path, release_repo)
            print '    Upload path is: {0}'.format(upload_path)
            deb_packages = [filename for filename in os.listdir(self.package_folder) if filename.endswith(self.package_suffix)]
            print 'Creating the upload directory on the server'
            SourceCollector.run(command="ssh {0}@{1} 'mkdir -p {2}'".format(user, server, upload_path),
                                working_directory=self.package_folder)
            for deb_package in deb_packages:
                print '   {0}'.format(deb_package)
                destination_path = os.path.join(upload_path, deb_package)
                print '   Determining if the package is already present'
                find_pool_package_command = "ssh {0}@{1} 'find {2}/ -name \"{3}\"'".format(user, server, pool_path, deb_package)
                pool_package = SourceCollector.run(command=find_pool_package_command,
                                                   working_directory=self.package_folder).strip()
                if pool_package != '':
                    print '    Already present on server, using that package'
                    place_command = "ssh {0}@{1} 'cp {2} {3}'".format(user, server, pool_package, destination_path)
                else:
                    print '    Uploading package'
                    source_path = os.path.join(self.package_folder, deb_package)
                    place_command = "scp {0} {1}@{2}:{3}".format(source_path, user, server, destination_path)
                SourceCollector.run(command=place_command, print_only=self.dry_run, working_directory=self.package_folder)
                if add is True:
                    print '    Adding package to repo'
                    if hotfix_release:
                        include_release = hotfix_release
                    else:
                        include_release = release_repo
                    print '    Release to include: {0}'.format(include_release)
                    remote_command = "ssh {0}@{1} 'reprepro -Vb {2}/debian includedeb {3} {4}'".format(user, server, base_path, include_release, destination_path)
                    SourceCollector.run(command=remote_command, print_only=self.dry_run, working_directory=self.package_folder)
                else:
                    print '    NOT adding package to repo'
                    print '    Package can be found at: {0}'.format(destination_path)
