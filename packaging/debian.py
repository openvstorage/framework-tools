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
Debian packager module
"""
import os
import shutil
from sourcecollector import SourceCollector


class DebianPackager(object):
    """
    DebianPackager class

    Responsible for creating debian packages from the source archive
    """

    def __init__(self, source_collector, dry_run=False):
        """
        Creates an instance of a DebianPacker
        This instance is tied to a SourceCollector instance which holds all product information
        :param source_collector: SourceCollector instance
        :param dry_run: Run the source collector in dry run mode
        * This will not do any impacting changes (like uploading/tagging)
        """
        self.source_collector = source_collector
        self.dry_run = dry_run

        # Milestone
        self.packaged = False
        self.debian_folder = os.path.join(self.source_collector.path_package, 'debian')

    def package(self):
        """
        Packages the related product.
        """
        # Validation
        product = self.source_collector.product
        release_repo = self.source_collector.release_repo
        version_string = self.source_collector.version_string
        revision_date = self.source_collector.revision_date
        package_name = self.source_collector.package_name
        if any(item is None for item in [product, release_repo, version_string, revision_date, package_name]):
            raise RuntimeError('The given source collector has not yet collected all of the required information')

        path_code = self.source_collector.path_code
        path_package = self.source_collector.path_package

        # Prepare
        # /<pp>/debian
        if os.path.exists(self.debian_folder):
            shutil.rmtree(self.debian_folder)
        # /<rp>/packaging/debian -> /<pp>/debian
        shutil.copytree('{0}/packaging/debian'.format(path_code), self.debian_folder)

        # Rename tgz
        # /<pp>/<package name>_1.2.3.tar.gz -> /<pp>/debian/<package name>_1.2.3.orig.tar.gz
        shutil.copyfile('{0}/{1}_{2}.tar.gz'.format(path_package, package_name, version_string),
                        '{0}/{1}_{2}.orig.tar.gz'.format(self.debian_folder, package_name, version_string))
        # /<pp>/debian/<package name>-1.2.3/...
        SourceCollector.run(command='tar -xzf {0}_{1}.orig.tar.gz'.format(package_name, version_string),
                            working_directory=self.debian_folder)

        # Move the debian package metadata into the extracted source
        # /<pp>/debian/debian -> /<pp>/debian/<package name>-1.2.3/
        SourceCollector.run(command='mv {0}/debian {0}/{1}-{2}/'.format(self.debian_folder, package_name, version_string),
                            working_directory=path_package)

        # Build changelog entry
        with open('{0}/{1}-{2}/debian/changelog'.format(self.debian_folder, package_name, version_string), 'w') as changelog_file:
            changelog_file.write("""{0} ({1}-1) {2}; urgency=low

  * For changes, see individual changelogs

 -- Packaging System <engineering@openvstorage.com>  {3}
""".format(package_name, version_string, release_repo, revision_date.strftime('%a, %d %b %Y %H:%M:%S +0000')))

        # Some more tweaks
        SourceCollector.run(command='chmod 770 {0}/{1}-{2}/debian/rules'.format(self.debian_folder, package_name, version_string),
                            working_directory=path_package)
        SourceCollector.run(command="sed -i -e 's/__NEW_VERSION__/{0}/' *.*".format(version_string),
                            working_directory='{0}/{1}-{2}/debian'.format(self.debian_folder, package_name, version_string))

        # Build the package
        SourceCollector.run(command='dpkg-buildpackage',
                            working_directory='{0}/{1}-{2}'.format(self.debian_folder, package_name, version_string))
        self.packaged = True

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
        shutil.copytree(self.debian_folder, artifact_folder)

    def upload(self, add, hotfix_release=None):
        """
        Uploads a given set of packages
        :param add: Should the package be added to the repository
        :param hotfix_release: Which release to hotfix for (Add should still be True when wanting to add it to the repository)
        """
        if self.packaged is False:
            raise RuntimeError('Product has not yet been packaged. Unable to upload it')
        # Validation
        product = self.source_collector.product
        release_repo = self.source_collector.release_repo
        version_string = self.source_collector.version_string
        revision_date = self.source_collector.revision_date
        package_name = self.source_collector.package_name
        package_tags = self.source_collector.tags
        if any(item is None for item in [product, release_repo, version_string, revision_date, package_name, package_tags]):
            raise RuntimeError('The given source collector has not yet collected all of the required information')

        settings = self.source_collector.settings

        package_info = settings['repositories']['packages'].get('debian', [])
        for destination in package_info:
            server = destination['ip']
            tags = destination.get('tags', [])
            if len(set(tags).intersection(package_tags)) == 0:
                print 'Skipping {0} ({1}). {2} requested'.format(server, tags, package_tags)
                continue
            user = destination['user']
            base_path = destination['base_path']
            pool_path = os.path.join(base_path, 'debian/pool/main')

            print 'Publishing to {0}@{1}'.format(user, server)
            print 'Determining upload path'
            if hotfix_release:
                upload_path = os.path.join(base_path, hotfix_release)
            else:
                upload_path = os.path.join(base_path, release_repo)
            print '    Upload path is: {0}'.format(upload_path)
            deb_packages = [filename for filename in os.listdir(self.debian_folder) if filename.endswith('.deb')]
            print 'Creating the upload directory on the server'
            SourceCollector.run(command="ssh {0}@{1} 'mkdir -p {2}'".format(user, server, upload_path),
                                working_directory=self.debian_folder)
            for deb_package in deb_packages:
                print '   {0}'.format(deb_package)
                destination_path = os.path.join(upload_path, deb_package)
                print '   Determining if the package is already present'
                find_pool_package_command = "ssh {0}@{1} 'find {2}/ -name \"{3}\"'".format(user, server, pool_path, deb_package)
                pool_package = SourceCollector.run(command=find_pool_package_command,
                                                   working_directory=self.debian_folder).strip()
                if pool_package != '':
                    print '    Already present on server, using that package'
                    place_command = "ssh {0}@{1} 'cp {2} {3}'".format(user, server, pool_package, destination_path)
                else:
                    print '    Uploading package'
                    source_path = os.path.join(self.debian_folder, deb_package)
                    place_command = "scp {0} {1}@{2}:{3}".format(source_path, user, server, destination_path)
                SourceCollector.run(command=place_command, print_only=self.dry_run, working_directory=self.debian_folder)
                if add is True:
                    print '    Adding package to repo'
                    if hotfix_release:
                        include_release = hotfix_release
                    else:
                        include_release = release_repo
                    print '    Release to include: {0}'.format(include_release)
                    remote_command = "ssh {0}@{1} 'reprepro -Vb {2}/debian includedeb {3} {4}'".format(user, server, base_path, include_release, destination_path)
                    SourceCollector.run(command=remote_command, print_only=self.dry_run, working_directory=self.debian_folder)
                else:
                    print '    NOT adding package to repo'
                    print '    Package can be found at: {0}'.format(destination_path)
