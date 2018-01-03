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

    def __init__(self):
        """
        Dummy init method, DebianPackager is static
        """
        raise NotImplementedError('DebianPackager is a static class')

    @classmethod
    def package(cls, metadata):
        """
        Packages a given package.
        """

        product, release, version_string, revision_date, package_name, _ = metadata

        settings = SourceCollector.get_settings()
        _, path_code, path_package, _ = SourceCollector.get_paths(product, settings)

        # Prepare
        # /<pp>/debian
        debian_folder = cls.get_package_destination(product, settings)
        if os.path.exists(debian_folder):
            shutil.rmtree(debian_folder)
        # /<rp>/packaging/debian -> /<pp>/debian
        shutil.copytree('{0}/packaging/debian'.format(path_code), debian_folder)

        # Rename tgz
        # /<pp>/<package name>_1.2.3.tar.gz -> /<pp>/debian/<package name>_1.2.3.orig.tar.gz
        shutil.copyfile('{0}/{1}_{2}.tar.gz'.format(path_package, package_name, version_string),
                        '{0}/{1}_{2}.orig.tar.gz'.format(debian_folder, package_name, version_string))
        # /<pp>/debian/<package name>-1.2.3/...
        SourceCollector.run(command='tar -xzf {0}_{1}.orig.tar.gz'.format(package_name, version_string),
                            working_directory=debian_folder)

        # Move the debian package metadata into the extracted source
        # /<pp>/debian/debian -> /<pp>/debian/<package name>-1.2.3/
        SourceCollector.run(command='mv {0}/debian {0}/{1}-{2}/'.format(debian_folder, package_name, version_string),
                            working_directory=path_package)

        # Build changelog entry
        with open('{0}/{1}-{2}/debian/changelog'.format(debian_folder, package_name, version_string), 'w') as changelog_file:
            changelog_file.write("""{0} ({1}-1) {2}; urgency=low

  * For changes, see individual changelogs

 -- Packaging System <engineering@openvstorage.com>  {3}
""".format(package_name, version_string, release, revision_date.strftime('%a, %d %b %Y %H:%M:%S +0000')))

        # Some more tweaks
        SourceCollector.run(command='chmod 770 {0}/{1}-{2}/debian/rules'.format(debian_folder, package_name, version_string),
                            working_directory=path_package)
        SourceCollector.run(command="sed -i -e 's/__NEW_VERSION__/{0}/' *.*".format(version_string),
                            working_directory='{0}/{1}-{2}/debian'.format(debian_folder, package_name, version_string))

        # Build the package
        SourceCollector.run(command='dpkg-buildpackage',
                            working_directory='{0}/{1}-{2}'.format(debian_folder, package_name, version_string))

    @classmethod
    def prepare_artifact(cls, metadata):
        """
        Prepares the current package to be stored as an artifact on Jenkins
        :param metadata: Metadata about the product
        :return: None
        :rtype: NoneType
        """
        product, release, version_string, revision_date, package_name, _ = metadata
        # Get the current workspace directory
        debian_folder = cls.get_package_destination(product)
        workspace_folder = os.environ['WORKSPACE']
        artifact_folder = os.path.join(workspace_folder, 'artifacts')
        # Clear older artifacts
        if os.path.exists(artifact_folder):
            shutil.rmtree(artifact_folder)
        shutil.copytree(debian_folder, artifact_folder)

    @classmethod
    def get_package_destination(cls, product, settings=None):
        """
        Return the directory where the packages will be placed
        :param product: The product to build
        :param settings: Settings to use, defaults to the provided settings in the settings.json
        :return: The path to the directory of the packages
        """
        _, _, path_package, _ = SourceCollector.get_paths(product, settings)
        return os.path.join(path_package, 'debian')

    @classmethod
    def upload(cls, metadata, add, hotfix_release=None):
        """
        Uploads a given set of packages
        :param metadata: Metadata about the package to upload
        :param add: Should the package be added to the repository
        :param hotfix_release: Which release to hotfix for (Add should still be True when wanting to add it to the repository)
        """

        product, release, version_string, revision_date, package_name, package_tags = metadata

        settings = SourceCollector.get_settings()
        _, _, path_package, _ = SourceCollector.get_paths(product, settings)

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
                upload_path = os.path.join(base_path, release)
            print '    Upload path is: {0}'.format(upload_path)
            debs_path = cls.get_package_destination(product, settings)
            deb_packages = [filename for filename in os.listdir(debs_path) if filename.endswith('.deb')]
            print 'Creating the upload directory on the server'
            SourceCollector.run(command="ssh {0}@{1} 'mkdir -p {2}'".format(user, server, upload_path),
                                working_directory=debs_path)
            for deb_package in deb_packages:
                print '   {0}'.format(deb_package)
                destination_path = os.path.join(upload_path, deb_package)
                print '   Determining if the package is already present'
                find_pool_package_command = "ssh {0}@{1} 'find {2}/ -name \"{3}\"'".format(user, server, pool_path, deb_package)
                pool_package = SourceCollector.run(command=find_pool_package_command,
                                                   working_directory=debs_path).strip()
                if pool_package != '':
                    print '    Already present on server, using that package'
                    cp_command = "ssh {0}@{1} 'cp {2} {3}'".format(user, server, pool_package, destination_path)
                    SourceCollector.run(command=cp_command, working_directory=debs_path)
                else:
                    print '    Uploading package'
                    source_path = os.path.join(debs_path, deb_package)

                    scp_command = "scp {0} {1}@{2}:{3}".format(source_path, user, server, destination_path)
                    SourceCollector.run(command=scp_command, working_directory=debs_path)
                if add is True:
                    print '    Adding package to repo'
                    if hotfix_release:
                        include_release = hotfix_release
                    else:
                        include_release = release
                    print '    Release to include: {0}'.format(include_release)
                    remote_command = "ssh {0}@{1} 'reprepro -Vb {2}/debian includedeb {3} {4}'".format(user, server, base_path, include_release, destination_path)
                    SourceCollector.run(command=remote_command, working_directory=debs_path)
                else:
                    print '    NOT adding package to repo'
                    print '    Package can be found at: {0}'.format(destination_path)
